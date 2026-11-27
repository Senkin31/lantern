"""Checks the model against your own labels from label_fintraffic.html.
  python evaluate_fintraffic.py --labels fintraffic_labels.csv --frames <frames folder>
Prints, for each of your labels (v2: cleared / partial / not_cleared), how often the model said cleared / check (inspector only) / not_cleared (goes to the contractor)."""
import argparse, collections, csv, json, os
from PIL import Image
from lantern_vision import SnowModel
p = argparse.ArgumentParser(); p.add_argument('--labels', required=True); p.add_argument('--frames', required=True)
p.add_argument('--config', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'cameras.json')); a = p.parse_args()
zones = {z['zone_id']: z for c in json.load(open(a.config, encoding='utf-8'))['cameras'] for z in c.get('zones', []) if 'zone_id' in z}
m = SnowModel(); tab = collections.defaultdict(collections.Counter); per_zone = collections.defaultdict(collections.Counter)
for r in csv.DictReader(open(a.labels, encoding='utf-8')):
    if r['label'] == 'unknown' or r['zone_id'] not in zones: continue
    out = m.predict_frame(Image.open(os.path.join(a.frames, r['file'])), [zones[r['zone_id']]])[0]
    lev = out['level'] if out['judged'] else 'not judged'
    tab[r['label']][lev] += 1; per_zone[r['zone_id']][(r['label'], lev)] += 1
levels = ['cleared', 'check', 'not_cleared', 'not judged']
print(f"{'true label':10} " + ' '.join(f'{l:>11}' for l in levels))
for lab in ['cleared', 'partial', 'not_cleared', 'clear', 'covered']:
    if tab[lab]: print(f'{lab:10} ' + ' '.join(f'{tab[lab][l]:>11}' for l in levels))
print('\nfalse orders to the contractor = cleared frames judged "not_cleared":', tab['cleared']['not_cleared'], 'of', sum(tab['cleared'].values()))
for z, c in sorted(per_zone.items()): print(' ', z, dict(c))
