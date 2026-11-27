"""
Lantern: weather-based ice risk ("check the gritting here").

Ice is invisible on a camera frame, so Lantern does not try to see it. It uses the weather instead:
the council requires slippery sections to be gritted, and black ice forms in a few known situations.
For each camera we read hourly weather from Open-Meteo (free, no key; https://open-meteo.com, CC BY 4.0)
and flag the risk:

  high   - freezing rain or drizzle in the last 6 h / next 3 h
  high   - thaw then frost: air was >= +1 C in the last 12 h and drops to <= 0 C (air or ground) within 3 h back / 6 h ahead
           (meltwater and cleared-but-wet sidewalks refreeze)
  medium - precipitation >= 0.3 mm in the last 12 h and the ground is at or below 0 C now or in the next 6 h
  medium - humid frost: air <= 0 C, dew point within 1 C of the air temperature and ground <= 0 C (hoar frost)

camera_worker.py --ice uses this: when a zone looks cleared but the ice risk is medium/high, the signal is
'possible_ice' instead of 'clear' (a cleared, wet sidewalk is exactly where ice forms), with the frame as evidence.

  py ice_risk.py                       # risk now for every active camera in config/cameras.json
  py ice_risk.py --at 2026-11-24T07:00 # risk at a past time (up to ~90 days back)
"""
import argparse, datetime as dt, json, os, threading, time, urllib.request

API = 'https://api.open-meteo.com/v1/forecast'
HOURLY = 'temperature_2m,dew_point_2m,precipitation,rain,snowfall,soil_temperature_0cm,weather_code'
FREEZING_CODES = {56, 57, 66, 67}   # WMO: freezing drizzle / freezing rain
_cache, _lock = {}, threading.Lock()
CACHE_S = 1800


def fetch(lat, lon, at):
    """Hourly weather around `at` (UTC). Cached per place and hour block for 30 min."""
    past = max(1, min(92, (dt.datetime.now(dt.timezone.utc) - at).days + 2))
    key = (round(lat, 2), round(lon, 2), past)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_S: return hit[1]
    url = f'{API}?latitude={lat:.4f}&longitude={lon:.4f}&hourly={HOURLY}&past_days={past}&forecast_days=2&timezone=UTC'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Lantern/RobotHack2026'}), timeout=15) as r:
        data = json.loads(r.read().decode('utf-8'))
    with _lock: _cache[key] = (time.time(), data)
    return data


def evaluate(hourly, at):
    """Pure rule check on an Open-Meteo 'hourly' block. Returns dict(level, reasons, air_c, ground_c)."""
    times = [dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc) for t in hourly['time']]
    t0 = at.replace(minute=0, second=0, microsecond=0)
    if t0 not in times: return dict(level='unknown', reasons=['no weather for this hour'], air_c=None, ground_c=None)
    i0 = times.index(t0)
    def win(name, a, b):   # values from hour i0+a to i0+b inclusive, None dropped
        v = hourly.get(name) or []
        return [x for x in v[max(0, i0 + a): i0 + b + 1] if x is not None]
    T, D, G = (hourly['temperature_2m'][i0], hourly['dew_point_2m'][i0], (hourly.get('soil_temperature_0cm') or [None] * len(times))[i0])
    reasons, level = [], 'none'
    def up(lv):
        nonlocal level
        if ['none', 'medium', 'high'].index(lv) > ['none', 'medium', 'high'].index(level): level = lv
    if FREEZING_CODES & set(win('weather_code', -6, 3)):
        up('high'); reasons.append('freezing rain or drizzle')
    cold = win('temperature_2m', -3, 6) + win('soil_temperature_0cm', -3, 6)
    if win('temperature_2m', -12, 0) and max(win('temperature_2m', -12, 0)) >= 1 and cold and min(cold) <= 0:
        up('high'); reasons.append(f"thaw then frost: up to {max(win('temperature_2m', -12, 0)):+.0f} C in the last 12 h, down to {min(cold):+.0f} C")
    ground_next = win('soil_temperature_0cm', 0, 6) or win('temperature_2m', 0, 6)
    if sum(win('precipitation', -12, 0)) >= 0.3 and ground_next and min(ground_next) <= 0:
        up('medium'); reasons.append(f"{sum(win('precipitation', -12, 0)):.1f} mm precipitation in 12 h, ground {min(ground_next):+.0f} C")
    if T is not None and D is not None and T <= 0 and T - D <= 1 and (G if G is not None else T) <= 0:
        up('medium'); reasons.append(f'humid frost: air {T:+.0f} C, dew point {D:+.0f} C')
    return dict(level=level, reasons=reasons, air_c=T, ground_c=G)


def assess(lat, lon, at=None):
    at = (at or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    try:
        return evaluate(fetch(lat, lon, at)['hourly'], at)
    except Exception as e:   # no network / API change: never block the camera pipeline
        return dict(level='unknown', reasons=[f'weather unavailable: {type(e).__name__}'], air_c=None, ground_c=None)


def main():
    ap = argparse.ArgumentParser(description='Weather-based ice risk per camera')
    ap.add_argument('--config', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'cameras.json'))
    ap.add_argument('--at', help='UTC time, e.g. 2026-11-24T07:00 (default: now)')
    a = ap.parse_args()
    at = dt.datetime.fromisoformat(a.at).replace(tzinfo=dt.timezone.utc) if a.at else None
    for cam in json.load(open(a.config, encoding='utf-8'))['cameras']:
        if cam.get('active') is False or cam.get('district') == 'training': continue
        r = assess(cam['lat'], cam['lon'], at)
        print(f"{cam['camera_id']:10} {cam.get('name', '')[:34]:34} {r['level']:7} air {r['air_c']} ground {r['ground_c']}  {'; '.join(r['reasons'])}")
    print('Weather: Open-Meteo (open-meteo.com), CC BY 4.0')


if __name__ == '__main__':
    main()
