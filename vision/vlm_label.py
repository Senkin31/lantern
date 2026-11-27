"""
Lantern: label harvested Fintraffic frames with the VLM (Kimi-K3) by the council rule, then let a person check them.

  py vlm_label.py --frames <frames folder> --zones config/zones_hist.json

What it does:
  1. for every camera in the zones file, takes its daylight frames (sun > -3 deg, broken/tiny images skipped);
  2. asks the VLM about the zone (same prompt and rule as vlm_check.py) -> verdict, confidence, note;
  3. writes labels_kimi.csv (resumable: frames already labelled are skipped);
  4. writes review_kimi.html: every frame with the zone outlined and Kimi's answer pre-selected.
     Open it, press 1 cleared / 2 partial / 3 not cleared / 4 unsure to correct, then "Export CSV"
     -> labels_checked.csv. The page shows how often you agreed with Kimi.

Needs NEBIUS_API_KEY in .env (same as camera_worker --vlm). Images stay local; do not commit them.
"""
import argparse, base64, csv, datetime as dt, html, io, json, math, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, wait
from PIL import Image
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import vlm_check

MIN_BYTES = 20000   # Fintraffic sends a ~10 kB placeholder when a camera is offline


def sun_elevation(lat, lon, t):
    d = t.timetuple().tm_yday; hr = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / 365 * (d - 1 + (hr - 12) / 24)
    decl = 0.006918 - 0.399912*math.cos(g) + 0.070257*math.sin(g) - 0.006758*math.cos(2*g) + 0.000907*math.sin(2*g) - 0.002697*math.cos(3*g) + 0.00148*math.sin(3*g)
    eqt = 229.18 * (0.000075 + 0.001868*math.cos(g) - 0.032077*math.sin(g) - 0.014615*math.cos(2*g) - 0.040849*math.sin(2*g))
    ha = math.radians((hr * 60 + eqt + 4 * lon) / 4 - 180); la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la)*math.sin(decl) + math.cos(la)*math.cos(decl)*math.cos(ha)))


