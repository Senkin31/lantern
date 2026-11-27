"""How good is the VLM second opinion? Runs the small model and the VLM on your labelled frames and prints tables.
Needs NEBIUS_API_KEY in .env. About 1 request per labelled frame (89 for labels v2), a few minutes.
  py vlm_eval.py --labels <labels.csv> --frames <frames folder>
Options: --only-flagged  ask the VLM only where the small model flagged the zone (as camera_worker --vlm does)."""
import argparse, collections, csv, json, os
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass
from PIL import Image
from lantern_vision import SnowModel
import vlm_check
p = argparse.ArgumentParser(); p.add_argument('--labels', required=True); p.add_argument('--frames', required=True)
p.add_argument('--config', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'cameras.json'))
p.add_argument('--only-flagged', action='store_true'); p.add_argument('--out', default='vlm_eval_results.csv'); a = p.parse_args()
if not os.getenv('NEBIUS_API_KEY'): raise SystemExit('NEBIUS_API_KEY is not set (.env)')
cams = {c['camera_id']: c for c in json.load(open(a.config, encoding='utf-8'))['cameras']}
zones = {z['zone_id']: (z, cams[z['zone_id'].split(':')[0]]) for c in cams.values() for z in c.get('zones', [])}
m = SnowModel(); T = {k: collections.Counter() for k in ['model', 'vlm', 'fused']}; rows = []
for r in csv.DictReader(open(a.labels, encoding='utf-8')):
    if r['label'] == 'unknown' or r['zone_id'] not in zones: continue
    z, cam = zones[r['zone_id']]; im = Image.open(os.path.join(a.frames, r['file'])).convert('RGB')
    res = m.predict_frame(im, [z])[0]
    if not res['judged']: continue
    v = dict(verdict='skipped', confidence=0, note='') if (a.only_flagged and res['level'] == 'cleared') else vlm_check.check_zone(im, z['points'], cam.get('place_type', 'sidewalk'))
    fused = dict(res); fused.update(vlm_check.fuse(res, v)) if v['verdict'] != 'skipped' else None
    T['model'][(r['label'], res['level'])] += 1; T['vlm'][(r['label'], v['verdict'])] += 1; T['fused'][(r['label'], fused['level'])] += 1
    rows.append([r['file'], r['zone_id'], r['label'], res['level'], round(res['p_not_cleared'], 3), v['verdict'], v['confidence'], fused['level'], v['note']])
    print(f"{r['file']:35} label={r['label']:12} model={res['level']:12} vlm={v['verdict']:12} -> {fused['level']}")
with open(a.out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['file', 'zone_id', 'label', 'model', 'p_not_cleared', 'vlm', 'vlm_conf', 'fused', 'note']); w.writerows(rows)
for k, c in T.items():
    print(f'\n== {k}: rows = your label, columns = answer')
    cols = sorted({b for _, b in c}); print(f"{'':12}" + ''.join(f'{x:>13}' for x in cols))
    for lab in ['cleared', 'partial', 'not_cleared']:
        if any(l == lab for l, _ in c): print(f'{lab:12}' + ''.join(f'{c[(lab, x)]:>13}' for x in cols))
print('\nsaved', a.out)
