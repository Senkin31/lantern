"""Camera worker: takes camera frames, judges each sidewalk zone, sends signals to the Lantern app (POST /signals).

  live:    python camera_worker.py --config config/cameras.json --live --every 10
           (downloads the latest Fintraffic image of each camera every N minutes)
  replay:  python camera_worker.py --config config/cameras.json --replay <frames folder> --speed 2
           (plays saved frames in time order; --speed = real seconds between frames)

Sends a signal when a zone's verdict changes, and repeats 'snow' every --resend minutes of camera time.
Night / dark frames are skipped (not judged). Crops and frames are saved under media/ and served by service.py."""
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass
import argparse, collections, datetime as dt, glob, io, json, os, sys, time, urllib.request, uuid
from PIL import Image
from lantern_vision import SnowModel, decide, zone_crop
from privacy import PeopleBlur
import vlm_check, ice_risk

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_BASE = 'https://weathercam.digitraffic.fi'
UA = {'Digitraffic-User': 'Lantern/RobotHack2026', 'User-Agent': 'Lantern/RobotHack2026'}

def centroid(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]; return sum(ys) / len(ys), sum(xs) / len(xs)   # lat, lon

def post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r: return r.status

def sun_elevation(lat, lon, t: dt.datetime):
    """Approximate solar elevation in degrees (NOAA formula, ~0.5 deg accuracy). t must be UTC-aware."""
    import math
    d = t.timetuple().tm_yday; hr = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / 365 * (d - 1 + (hr - 12) / 24)
    decl = 0.006918 - 0.399912*math.cos(g) + 0.070257*math.sin(g) - 0.006758*math.cos(2*g) + 0.000907*math.sin(2*g) - 0.002697*math.cos(3*g) + 0.00148*math.sin(3*g)
    eqt = 229.18 * (0.000075 + 0.001868*math.cos(g) - 0.032077*math.sin(g) - 0.014615*math.cos(2*g) - 0.040849*math.sin(2*g))
    ha = math.radians((hr * 60 + eqt + 4 * lon) / 4 - 180); la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la)*math.sin(decl) + math.cos(la)*math.cos(decl)*math.cos(ha)))

