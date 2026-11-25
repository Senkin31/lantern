"""One-command demo: reset the app, set time compression, replay mock/ through send_signals.py
and point the clearing deadline at the replay's snowfall end.

    python -m app.demo                    # 1 scenario hour = 6 s (whole day ~1.5 min)
    python -m app.demo --speed 3          # faster
    python -m app.demo --auto-done        # also press the contractor's "Cleared" at ~13:30 (no UI needed)

The app must already be running (uvicorn app.main:app --host 127.0.0.1 --port 8000).
"""
import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .config import ROOT


def call(url, method, path, body=None):
    req = urllib.request.Request(url + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--speed", type=float, default=6.0, help="real seconds per scenario hour")
    ap.add_argument("--auto-done", action="store_true", help="contractor A presses 'Cleared' at ~13:30")
    ap.add_argument("--keep", action="store_true", help="don't reset existing alerts")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    script = ROOT / "mock" / "send_signals.py"
    if not script.is_file():
        sys.exit("mock/send_signals.py not found: unzip lantern_mock.zip into the repo root")
    try:
        if not a.keep:
            call(url, "POST", "/admin/reset")
        call(url, "POST", "/settings", {"hour_seconds": a.speed})
    except urllib.error.URLError as exc:
        sys.exit(f"Lantern app not reachable at {url}: {exc}")

    start = time.time()
    # -u: unbuffered, otherwise the SNOWFALL_END line only arrives when the replay is over
    proc = subprocess.Popen([sys.executable, "-u", str(script), "--url", url, "--speed", str(a.speed)],
                            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    first = proc.stdout.readline()
    second = proc.stdout.readline()
    print(first.rstrip())
    snow_end = second.split("SNOWFALL_END=")[1].split()[0]
    rt = call(url, "POST", "/settings", {"snowfall_end": snow_end})
    print(f"Snowfall ended {snow_end}; clearing deadline {rt['deadline']} "
          f"(= {rt['clearing_hours']:g} scenario hours, 1 h = {rt['hour_seconds']:g} s)")
    print(f"Open {url}/inspector and {url}/contractor?contractor=A")

    if a.auto_done:
        def press():
            time.sleep(9.0 * a.speed)  # first event 04:30 -> 13:30
            for al in call(url, "GET", "/alerts?role=contractor&contractor=A")["alerts"]:
                if al["zone_id"] == "mock_cam_1:crossing" and al["status"] in ("open", "reopened"):
                    call(url, "POST", f"/alerts/{al['id']}/status",
                         {"status": "done_reported", "role": "contractor", "contractor": "A", "actor": "demo"})
                    print(f"[13:30] contractor A pressed 'Cleared' on alert {al['id']}")
        threading.Thread(target=press, daemon=True).start()
    else:
        print("At ~13:30 scenario time press 'Cleared' on the crossing in the contractor screen.")

    for line in proc.stdout:
        print(line.rstrip())
    proc.wait()
    print(f"Replay finished in {time.time() - start:.0f} s.")


if __name__ == "__main__":
    main()
