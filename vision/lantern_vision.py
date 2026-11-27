"""Lantern vision: is the sidewalk zone in a camera frame clear, partly cleared or covered with snow?
Runs with onnxruntime + numpy + pillow only (no torch), so it works on x86 and ARM laptops.
Model: YOLO11n-cls backbone (Ultralytics, AGPL-3.0) as a frozen feature extractor -> logistic regression heads
trained on SkyFinder day-level labels (cameras 7233, 10917)."""
import json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
HERE = os.path.dirname(os.path.abspath(__file__))

def zone_crop(im: Image.Image, pts, fill=(114, 114, 114)) -> Image.Image:
    """Crop the bounding box of a zone polygon; pixels outside the polygon become grey."""
    m = Image.new('L', im.size, 0); ImageDraw.Draw(m).polygon([tuple(map(float, p)) for p in pts], fill=255)
    g = Image.new('RGB', im.size, fill); g.paste(im, mask=m)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return g.crop((max(0, int(min(xs))), max(0, int(min(ys))), min(im.width, int(max(xs)) + 1), min(im.height, int(max(ys)) + 1)))

def light_check(crop: Image.Image):
    """Returns (ok, reason). Night frames and sodium-lit frames are not judged."""
    a = np.asarray(crop.convert('RGB'), np.float32).reshape(-1, 3)
    a = a[~(np.abs(a - 114) < 1).all(1)]
    if len(a) == 0: return False, 'empty zone'
    if a.mean() < 35: return False, 'too dark'
    if a[:, 2].mean() / (a[:, 0].mean() + 1e-6) < 0.75: return False, 'street lighting (night)'
    return True, ''

def _prep(im: Image.Image) -> np.ndarray:
    """Letterbox to 224x224 (keep the whole zone, pad with grey) - narrow zones like crossings are not cut."""
    im = im.convert('RGB'); w, h = im.size; s = 224 / max(w, h)
    im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    canvas = Image.new('RGB', (224, 224), (114, 114, 114)); canvas.paste(im, ((224 - im.width) // 2, (224 - im.height) // 2))
    return np.asarray(canvas, np.float32).transpose(2, 0, 1)[None] / 255

def decide(p_nc: float, th: dict, was: str = None) -> dict:
    """Council rule (RD-24-270-sn): packed snow with a cleared track counts as cleared; untouched snow does not.
    p_nc = probability that the walking zone was NOT cleared at all.
    - p_nc >= 0.5 -> 'not_cleared': snow, confidence >= 0.5, the app may send it to the contractor;
    - p_nc >= 0.3 -> 'check': snow, confidence < 0.5, inspector only;
    - otherwise 'cleared'.
    `was` = previous level of this zone; thresholds get a 0.05 hysteresis."""
    h = lambda key, level: th[key] - (0.05 if was == level else -0.05 if was is not None else 0.0)
    if p_nc >= h('not_cleared', 'not_cleared'):
        return dict(hazard_class='snow', level='not_cleared', confidence=round(p_nc, 3), blocked_share=round(0.5 + 0.5 * p_nc, 2))
    if p_nc >= h('check', 'check'):
        return dict(hazard_class='snow', level='check', confidence=round(min(0.49, p_nc), 3), blocked_share=round(p_nc, 2))
    return dict(hazard_class='clear', level='cleared', confidence=round(1 - p_nc, 3), blocked_share=round(0.3 * p_nc, 2))


class SnowModel:
    def __init__(self, onnx_path=os.path.join(HERE, 'lantern_embed.onnx'), heads_path=os.path.join(HERE, 'lantern_heads.json')):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
        self.heads = json.load(open(heads_path))

    def embed(self, crop: Image.Image) -> np.ndarray:
        e = self.sess.run(None, {'image': _prep(crop)})[0][0]
        return e / (np.linalg.norm(e) + 1e-9)

    def _p(self, name, e):
        h = self.heads[name]; z = (e - np.array(h['mean'])) / np.array(h['scale'])
        return float(1 / (1 + np.exp(-(z @ np.array(h['coef']) + h['intercept']))))

    def predict_crop(self, crop: Image.Image) -> dict:
        ok, why = light_check(crop)
        if not ok: return dict(judged=False, reason=why)
        e = self.embed(crop)
        p_snow = self._p('snow', e)
        p_nc = self._p('not_cleared', e) if 'not_cleared' in self.heads else min(self._p('covered', e), p_snow)
        r = decide(p_nc, self.heads['thresholds'])
        r.update(judged=True, p_snow=round(p_snow, 3), p_not_cleared=round(p_nc, 3))
        return r

    def predict_frame(self, im: Image.Image, zones) -> list:
        """zones: list of {zone_id, points} in the frame's pixel coordinates."""
        im = im.convert('RGB'); out = []
        for z in zones:
            c = zone_crop(im, z['points']); r = self.predict_crop(c); r['zone_id'] = z.get('zone_id'); r['_crop'] = c; out.append(r)
        return out
