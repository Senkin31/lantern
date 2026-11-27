#!/usr/bin/env python3
"""
Lantern: bulk harvest of Fintraffic weather-camera history for training data.

Fintraffic keeps only the last 24 hours of camera images. This script:
  1. downloads the list of all weather cameras (stations + presets);
  2. picks up to --max-presets presets in the snowy north (lat >= --min-lat),
     one preset per station by default, spread evenly over latitude;
  3. downloads each preset's 24-hour history, daylight frames only
     (sun higher than --min-sun degrees at the camera, same rule as camera_worker);
  4. writes <out>/<PRESET>/<UTC>.jpg, <out>/manifest.csv (same format as collect_fintraffic.py),
     <out>/presets.csv (name, lat, lon) and <out>/contact_sheet.html (one frame per camera, to pick sidewalk cameras).

Re-running is safe: frames already in manifest.csv are skipped. Running it again tomorrow adds the next 24 hours.
Standard library only, Python 3.8+.

Examples:
  py harvest_fintraffic.py --plan                              # show which cameras would be used, download nothing
  py harvest_fintraffic.py --out <folder>
  py harvest_fintraffic.py --max-presets 150 --min-lat 63      # more cameras, further north

Data: Fintraffic / digitraffic.fi, licence CC BY 4.0. Do not commit the images to the public repo.
"""
import argparse, csv, gzip, hashlib, json, math, os, random, re, signal, sys, threading, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone

API_BASE = os.environ.get('LANTERN_FT_API', 'https://tie.digitraffic.fi/api/weathercam/v1')
HEADERS = {'Digitraffic-User': 'Lantern/RobotHack2026', 'User-Agent': 'Lantern/RobotHack2026', 'Accept-Encoding': 'gzip'}
_stop = threading.Event()
_lock = threading.Lock()


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url, accept=None, timeout=30):
    """GET with gzip and polite retry on 429 / network errors. Returns (status, body) or (None, b'')."""
    h = dict(HEADERS)
    if accept: h['Accept'] = accept
    for attempt in range(4):
        if _stop.is_set(): return None, b''
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read()
                if (r.headers.get('Content-Encoding') or '').lower() == 'gzip': body = gzip.decompress(body)
                return r.status, body
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get('Retry-After') or 60)
                log(f'429 too many requests, waiting {wait} s'); _stop.wait(wait); continue
            if e.code in (500, 502, 503, 504): _stop.wait(5 * (attempt + 1)); continue
            return e.code, b''
        except Exception as e:   # URLError, timeout, reset
            log(f'network: {e} ({url}), try {attempt + 1}/4'); _stop.wait(5 * (attempt + 1))
    return None, b''


def sun_elevation(lat, lon, t):
    """Approximate solar elevation in degrees (NOAA formula). t is UTC-aware."""
    d = t.timetuple().tm_yday; hr = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / 365 * (d - 1 + (hr - 12) / 24)
    decl = 0.006918 - 0.399912*math.cos(g) + 0.070257*math.sin(g) - 0.006758*math.cos(2*g) + 0.000907*math.sin(2*g) - 0.002697*math.cos(3*g) + 0.00148*math.sin(3*g)
    eqt = 229.18 * (0.000075 + 0.001868*math.cos(g) - 0.032077*math.sin(g) - 0.014615*math.cos(2*g) - 0.040849*math.sin(2*g))
    ha = math.radians((hr * 60 + eqt + 4 * lon) / 4 - 180); la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la)*math.sin(decl) + math.cos(la)*math.cos(decl)*math.cos(ha)))


def parse_time(s):
    try: return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (AttributeError, ValueError): return None


def list_presets(min_lat, max_lat):
    """All presets in collection, with station name and coordinates."""
    st, body = http_get(f'{API_BASE}/stations', 'application/json')
    if st != 200: sys.exit(f'Could not get the camera list (HTTP {st})')
    out = []
    for f in json.loads(body.decode('utf-8')).get('features', []):
        p = f.get('properties', {}); c = (f.get('geometry') or {}).get('coordinates') or [None, None]
        lon, lat = c[0], c[1]
        if lat is None or not (min_lat <= lat <= max_lat): continue
        if p.get('collectionStatus', 'GATHERING') != 'GATHERING': continue
        presets = [q['id'] for q in p.get('presets', []) if q.get('inCollection', True) and q.get('id')]
        if presets: out.append(dict(station=p.get('id'), name=p.get('name', ''), lat=lat, lon=lon, presets=presets))
    return out


