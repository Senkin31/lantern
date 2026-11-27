"""POST /analyze — checks a resident photo with a vision LLM (Nebius Token Factory, OpenAI-compatible).
Returns: relevant (accept|review|reject), score, hint (snow|blocked|ice|icicles|unknown), note.
Any error or timeout -> review, so a person decides. The key lives only in .env (NEBIUS_API_KEY)."""
import base64, io, json, os, re
from PIL import Image

BASE_URL = os.getenv('NEBIUS_BASE_URL', 'https://api.tokenfactory.nebius.com/v1/')
MODEL = os.getenv('VLM_MODEL', 'Qwen/Qwen2.5-VL-72B-Instruct')
TIMEOUT = float(os.getenv('ANALYZE_TIMEOUT', '10'))
HINTS = {'snow', 'blocked', 'ice', 'icicles', 'unknown'}

PROMPT = """You check photos that residents send to the Riga City Council about winter hazards on sidewalks.
Comment from the resident: "{comment}"
Rules of the city (RD-24-270-sn): sidewalks do NOT have to be cleared down to the bare surface; packed snow is fine.
A sidewalk counts as CLEARED if a track at least half of its width and at least 1.5 m wide has been cleared
(plough marks or snowbanks along the edges are typical) and the surface is not slippery.
It is a HAZARD if: the sidewalk is under untouched snow (only footprints), the cleared track is clearly too narrow,
a snowbank blocks the way (e.g. at a crossing or stop), there is visible ice / a slippery surface, or icicles hang over a footway.
Not relevant: selfies, screenshots, indoor photos, cleared sidewalks, snow only on grass verges or lawns, unrelated objects.
Answer ONLY with JSON: {{"relevant": true|false, "score": 0..1, "hint": "snow|blocked|ice|icicles|unknown", "note": "<max 15 words, English>"}}
relevant = the photo shows such a hazard on a sidewalk, path, crossing or stop. score = how sure you are."""

def _small_jpeg(data: bytes) -> str:
    im = Image.open(io.BytesIO(data)).convert('RGB'); im.thumbnail((1024, 1024))
    b = io.BytesIO(); im.save(b, 'JPEG', quality=85); return base64.b64encode(b.getvalue()).decode()

def _decide(j: dict) -> dict:
    score = max(0.0, min(1.0, float(j.get('score', 0))))
    hint = j.get('hint') if j.get('hint') in HINTS else 'unknown'
    if not j.get('relevant'): rel = 'reject' if score >= 0.6 else 'review'   # unsure "not relevant" -> human
    else: rel = 'accept' if score >= 0.6 else 'review'
    return dict(relevant=rel, score=round(score, 2), hint=hint, note=str(j.get('note', ''))[:120])

def analyze(photo: bytes, comment: str = '') -> dict:
    key = os.getenv('NEBIUS_API_KEY')
    if not key: return dict(relevant='review', score=0.0, hint='unknown', note='no API key, needs manual review')
    try:
        from openai import OpenAI
        cl = OpenAI(base_url=BASE_URL, api_key=key, timeout=TIMEOUT, max_retries=0)
        r = cl.chat.completions.create(model=MODEL, temperature=0, max_tokens=150, messages=[{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT.format(comment=(comment or '')[:500].replace('"', "'"))},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + _small_jpeg(photo)}}]}])
        txt = r.choices[0].message.content or ''
        m = re.search(r'\{.*\}', txt, re.S)
        return _decide(json.loads(m.group(0)))
    except Exception as e:
        return dict(relevant='review', score=0.0, hint='unknown', note=f'check failed ({type(e).__name__}), needs manual review')