def frames_for(root, preset, lat, lon, min_sun):
    folder = os.path.join(root, preset)
    if not os.path.isdir(folder): return []
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not name.endswith('.jpg') or os.path.getsize(path) < MIN_BYTES: continue
        try: t = dt.datetime.strptime(name[:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc)
        except ValueError: continue
        if sun_elevation(lat, lon, t) >= min_sun: out.append(path)
    return out


def thumb_b64(im, pts):
    v = vlm_check.zone_view(im, pts, max_side=520); b = io.BytesIO(); v.save(b, 'JPEG', quality=80)
    return base64.b64encode(b.getvalue()).decode()


def write_review(rows, zones, root, path):
    cards = []
    for i, r in enumerate(rows):
        z = zones[r['preset']]
        try: im = Image.open(os.path.join(root, r['file'])).convert('RGB')
        except OSError: continue
        cards.append(f'<div class="c" data-i="{i}" data-file="{html.escape(r["file"])}" data-preset="{r["preset"]}" data-kimi="{r["verdict"]}">'
                     f'<img src="data:image/jpeg;base64,{thumb_b64(im, z["points"])}"><div class="m"><b>{r["preset"]}</b> {r["file"][-20:-4]}<br>'
                     f'Kimi: <b>{r["verdict"]}</b> ({float(r["confidence"]):.2f}) <i>{html.escape(r["note"])}</i></div>'
                     '<div class="b"><button data-v="cleared">1 убрано</button><button data-v="partial">2 частично</button>'
                     '<button data-v="not_cleared">3 не убрано</button><button data-v="unsure">4 не понятно</button></div></div>')
    page = """<!doctype html><meta charset="utf-8"><title>Lantern - check Kimi labels</title><style>
body{font:14px sans-serif;margin:10px;background:#f4f4f4}.top{position:sticky;top:0;background:#fff;padding:8px;border-bottom:1px solid #ccc;z-index:2}
.c{display:inline-block;width:540px;margin:6px;padding:8px;background:#fff;border:3px solid #fff;vertical-align:top}.c.cur{border-color:#2266dd}
.c img{width:520px}.m{margin:4px 0}.b button{margin-right:4px;padding:4px 8px}.b button.on{background:#2266dd;color:#fff}.c.chg{background:#fff3d6}
</style><div class="top">1 убрано · 2 частично · 3 не убрано · 4 не понятно · ←/→ листать.
Правило думы: убрано = расчищенная полоса ≥ 50% ширины и ≥ 1,5 м (укатанный снег можно); нетронутый снег со следами ног = не убрано; снег на газоне не считается.
<br><b id="st"></b> <button id="ex">Export CSV</button></div><div id="g">""" + ''.join(cards) + """</div><script>
const C=[...document.querySelectorAll('.c')];let cur=0;const key='lantern_kimi_review';let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
function val(c){return saved[c.dataset.file]||c.dataset.kimi}
function paint(c){const v=val(c);c.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v==v));c.classList.toggle('chg',v!=c.dataset.kimi)}
function stat(){let a=0,n=0;C.forEach(c=>{n++;if(val(c)==c.dataset.kimi)a++});document.getElementById('st').textContent=`${n} кадров · согласен с Kimi: ${a} (${Math.round(100*a/Math.max(1,n))}%) · исправлено: ${n-a}`}
function set(c,v){saved[c.dataset.file]=v;try{localStorage.setItem(key,JSON.stringify(saved))}catch(e){}paint(c);stat()}
function go(i){C[cur]&&C[cur].classList.remove('cur');cur=Math.max(0,Math.min(C.length-1,i));C[cur].classList.add('cur');C[cur].scrollIntoView({block:'center'})}
C.forEach((c,i)=>{paint(c);c.onclick=e=>{if(e.target.dataset.v){set(c,e.target.dataset.v)}go(i)}});stat();go(0);
document.onkeydown=e=>{const m={'1':'cleared','2':'partial','3':'not_cleared','4':'unsure'};if(m[e.key]){set(C[cur],m[e.key]);go(cur+1)}
if(e.key=='ArrowRight')go(cur+1);if(e.key=='ArrowLeft')go(cur-1)};
document.getElementById('ex').onclick=()=>{let s='file,preset,kimi,human\\n';C.forEach(c=>{s+=`${c.dataset.file},${c.dataset.preset},${c.dataset.kimi},${val(c)}\\n`});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([s],{type:'text/csv'}));a.download='labels_checked.csv';a.click()};
</script>"""
    with open(path, 'w', encoding='utf-8') as f: f.write(page)


def main():
    ap = argparse.ArgumentParser(description='Label harvested frames with the VLM and build a review page')
    ap.add_argument('--frames', required=True, help='folder from harvest_fintraffic.py')
    ap.add_argument('--zones', default=os.path.join('config', 'zones_hist.json'))
    ap.add_argument('--out', default='labels_kimi.csv')
    ap.add_argument('--review', default='review_kimi.html')
    ap.add_argument('--min-sun', type=float, default=-3)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--limit', type=int, default=0, help='label at most N new frames (0 = all)')
    a = ap.parse_args()
    if not os.getenv('NEBIUS_API_KEY'): sys.exit('NEBIUS_API_KEY is not set (put it in .env)')
    zones = json.load(open(a.zones, encoding='utf-8'))['zones']

    done = {}
    if os.path.exists(a.out):
        with open(a.out, newline='', encoding='utf-8') as f: done = {r['file']: r for r in csv.DictReader(f)}
    todo = []
    for pid, z in zones.items():
        for p in frames_for(a.frames, pid, z['lat'], z['lon'], a.min_sun):
            rel = os.path.relpath(p, a.frames)
            if rel not in done: todo.append((pid, rel))
    if a.limit: todo = todo[:a.limit]
    print(f'{len(done)} already labelled, {len(todo)} to label with {vlm_check.MODEL}', flush=True)

    lock = threading.Lock(); new = not os.path.exists(a.out)
    f = open(a.out, 'a', newline='', encoding='utf-8'); w = csv.writer(f)
    if new: w.writerow(['file', 'preset', 'zone_id', 'verdict', 'confidence', 'note']); f.flush()

    def job(item):
        pid, rel = item; z = zones[pid]
        try: im = Image.open(os.path.join(a.frames, rel)).convert('RGB')
        except OSError: return
        v = vlm_check.check_zone(im, z['points'], z.get('place_type', 'sidewalk'))
        row = [rel, pid, z['zone_id'], v['verdict'], f"{v['confidence']:.2f}", v['note'].replace('\n', ' ')]
        with lock:
            w.writerow(row); f.flush(); done[rel] = dict(zip(['file', 'preset', 'zone_id', 'verdict', 'confidence', 'note'], row))
            print(f'[{len(done)}] {rel}: {v["verdict"]} ({v["confidence"]:.2f}) {v["note"][:70]}', flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(job, t) for t in todo]
        while wait(futs, timeout=1).not_done: pass
    f.close()

    rows = [r for r in done.values() if r['preset'] in zones]
    counts = {}
    for r in rows: counts[r['verdict']] = counts.get(r['verdict'], 0) + 1
    print('verdicts:', counts)
    write_review(sorted(rows, key=lambda r: r['file']), zones, a.frames, a.review)
    print(f'review page: {os.path.abspath(a.review)} (open it, check, press Export CSV)')


if __name__ == '__main__':
    main()