class Worker:
    def __init__(s, a):
        s.a = a; s.model = SnowModel(); s.blur = None if a.no_blur else PeopleBlur(); s.state = {}; s.hist = collections.defaultdict(lambda: collections.deque(maxlen=a.smooth))
        cfg = json.load(open(a.config, encoding='utf-8'))
        s.cams = [c for c in cfg['cameras'] if c.get('district') != 'training' and c.get('active', True) and (not a.only or c['camera_id'] in a.only)]
        s.media = a.media; os.makedirs(os.path.join(s.media, 'crops'), exist_ok=True); os.makedirs(os.path.join(s.media, 'frames'), exist_ok=True)

    def handle(s, cam, im: Image.Image, frame_time: dt.datetime):
        zones = [dict(zone_id=z['zone_id'], points=z['points']) for z in cam['zones']]
        if tuple(im.size) != tuple(cam.get('image_size', im.size)): im = im.resize(tuple(cam['image_size']))
        stamp = frame_time.strftime('%Y%m%dT%H%M%SZ'); frame_name = None; safe = None
        el = sun_elevation(cam['lat'], cam['lon'], frame_time)
        risk = ice_risk.assess(cam['lat'], cam['lon'], frame_time) if s.a.ice else None
        icy = bool(risk) and risk['level'] in ('medium', 'high')
        if risk and risk['level'] != 'none': print(f'{stamp} {cam["camera_id"]}: ice risk {risk["level"]} ({"; ".join(risk["reasons"])})')
        night = el < s.a.min_sun   # dusk/night: street lights fool both models, so snow is not judged
        if night and not icy:
            print(f'{stamp} {cam["camera_id"]}: skipped (sun {el:.1f} deg < {s.a.min_sun})'); return
        results = ([dict(zone_id=z['zone_id'], judged=True, night=True) for z in cam['zones']] if night
                   else s.model.predict_frame(im, zones))
        for r, z in zip(results, cam['zones']):
            zid = r['zone_id']
            if not r['judged']: print(f'{stamp} {zid}: skipped ({r["reason"]})'); continue
            prev = s.state.get(zid)
            if night and prev and prev[2] not in ('cleared', 'possible_ice'): continue   # keep the daytime snow verdict
            if night:   # only the ice check runs at night; the snow verdict waits for daylight
                r.update(level='cleared', hazard_class='clear', confidence=0.5, blocked_share=0.0, p_not_cleared=None, p_snow=None)
            else:
                # smooth over the last frames + hysteresis, so one odd frame does not flip the verdict
                h = s.hist[zid]; h.append(r['p_not_cleared']); pn = sum(h) / len(h)
                r.update(decide(pn, s.model.heads['thresholds'], prev[2] if prev else None)); r['p_not_cleared'] = round(pn, 3)
                if (s.a.vlm and r['level'] != 'cleared') or s.a.vlm_all:   # second opinion: flagged zones, or every judged frame
                    v = vlm_check.check_zone(im, z['points'], cam.get('place_type', 'sidewalk')); r.update(vlm_check.fuse(r, v))
                    print(f'   VLM: {v["verdict"]} ({v["confidence"]:.2f}) {v["note"]}')
            if icy and r['level'] == 'cleared':   # cleared or not judged, but ice is likely: ask for gritting
                r.update(level='possible_ice', hazard_class='possible_ice', blocked_share=0.0,
                         confidence=0.75 if risk['level'] == 'high' else 0.55)
            due = prev is None or prev[2] != r['level'] or (
                r['hazard_class'] in ('snow', 'possible_ice') and (frame_time - prev[1]).total_seconds() >= s.a.resend * 60)
            print(f'{stamp} {zid}: {r["hazard_class"]}/{r["level"]} conf={r["confidence"]} p_not_cleared={r["p_not_cleared"]} p_snow={r["p_snow"]}' + ('  -> send' if due else ''))
            if not due: continue
            if frame_name is None:
                frame_name = f'frames/{cam["camera_id"]}_{stamp}.jpg'; im.save(os.path.join(s.media, frame_name), quality=85)
            if safe is None:                 # the contractor's crop: people blurred; the inspector keeps the original frame
                safe = im if s.blur is None else s.blur.blur(im)[0]
            crop_name = f'crops/{zid.replace(":", "_")}_{stamp}.jpg'; zone_crop(safe, z['points']).save(os.path.join(s.media, crop_name), quality=88)
            lat, lon = centroid(z['map_polygon']) if z.get('map_polygon') else (cam['lat'], cam['lon'])
            ts = dt.datetime.now(dt.timezone.utc) if s.a.stamp == 'now' else frame_time
            body = dict(source='camera', camera_id=cam['camera_id'], zone_id=zid, lat=round(lat, 6), lon=round(lon, 6),
                        timestamp=ts.strftime('%Y-%m-%dT%H:%M:%SZ'), hazard_class=r['hazard_class'], blocked_share=r['blocked_share'],
                        confidence=r['confidence'], frame_url=f'{s.a.media_url}/{frame_name}', crop_url=f'{s.a.media_url}/{crop_name}')
            if s.a.dry_run: print('   DRY', json.dumps(body))
            else:
                try: print('   POST /signals ->', post_json(s.a.url.rstrip('/') + '/signals', body))
                except Exception as e: print('   POST failed:', e)
            s.state[zid] = (r['hazard_class'], frame_time, r['level'])

    def live(s):
        while True:
            for cam in s.cams:
                try:
                    req = urllib.request.Request(f'{IMG_BASE}/{cam["camera_id"]}.jpg', headers=UA)
                    with urllib.request.urlopen(req, timeout=30) as r: data = r.read()
                    s.handle(cam, Image.open(io.BytesIO(data)).convert('RGB'), dt.datetime.now(dt.timezone.utc))
                except Exception as e: print(cam['camera_id'], 'error:', e)
            time.sleep(s.a.every * 60)

    def replay(s):
        items = []
        for cam in s.cams:
            for f in glob.glob(os.path.join(s.a.replay, cam['camera_id'], '*.jpg')):
                try: t = dt.datetime.strptime(os.path.basename(f)[:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc)
                except ValueError: continue
                if s.a.since and t < s.a.since: continue
                items.append((t, cam, f))
        items.sort(key=lambda x: x[0]); print(f'{len(items)} frames to replay')
        for t, cam, f in items:
            s.handle(cam, Image.open(f).convert('RGB'), t); time.sleep(s.a.speed)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', default=os.path.join(HERE, 'config', 'cameras.json'))
    p.add_argument('--url', default=os.getenv('APP_URL', 'http://localhost:8000'))
    p.add_argument('--media', default=os.getenv('LANTERN_MEDIA', os.path.join(HERE, 'media')))
    p.add_argument('--media-url', default=os.getenv('MEDIA_URL', 'http://localhost:8001/media'))
    g = p.add_mutually_exclusive_group(required=True); g.add_argument('--live', action='store_true'); g.add_argument('--replay')
    p.add_argument('--every', type=float, default=10, help='live: minutes between rounds')
    p.add_argument('--speed', type=float, default=1, help='replay: real seconds between frames')
    p.add_argument('--since', type=lambda x: dt.datetime.fromisoformat(x).replace(tzinfo=dt.timezone.utc), help='replay: start time, e.g. 2026-11-24T06:00')
    p.add_argument('--resend', type=float, default=30, help='minutes of camera time before repeating a snow signal')
    p.add_argument('--stamp', choices=['frame', 'now'], default=None, help='signal timestamp: camera time or now (default: frame for live, now for replay)')
    p.add_argument('--smooth', type=int, default=3, help='frames to average per zone')
    p.add_argument('--only', nargs='*', help='camera ids')
    p.add_argument('--vlm', action='store_true', help='ask the VLM (NEBIUS_API_KEY in .env) about every flagged zone before sending')
    p.add_argument('--vlm-all', action='store_true', help='ask the VLM about every judged zone frame (~200 requests/day for 4 cameras)')
    p.add_argument('--min-sun', type=float, default=-3, help='skip frames when the sun is lower than this (degrees); -3 = end of civil dusk')
    p.add_argument('--ice', action='store_true', help='weather-based ice risk (Open-Meteo): a cleared zone under ice risk is sent as possible_ice, also at night')
    p.add_argument('--no-blur', action='store_true', help='do not blur people on contractor crops')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(); a.stamp = a.stamp or ('frame' if a.live else 'now')
    w = Worker(a); w.live() if a.live else w.replay()
