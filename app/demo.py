"""One-command demo of the 25.11 day from brief v3 (deadlines 08:00 / 22:00 Riga time).

    python -m app.demo                 # 1 scenario hour = 6 s, the day takes ~1.5 min
    python -m app.demo --speed 3       # faster (3 s per scenario hour)
    python -m app.demo --auto-done     # contractor A presses "Cleared" at 11:30 by itself (no UI needed)

The app must already be running (uvicorn app.main:app --host 127.0.0.1 --port 8000).

If mock/signals.json is Nikita's v3 file (it has "snowfalls"), his mock/send_signals.py runs
the replay: it sets POST /demo/clock and POST /snowfalls itself. Otherwise the built-in copy
of the brief's timeline below is replayed, using the frames and photos that are in mock/.
Times in the timeline are Riga time on 25.11.2026 (UTC+2).
"""
import argparse
import json
import mimetypes
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from .config import ROOT

MOCK = ROOT / "mock"
DAY = "2026-11-25"
CROSSING, SQUARE, SIDEWALK = "mock_cam_1:crossing", "mock_cam_2:square", "mock_cam_2:sidewalk"
CAMS = {"mock_cam_1": (56.9498, 24.1052), "mock_cam_2": (56.9549, 24.1180)}

# (Riga time, kind, payload) -- brief v3, "Моки v3 и сценарий демо"
TIMELINE = [
    ("07:00", "snowfall", {"start": "2026-11-24T23:00", "end": "2026-11-25T03:00",
                           "_note": "snowfall 1 ended 03:00 -> deadline 08:00"}),
    ("09:00", "signal", (CROSSING, "blocked", 0.82, 0.86, "20261125T0800Z", "wall of snow on the crossing -> open, act, Contractor A")),
    ("09:00", "signal", (SQUARE, "snow", 0.40, 0.80, "20261125T1500Z", "partly cleared -> open, notice, Contractor B")),
    ("09:00", "signal", (SIDEWALK, "clear", 0.05, 0.90, "20261125T1000Z", "clean -> no alert")),
    ("09:40", "report", ("dev-crossing-1", 56.94982, 24.10525, "no", "crossing", "report_snow_1.jpg", "impassable at the crossing -> joins, high")),
    ("10:15", "report", ("dev-stop-1", 56.9581, 24.1265, "no", "stop", "report_stop.jpg", "bus stop without a camera -> new alert, max medium")),
    ("11:00", "report", ("dev-cat-1", 56.952, 24.11, "no", "other", "report_irrelevant.jpg", "off-topic photo -> /analyze reject")),
    ("11:30", "done", ("A", CROSSING, "contractor A presses 'Cleared' on the crossing (UI)")),
    ("11:50", "report", ("dev-crossing-2", 56.94978, 24.10512, "partly", "crossing", "report_snow_2.jpg", "second phone at the crossing -> +1 confirmation")),
    ("12:00", "signal", (CROSSING, "snow", 0.70, 0.82, "20261125T1430Z", "snow still there after 'done' -> reopened")),
    ("13:30", "signal", (SQUARE, "clear", 0.05, 0.90, "20261125T1800Z", "clean, nobody pressed 'done' -> verified")),
    ("14:00", "snowfall", {"start": "2026-11-25T13:00", "end": "2026-11-25T14:00",
                           "_note": "snowfall 2 ended 14:00 -> deadline 22:00"}),
    ("14:00", "signal", (CROSSING, "clear", 0.03, 0.91, "20261125T1700Z", "clean -> verified, response 5 h")),
    ("14:30", "signal", (SIDEWALK, "snow", 0.40, 0.80, "20261125T0700Z", "snow after snowfall 2 -> watch (deadline 22:00)")),
    ("15:30", "signal", (SIDEWALK, "clear", 0.02, 0.90, "20261125T1000Z", "clean before 22:00 -> cleared_in_time")),
]


