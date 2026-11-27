"""Second opinion from a vision-language model (Qwen2.5-VL via Nebius Token Factory, OpenAI-compatible)
for camera zones the small model flagged. Uses the council's rule (RD-24-270-sn, mentor's answer 25.11).
Without NEBIUS_API_KEY, or on any error/timeout, returns verdict 'unsure' and the small model's result stands."""
import base64, io, json, os, re
from PIL import Image, ImageDraw

BASE_URL = os.getenv('NEBIUS_BASE_URL', 'https://api.tokenfactory.nebius.com/v1/')
MODEL = os.getenv('VLM_MODEL', 'moonshotai/Kimi-K3')
TIMEOUT = float(os.getenv('VLM_TIMEOUT', '20'))
VERDICTS = {'cleared', 'partial', 'not_cleared', 'unsure'}

PROMPT = """This is a frame from a city camera. The red outline marks a sidewalk / footpath zone ({place}).
Judge ONLY the walking surface inside the red outline, using the Riga City Council rule (RD-24-270-sn):
- sidewalks do NOT have to be cleared down to the bare surface; packed snow is acceptable;
- CLEARED: a cleared track at least half of the zone width (and at least 1.5 m) - plough marks, a smooth packed track,
  or snowbanks pushed to the edges; or the surface is visible;
- PARTIAL: a cleared track exists but is clearly narrower than half of the width;
- NOT_CLEARED: untouched snow over the walking surface, only footprints or ski tracks, no plough track;
- UNSURE: too dark, blurred, covered by an object, or the zone is not visible.
Snow on grass verges or lawns outside the walking surface does not matter.
Answer ONLY with JSON: {{"verdict": "cleared|partial|not_cleared|unsure", "confidence": 0..1, "note": "<max 15 words>"}}"""


def zone_view(im: Image.Image, pts, max_side=1024) -> Image.Image:
    """The zone with context around it and a red outline."""
    im = im.convert('RGB').copy(); d = ImageDraw.Draw(im); p = [tuple(map(float, q)) for q in pts]
    d.line(p + [p[0]], fill=(255, 0, 0), width=max(3, im.width // 300))
    xs, ys = [q[0] for q in p], [q[1] for q in p]; w, h = max(xs) - min(xs), max(ys) - min(ys)
    box = (max(0, min(xs) - 0.6 * w - 40), max(0, min(ys) - 0.6 * h - 40), min(im.width, max(xs) + 0.6 * w + 40), min(im.height, max(ys) + 0.6 * h + 40))
    v = im.crop(tuple(int(b) for b in box)); v.thumbnail((max_side, max_side)); return v


def _b64(im):
    b = io.BytesIO(); im.save(b, 'JPEG', quality=88); return base64.b64encode(b.getvalue()).decode()


def check_zone(im: Image.Image, pts, place='sidewalk') -> dict:
    key = os.getenv('NEBIUS_API_KEY')
    if not key: return dict(verdict='unsure', confidence=0.0, note='no API key')
    try:
        from openai import OpenAI
        cl = OpenAI(base_url=BASE_URL, api_key=key, timeout=TIMEOUT, max_retries=0)
        r = cl.chat.completions.create(model=MODEL, temperature=0, max_tokens=int(os.getenv('VLM_MAX_TOKENS', '1500')), messages=[{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT.format(place=place)},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + _b64(zone_view(im, pts))}}]}])
        msg = r.choices[0].message
        text = (msg.content or '') + '\n' + (getattr(msg, 'reasoning_content', None) or '')   # reasoning models may answer late
        found = re.findall(r'\{[^{}]*"verdict"[^{}]*\}', text, re.S)
        if not found and (msg.content or '').strip():                # answered in prose: ask once more for the JSON only
            r2 = cl.chat.completions.create(model=MODEL, temperature=0, max_tokens=int(os.getenv('VLM_MAX_TOKENS', '1500')), messages=[
                {'role': 'user', 'content': PROMPT.format(place=place)}, {'role': 'assistant', 'content': msg.content},
                {'role': 'user', 'content': 'Now give ONLY the JSON object for your answer above, nothing else.'}])
            m2 = r2.choices[0].message
            text = (m2.content or '') + '\n' + (getattr(m2, 'reasoning_content', None) or '')
            found = re.findall(r'\{[^{}]*"verdict"[^{}]*\}', text, re.S)
        if not found:
            return dict(verdict='unsure', confidence=0.0, note='no JSON in answer: ' + ' '.join(text.split())[:80])
        j = json.loads(found[-1])
        v = str(j.get('verdict', 'unsure')).lower().replace(' ', '_')
        return dict(verdict=v if v in VERDICTS else 'unsure', confidence=max(0.0, min(1.0, float(j.get('confidence', 0)))), note=str(j.get('note', ''))[:120])
    except Exception as e:
        return dict(verdict='unsure', confidence=0.0, note=f'VLM failed: {type(e).__name__}: {str(e)[:80]}')


def fuse(model: dict, vlm: dict) -> dict:
    """Combine the small model's level with the VLM verdict. Returns fields to update on the result.
    The contractor gets an order only when both agree on 'not cleared', or the VLM is sure of it."""
    lvl, v, c = model['level'], vlm['verdict'], vlm['confidence']
    if v == 'unsure' or c < 0.5:
        return dict(vlm=v)                                         # keep the small model's answer
    if v == 'not_cleared':
        conf = max(model['confidence'], c) if lvl == 'not_cleared' else round(0.5 + 0.3 * c, 3)
        return dict(vlm=v, hazard_class='snow', level='not_cleared', confidence=round(conf, 3), blocked_share=0.9)
    if v == 'partial':                                             # narrow track: a violation, but a small one (e-mail level)
        return dict(vlm=v, hazard_class='snow', level='partial', confidence=0.55, blocked_share=0.4)
    # VLM says cleared
    if lvl == 'not_cleared':                                       # disagreement -> inspector only
        return dict(vlm=v, hazard_class='snow', level='check', confidence=0.45, blocked_share=0.3)
    return dict(vlm=v, hazard_class='clear', level='cleared', confidence=round(c, 3), blocked_share=0.05)