def choose(stations, max_presets, per_station, seed):
    """Spread over latitude: sort by lat, take evenly spaced stations, then per_station presets each."""
    rnd = random.Random(seed); stations = sorted(stations, key=lambda s: s['lat'])
    n_st = min(len(stations), max(1, max_presets // per_station))
    step = len(stations) / n_st if n_st else 1
    picked = [stations[int(i * step)] for i in range(n_st)]
    res = []
    for s in picked:
        ps = s['presets'][:]; rnd.shuffle(ps)
        for pid in sorted(ps[:per_station]):
            res.append(dict(preset=pid, station=s['station'], name=s['name'], lat=s['lat'], lon=s['lon']))
    return res[:max_presets]


def walk_history(obj, found):
    """Find {image url, time} pairs anywhere in the history JSON (format not fixed on purpose)."""
    if isinstance(obj, dict):
        url = next((v for v in obj.values() if isinstance(v, str) and re.search(r'\.jpe?g(\?|$)', v)), None)
        if url:
            when = next((v for k, v in obj.items() if isinstance(v, str) and re.search(r'time|modified|date', k, re.I)), None)
            found.append((url, when))
        for v in obj.values(): walk_history(v, found)
    elif isinstance(obj, list):
        for v in obj: walk_history(v, found)


def history(preset):
    st, body = http_get(f'{API_BASE}/stations/{preset}/history', 'application/json')
    if st != 200 or not body: return []
    try: data = json.loads(body.decode('utf-8'))
    except ValueError: return []
    found, seen, items = [], set(), []
    walk_history(data, found)
    for url, when in found:
        t = parse_time(when) if when else None
        if preset in url and url not in seen and t: seen.add(url); items.append((url, t))
    return items


class Store:
    def __init__(s, out):
        s.out = out; os.makedirs(out, exist_ok=True); s.manifest = os.path.join(out, 'manifest.csv'); s.seen = set(); s.stamps = set()
        if os.path.exists(s.manifest):
            with open(s.manifest, newline='', encoding='utf-8') as f:
                for r in csv.DictReader(f): s.seen.add((r['preset'], r['sha1'])); s.stamps.add((r['preset'], r['time_utc']))
        else:
            with open(s.manifest, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['preset', 'time_utc', 'file', 'source', 'bytes', 'sha1'])

    def have(s, preset, stamp): return (preset, stamp) in s.stamps

    def save(s, preset, stamp, data):
        if not data or data[:2] != b'\xff\xd8': return False
        sha = hashlib.sha1(data).hexdigest()
        with _lock:
            if (preset, sha) in s.seen: return False
            folder = os.path.join(s.out, preset); os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f'{stamp}.jpg')
            with open(path, 'wb') as f: f.write(data)
            with open(s.manifest, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([preset, stamp, os.path.relpath(path, s.out), 'history', len(data), sha])
            s.seen.add((preset, sha)); s.stamps.add((preset, stamp))
        return True


def write_meta(out, chosen, store):
    path = os.path.join(out, 'presets.csv'); old = {}
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f: old = {r['preset']: r for r in csv.DictReader(f)}
    for c in chosen: old[c['preset']] = {k: c[k] for k in ('preset', 'station', 'name', 'lat', 'lon')}
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['preset', 'station', 'name', 'lat', 'lon']); w.writeheader(); w.writerows(old.values())
    # contact sheet: the middle saved frame of each camera, to pick the ones that show a sidewalk or footpath
    rows = []
    for pid, meta in sorted(old.items(), key=lambda kv: -float(kv[1]['lat'])):
        folder = os.path.join(out, pid)
        files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        if not files: continue
        rows.append(f'<figure><img loading="lazy" src="{pid}/{files[len(files)//2]}"><figcaption><b>{pid}</b> {meta["name"]} '
                    f'({float(meta["lat"]):.2f}) &middot; {len(files)} frames</figcaption></figure>')
    with open(os.path.join(out, 'contact_sheet.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>Fintraffic cameras</title><style>body{font:13px sans-serif;margin:12px}'
                'figure{display:inline-block;width:320px;margin:4px;vertical-align:top}img{width:320px}</style>'
                f'<h3>{len(rows)} cameras &middot; Fintraffic, CC BY 4.0</h3>' + ''.join(rows))


def main():
    ap = argparse.ArgumentParser(description='Harvest 24 h of Fintraffic camera history for training data')
    ap.add_argument('--out', default=os.path.join('data', 'fintraffic_hist'))
    ap.add_argument('--max-presets', type=int, default=100)
    ap.add_argument('--per-station', type=int, default=1, help='presets per station (1 = most camera variety)')
    ap.add_argument('--min-lat', type=float, default=61.5, help='only cameras north of this (snow)')
    ap.add_argument('--max-lat', type=float, default=71)
    ap.add_argument('--presets', nargs='+', help='use exactly these presets instead of choosing')
    ap.add_argument('--min-sun', type=float, default=-3, help='skip frames when the sun is lower (degrees); -90 = keep all')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--pause', type=float, default=1.0, help='seconds each worker waits between image requests')
    ap.add_argument('--seed', type=int, default=26)
    ap.add_argument('--plan', action='store_true', help='only list the chosen cameras')
    a = ap.parse_args()
    signal.signal(signal.SIGINT, lambda *_: (_stop.set(), log('stopping after current downloads...')))

    stations = list_presets(-90 if a.presets else a.min_lat, 90 if a.presets else a.max_lat)
    if a.presets:
        idx = {p: s for s in stations for p in s['presets']}
        chosen = [dict(preset=p, station=idx[p]['station'], name=idx[p]['name'], lat=idx[p]['lat'], lon=idx[p]['lon']) for p in a.presets if p in idx]
        missing = [p for p in a.presets if p not in idx]
        if missing: log(f'not in collection, skipped: {" ".join(missing)}')
    else:
        chosen = choose(stations, a.max_presets, a.per_station, a.seed)
    log(f'{len(stations)} stations in range, using {len(chosen)} presets')
    if a.plan:
        for c in chosen: print(f"{c['preset']}  {c['lat']:.3f} {c['lon']:.3f}  {c['name']}")
        return

    store = Store(a.out); write_meta(a.out, chosen, store)
    jobs, skipped_dark = [], 0
    for i, c in enumerate(chosen, 1):
        if _stop.is_set(): break
        items = history(c['preset']); keep = 0
        for url, t in items:
            stamp = t.strftime('%Y%m%dT%H%M%SZ')
            if store.have(c['preset'], stamp): continue
            if sun_elevation(c['lat'], c['lon'], t) < a.min_sun: skipped_dark += 1; continue
            jobs.append((c['preset'], stamp, url)); keep += 1
        log(f"[{i}/{len(chosen)}] {c['preset']} {c['name'][:40]}: {len(items)} in history, {keep} new daylight frames")
        time.sleep(0.3)
    log(f'{len(jobs)} frames to download ({skipped_dark} dark ones skipped), ~{len(jobs) * a.pause / max(1, a.workers) / 60:.0f} min')

    done = [0, 0]
    def get(job):
        if _stop.is_set(): return
        pid, stamp, url = job; st, body = http_get(url)
        ok = st == 200 and store.save(pid, stamp, body)
        with _lock:
            done[0] += 1; done[1] += ok
            if done[0] % 100 == 0: log(f'{done[0]}/{len(jobs)} downloaded, {done[1]} saved')
        _stop.wait(a.pause)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(get, j) for j in jobs]
        while wait(futs, timeout=1).not_done: pass   # short waits so Ctrl+C works on Windows
    write_meta(a.out, chosen, store)
    log(f'done: {done[1]} new frames saved in {os.path.abspath(a.out)}; open contact_sheet.html to pick sidewalk cameras')


if __name__ == '__main__':
    main()
