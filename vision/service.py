"""Lantern model service (port 8001).
  GET  /health
  POST /analyze   multipart: photo, comment -> {relevant: accept|review|reject, score, hint, note}   (resident reports)
  POST /classify  multipart: image, zones (optional JSON list of {zone_id, points}) -> per-zone snow verdicts
  GET  /media/... crops and frames saved by camera_worker.py
Run:  uvicorn service:app --host 0.0.0.0 --port 8001"""
import asyncio, io, json, os
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass
import analyze
from lantern_vision import SnowModel

MEDIA = os.getenv('LANTERN_MEDIA', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media'))
os.makedirs(MEDIA, exist_ok=True)
app = FastAPI(title='Lantern model service')
app.mount('/media', StaticFiles(directory=MEDIA), name='media')
model = SnowModel()

@app.get('/health')
def health(): return {'ok': True, 'vlm_key': bool(os.getenv('NEBIUS_API_KEY')), 'model': model.heads.get('info', {})}

@app.post('/analyze')
async def analyze_photo(photo: UploadFile = File(...), comment: str = Form('')):
    data = await photo.read()
    try:
        return await asyncio.wait_for(asyncio.to_thread(analyze.analyze, data, comment), timeout=analyze.TIMEOUT + 1)
    except asyncio.TimeoutError:
        return dict(relevant='review', score=0.0, hint='unknown', note='check timed out, needs manual review')

@app.post('/classify')
async def classify(image: UploadFile = File(...), zones: str = Form('')):
    im = Image.open(io.BytesIO(await image.read())).convert('RGB')
    zs = json.loads(zones) if zones else [{'zone_id': 'full', 'points': [[0, 0], [im.width, 0], [im.width, im.height], [0, im.height]]}]
    out = model.predict_frame(im, zs)
    for r in out: r.pop('_crop', None)
    return out