def riga(hhmm: str, day: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00+02:00").astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def call(url, method, path, body=None):
    req = urllib.request.Request(url + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_report(url, fields, photo):
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in fields.items()]
    ctype = mimetypes.guess_type(photo.name)[0] or "image/jpeg"
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{photo.name}"\r\n'
                 f'Content-Type: {ctype}\r\n\r\n'.encode() + photo.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(url + "/reports", data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]


def press_done(url, contractor, zone):
    for al in call(url, "GET", f"/alerts?role=contractor&contractor={contractor}")["alerts"]:
        if al["zone_id"] == zone and al["status"] in ("open", "reopened"):
            call(url, "POST", f"/alerts/{al['id']}/status",
                 {"status": "done_reported", "role": "contractor", "contractor": contractor, "actor": "demo"})
            return al["id"]
    return None


def builtin(url: str, speed: float, auto_done: bool, keep_fast: bool = False) -> None:
    factor = 3600.0 / speed
    start = riga(TIMELINE[0][0])
    real0 = time.time()
    rt = call(url, "POST", "/demo/clock", {"scenario_start": iso(start), "factor": factor})
    print(f"Demo clock: {DAY} 07:00 Riga, 1 h = {speed:g} s (factor {factor:g}) -> {rt['clock']['now']}")
    print(f"Open {url}/inspector and {url}/contractor?contractor=A\n")
    for hhmm, kind, payload in TIMELINE:
        when = riga(hhmm)
        wait = (when - start).total_seconds() / factor - (time.time() - real0)
        if wait > 0:
            time.sleep(wait)
        tag = f"[{hhmm} Riga]"
        if kind == "snowfall":
            body = {"start": iso(riga(payload["start"][11:], payload["start"][:10])),
                    "end": iso(riga(payload["end"][11:], payload["end"][:10])), "source": "demo"}
            r = call(url, "POST", "/snowfalls", body)
            print(f"{tag} snowfall {payload['start'][11:]}-{payload['end'][11:]} -> deadline {r['deadline_at']}  # {payload['_note']}")
        elif kind == "signal":
            zone, cls, share, conf, frame, note = payload
            cam, label = zone.split(":")
            lat, lon = CAMS[cam]
            crop = next(iter(sorted((MOCK / "crops" / cam).glob(f"{frame}_*.jpg"))), None) if (MOCK / "crops" / cam).is_dir() else None
            body = {"source": "camera", "camera_id": cam, "zone_id": zone, "lat": lat, "lon": lon,
                    "timestamp": iso(when), "hazard_class": cls, "blocked_share": share, "confidence": conf,
                    "frame_url": f"/static/frames/{cam}/{frame}.jpg",
                    "crop_url": f"/static/crops/{cam}/{crop.name}" if crop else f"/static/frames/{cam}/{frame}.jpg"}
            r = call(url, "POST", "/signals", body)
            print(f"{tag} signal {zone:20} {cls:8} share={share:.2f} conf={conf:.2f} -> alert {r['alert_id']}  # {note}")
        elif kind == "report":
            device, lat, lon, passable, place, photo, note = payload
            path = MOCK / "photos" / photo
            if not path.is_file():
                print(f"{tag} report skipped: {path} missing")
                continue
            status, r = post_report(url, {"lat": lat, "lon": lon, "passable": passable, "place_type": place,
                                          "device_id": device, "timestamp": iso(when), "channel": "replay"}, path)
            info = f"{r.get('relevant')} alert {r.get('alert_id')}" if isinstance(r, dict) else r
            print(f"{tag} report {device:15} {passable:6} {place:9} -> {status} {info}  # {note}")
        elif kind == "done":
            contractor, zone, note = payload
            if auto_done:
                print(f"{tag} done -> alert {press_done(url, contractor, zone)}  # {note}")
            else:
                print(f"{tag} >>> NOW: open {url}/contractor?contractor={contractor} and press 'Cleared' on the crossing <<<")
    if keep_fast:
        print(f"\nReplay finished in {time.time() - real0:.0f} s. The clock keeps running at x{factor:g} "
              f"(open alerts turn overdue in ~{24 * speed:.0f} s).")
    else:  # freeze the stage: same scenario time, normal speed
        now = call(url, "GET", "/demo/clock")["now"]
        call(url, "POST", "/demo/clock", {"scenario_start": now, "factor": 1})
        print(f"\nReplay finished in {time.time() - real0:.0f} s. The demo clock now runs at normal speed from "
              f"{now} (use --keep-fast to keep it racing, e.g. to show 'overdue').")


def nikita_v3(url: str, speed: float, auto_done: bool, keep_fast: bool = False) -> None:
    script = MOCK / "send_signals.py"
    print(f"Running {script} (v3 mocks: it sets the demo clock and snowfalls itself)")
    proc = subprocess.Popen([sys.executable, "-u", str(script), "--url", url, "--speed", str(speed)],
                            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if auto_done:
        def press():  # wait for 11:30 Riga on the server clock, then press "Cleared" on the crossing
            target = riga("11:30")
            while proc.poll() is None:
                now = datetime.fromisoformat(call(url, "GET", "/demo/clock")["now"].replace("Z", "+00:00"))
                if now >= target:
                    print(f"[11:30 Riga] auto-done -> alert {press_done(url, 'A', CROSSING)}")
                    return
                time.sleep(0.3)
        threading.Thread(target=press, daemon=True).start()
    for line in proc.stdout:
        print(line.rstrip())
    proc.wait()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--speed", type=float, default=6.0, help="real seconds per scenario hour")
    ap.add_argument("--auto-done", action="store_true", help="contractor A presses 'Cleared' at 11:30 Riga")
    ap.add_argument("--keep", action="store_true", help="don't reset existing alerts")
    ap.add_argument("--builtin", action="store_true", help="use the built-in timeline even if v3 mocks exist")
    ap.add_argument("--keep-fast", action="store_true", help="keep the demo clock fast after the replay")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    try:
        if not a.keep:
            call(url, "POST", "/admin/reset")
    except urllib.error.URLError as exc:
        sys.exit(f"Lantern app not reachable at {url}: {exc}")
    v3 = False
    sig = MOCK / "signals.json"
    if sig.is_file() and not a.builtin:
        try:
            v3 = "snowfalls" in json.loads(sig.read_text(encoding="utf-8")).get("scenario", {})
        except (ValueError, AttributeError):
            v3 = False
    (nikita_v3 if v3 else builtin)(url, a.speed, a.auto_done, a.keep_fast)


if __name__ == "__main__":
    main()
