"""Lantern app: backend + inspector, contractor and resident screens (port 8000).

Run from the repo root:  uvicorn app.main:app --port 8000
"""
import asyncio
import contextlib
import gzip
import hashlib
import json
import secrets
from pathlib import Path
from urllib.parse import quote
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analyze as analyze_mod
from . import auth
from . import evidence as evidence_mod
from . import tgapp
from .config import settings
from .db import Database
from .engine import LOCATION_SOURCES, PASSABLE, PLACE_TYPES, REPORT_HAZARDS, Engine, RuleError
from .registry import Registry, haversine_m
from .segments import Sidewalks
from .spam import SpamGuard, photo_hashes
from .timeutil import clock, fmt_ts, parse_ts
from .views import Views

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic",
               "image/heif": ".heif"}
DEVICE_COOKIE = "lantern_device"


def build_app(db_path: Optional[Path] = None, start_ticker: bool = True) -> FastAPI:
    db = Database(db_path or settings.db_path)
    registry = Registry(settings.cameras_file, settings.cameras_fallback, settings.contractors_file)
    engine = Engine(db, settings, clock, registry)
    views = Views(engine)
    views.sidewalks = Sidewalks.load(settings.sidewalks_file)
    guard = SpamGuard(db, settings, clock)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    _restore_demo_clock(db)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = None
        if start_ticker:
            async def loop():
                while True:
                    try:
                        await asyncio.to_thread(engine.tick)
                    except Exception as exc:  # keep ticking; one bad row must not stop deadlines
                        print("tick failed:", exc)
                    await asyncio.sleep(settings.tick_seconds)
            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Lantern", version="0.2.0", lifespan=lifespan,
                  description="Winter sidewalk alerts for Riga: camera signals + resident reports.")
    app.state.engine, app.state.views, app.state.db, app.state.guard = engine, views, db, guard

    @app.middleware("http")
    async def gate(request: Request, call_next):
        """Who may reach what (see app/auth.py and app/tgapp.py):
        - the Mini App page, its assets and pass-checked upload, /health and the login page: anyone;
        - logged in (session cookie): everything, also through the public link;
        - no LANTERN_PASSWORD set: as before (local: everything, public link: Mini App only);
        - otherwise pages go to the login page, and the API answers 401 unless the caller is a
          machine on this computer (bot, camera worker, demo script) or sends INTERNAL_API_KEY."""
        path = request.url.path
        proxied = tgapp.proxied(request.headers)
        if tgapp.public_path(path) or path in auth.OPEN:
            return await call_next(request)
        if auth.valid_session(request.cookies.get(auth.COOKIE)):
            return await call_next(request)
        if not auth.enabled():
            if proxied:
                return PlainTextResponse("Not Found", status_code=404)
            return await call_next(request)
        if path in auth.PAGES or path.endswith("/evidence"):
            target = path + ("?" + request.url.query if request.url.query else "")
            return RedirectResponse("/login?next=" + quote(target, safe=""), status_code=303)
        host = request.client.host if request.client else None
        if guard.trusted(None if proxied else host, request.headers.get("x-lantern-key")):
            return await call_next(request)
        return JSONResponse({"detail": "login required"}, status_code=401)

    # ------------------------------------------------------------------ static
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
    if settings.mock_dir.is_dir():
        app.mount("/static", StaticFiles(directory=settings.mock_dir), name="static")
    app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")

    def page(name: str):
        return FileResponse(STATIC / name, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/inspector")

    @app.get("/inspector", include_in_schema=False)
    def inspector_page():
        return page("inspector.html")

    @app.get("/contractor", include_in_schema=False)
    def contractor_page():
        return page("contractor.html")

    @app.get("/report", include_in_schema=False)
    def report_page():
        return page("report.html")

    @app.get("/tg", include_in_schema=False)
    def telegram_app_page():
        return page("tg.html")

    # ------------------------------------------------------------------ login
    @app.get("/login", include_in_schema=False)
    def login_form(request: Request, next: Optional[str] = None):
        if not auth.enabled() or auth.valid_session(request.cookies.get(auth.COOKIE)):
            return RedirectResponse(auth.safe_next(next), status_code=303)
        return HTMLResponse(auth.login_page(next or "/inspector"), headers={"Cache-Control": "no-store"})

    @app.post("/login", include_in_schema=False)
    def login_submit(request: Request, username: str = Form(""), password: str = Form(""),
                     next: str = Form("/inspector")):
        if not auth.enabled():
            return RedirectResponse(auth.safe_next(next), status_code=303)
        addr = tgapp.client_ip(request.headers, request.client.host if request.client else None) or "-"
        if auth.too_many_fails(addr):
            return HTMLResponse(auth.login_page(next, "Pārāk daudz mēģinājumu, pagaidi 15 min / "
                                                      "Too many tries, wait 15 minutes"), status_code=429)
        if not auth.check_login(username, password):
            auth.failed(addr)
            return HTMLResponse(auth.login_page(next, "Nepareizs lietotājs vai parole / Wrong username or password"),
                                status_code=401)
        resp = RedirectResponse(auth.safe_next(next), status_code=303)
        resp.set_cookie(auth.COOKIE, auth.make_session(), max_age=auth.SESSION_HOURS * 3600, httponly=True,
                        samesite="lax", secure=tgapp.proxied(request.headers))
        return resp

    @app.get("/logout", include_in_schema=False)
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(auth.COOKIE)
        return resp

    # ------------------------------------------------------------------ meta
    @app.get("/health")
    def health():
        return {"ok": True, "now": fmt_ts(clock.now())}

    @app.get("/meta")
    def meta():
        return {
            "cameras": registry.public_cameras(),
            "contractors": [{"id": c["id"], "name": c.get("name", c["id"]), "districts": c.get("districts", [])}
                            for c in registry.contractors],
            "tile_url": settings.tile_url,
            "tile_attribution": settings.tile_attribution,
            "images_credit": settings.images_credit,
            "source_url": settings.source_url,
            "analyze_connected": bool(settings.analyze_url),
            "login": auth.enabled(),
            "settings": engine.runtime_view(),
            "enums": {"passable": PASSABLE, "hazard": REPORT_HAZARDS, "place_type": PLACE_TYPES},
        }

    # ------------------------------------------------------------------ camera -> app
    class SignalIn(BaseModel):
        source: Literal["camera"] = "camera"
        camera_id: str = Field(min_length=1, max_length=100)
        zone_id: str = Field(min_length=1, max_length=150)
        lat: float = Field(ge=-90, le=90)
        lon: float = Field(ge=-180, le=180)
        timestamp: str
        hazard_class: Literal["clear", "snow", "blocked", "possible_ice"]
        blocked_share: float = Field(ge=0, le=1)
        confidence: float = Field(ge=0, le=1)
        frame_url: Optional[str] = None
        crop_url: Optional[str] = None

    @app.post("/signals", status_code=201, tags=["camera"])
    def post_signal(sig: SignalIn):
        try:
            parse_ts(sig.timestamp)
        except ValueError:
            raise HTTPException(422, "timestamp must be ISO 8601 UTC")
        return {"alert_id": engine.ingest_signal(sig.model_dump())}

    # ------------------------------------------------------------------ resident -> app
    async def read_photo(photo: UploadFile) -> tuple:
        data = await photo.read(MAX_PHOTO_BYTES + 1)
        if not data:
            raise HTTPException(422, "photo is required")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo is larger than 10 MB")
        ctype = (photo.content_type or "").lower()
        if ctype not in IMAGE_TYPES:
            raise HTTPException(415, "photo must be a JPEG, PNG, WebP or HEIC image")
        return data, ctype

    def sender_ip(request: Request) -> Optional[str]:
        return tgapp.client_ip(request.headers, request.client.host if request.client else None)

    async def take(*, data: bytes, ctype: str, filename: Optional[str], lat: float, lon: float, device: str,
                   ip_h: str, trusted: bool, chan: str, comment: str = "", passable: Optional[str] = None,
                   hazard: Optional[str] = None, place_type: Optional[str] = None,
                   location_source: Optional[str] = None, timestamp: Optional[str] = None,
                   registration_no: Optional[str] = None, capture: Optional[str] = None,
                   gps: Optional[tuple] = None) -> dict:
        """Spam checks, /analyze, storing: shared by the web form, the bot and the Telegram Mini App."""
        refused = guard.check(device, ip_h, trusted)
        if refused:
            guard.event(device, ip_h, refused["reason"])
            raise HTTPException(429, detail={"code": refused["reason"], "retry_after": refused["retry_after"],
                                             "message": "too many reports from this sender, try again later"},
                                headers={"Retry-After": str(refused["retry_after"])})
        if not guard.in_service_area(lat, lon):
            guard.event(device, ip_h, "outside_area")
            raise HTTPException(422, detail={"code": "outside_area",
                                             "message": "this location is outside the service area"})
        sha, dhash = await asyncio.to_thread(photo_hashes, data)
        ts = parse_ts(timestamp) if timestamp else clock.now()
        earlier = guard.same_photo(sha, dhash)          # this photo (or a near copy) was already sent
        repeat = engine.device_duplicate(lat, lon, ts, device)  # this sender already reported this place

        reuse_of, name = None, None
        if earlier is not None:
            reuse_of, name = earlier["id"], earlier["photo_path"]  # keep one copy of the file
            analysis = {"relevant": earlier["relevant"], "score": earlier["ai_score"], "hint": earlier["ai_hint"],
                        "note": f"same photo as report #{earlier['id']}, not re-analysed"}
        elif repeat is not None:
            analysis = {"relevant": repeat["relevant"], "score": repeat["ai_score"], "hint": repeat["ai_hint"],
                        "note": f"repeat from the same sender for this place (report #{repeat['id']}), not re-analysed"}
        else:
            analysis = await asyncio.to_thread(
                analyze_mod.analyze, settings.analyze_url, settings.analyze_timeout, data,
                filename or "photo", ctype, comment)
        if name is None:
            name = f"{fmt_ts(clock.now()).replace(':', '').replace('-', '')}_{secrets.token_hex(4)}{IMAGE_TYPES[ctype]}"
            (settings.upload_dir / name).write_bytes(data)
        # residents are no longer asked "can people get through?" or "what is there?": the photo answers.
        # The model's verdict stands in (marked passable_by=ai, so the evidence package does not say
        # a resident claimed it); its hint becomes the hazard type.
        passable_by = "resident" if passable else "ai"
        if passable is None:
            passable = {"accept": "no", "reject": "yes"}.get(analysis.get("relevant"), "partly")
        if hazard is None and analysis.get("relevant") != "reject":
            hazard = {"snow": "snow", "blocked": "snow", "ice": "ice", "icicles": "icicles"}.get(analysis.get("hint"))
        rep = engine.ingest_report(
            {"lat": lat, "lon": lon, "passable": passable, "passable_by": passable_by, "hazard": hazard,
             "place_type": place_type, "loc_source": location_source, "capture": capture,
             "comment": comment, "device_id": device, "timestamp": timestamp,
             "gps_lat": gps[0] if gps else None, "gps_lon": gps[1] if gps else None,
             "pin_moved_m": gps[2] if gps else None}, analysis, name, chan,
            photo_sha256=sha, photo_dhash=dhash, ip_hash=ip_h, reuse_of=reuse_of, registration_no=registration_no)
        if rep["relevant"] == "reject" or rep["duplicate"] or rep["reuse_of"]:
            guard.strike(device)  # repeated rejects/duplicates -> sender muted for a day
        return {"report_id": rep["id"], "ticket": None if rep["relevant"] == "reject" else rep["ticket"],
                "relevant": rep["relevant"],
                "alert_id": rep["alert_id"], "duplicate": bool(rep["duplicate"]),
                "same_photo": rep["reuse_of"] is not None,
                "ai_hint": rep["ai_hint"], "ai_note": rep["ai_note"]}

    @app.post("/reports", status_code=201, tags=["resident"])
    async def post_report(
        request: Request, response: Response,
        photo: UploadFile = File(...),
        lat: float = Form(..., ge=-90, le=90),
        lon: float = Form(..., ge=-180, le=180),
        passable: Optional[str] = Form(None),  # no longer asked: the model's verdict fills it
        hazard: Optional[str] = Form(None),
        place_type: Optional[str] = Form(None),
        comment: Optional[str] = Form(None),
        device_id: Optional[str] = Form(None),
        timestamp: Optional[str] = Form(None),
        channel: Optional[str] = Form(None),
        registration_no: Optional[str] = Form(None),
        location_source: Optional[str] = Form(None),  # gps | pin | typed | map | coarse (missing: trusted caller)
    ):
        passable = passable or None
        if passable is not None and passable not in PASSABLE:
            raise HTTPException(422, f"passable must be one of {PASSABLE}")
        hazard = hazard or None
        place_type = place_type or None
        if hazard is not None and hazard not in REPORT_HAZARDS:
            raise HTTPException(422, f"hazard must be one of {REPORT_HAZARDS}")
        if place_type is not None and place_type not in PLACE_TYPES:
            raise HTTPException(422, f"place_type must be one of {PLACE_TYPES}")
        registration_no = (registration_no or "").strip()[:40] or None
        location_source = location_source or None
        if location_source is not None and location_source not in LOCATION_SOURCES:
            raise HTTPException(422, f"location_source must be one of {LOCATION_SOURCES}")
        comment = (comment or "").strip()
        if len(comment) > 200:
            raise HTTPException(422, "comment is limited to 200 characters")
        if timestamp:
            try:
                parse_ts(timestamp)
            except ValueError:
                raise HTTPException(422, "timestamp must be ISO 8601 UTC")
        data, ctype = await read_photo(photo)

        # --- who is sending: only trusted callers (bot / replay on this machine, or INTERNAL_API_KEY)
        # may name their own device_id; web users always get the random cookie id. A request that came
        # through the public tunnel is never trusted by address, even though it arrives from 127.0.0.1.
        host = sender_ip(request)
        trusted = guard.trusted(None if tgapp.proxied(request.headers) else host, request.headers.get("x-lantern-key"))
        cookie = request.cookies.get(DEVICE_COOKIE)
        if device_id and trusted:
            device = device_id.strip()[:64]
        else:
            device = cookie or secrets.token_hex(8)
            if not cookie:
                response.set_cookie(DEVICE_COOKIE, device, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
        chan = channel if channel in ("web", "telegram", "whatsapp", "replay") else ("replay" if device_id else "web")
        return await take(data=data, ctype=ctype, filename=photo.filename, lat=lat, lon=lon, device=device,
                          ip_h=guard.ip_hash(host), trusted=trusted, chan=chan, comment=comment, passable=passable,
                          hazard=hazard, place_type=place_type, location_source=location_source,
                          timestamp=timestamp, registration_no=registration_no)

    @app.post("/reports/app", status_code=201, tags=["resident"])
    async def post_app_report(
        request: Request,
        photo: UploadFile = File(...),
        lat: float = Form(..., ge=-90, le=90),
        lon: float = Form(..., ge=-180, le=180),
        accuracy: Optional[float] = Form(None, ge=0),  # metres, from the phone
        capture: str = Form("live"),                    # live: the app's own camera (the only kind taken)
        tg_pass: str = Form(...),
        gps_lat: Optional[float] = Form(None, ge=-90, le=90),    # the phone's own fix, when lat/lon is a pin
        gps_lon: Optional[float] = Form(None, ge=-180, le=180),  # the resident moved on the preview map
    ):
        """Telegram Mini App: the photo was taken in the app just now, the place is the phone's position.
        The sender is the person the bot signed the pass for; time is the server's, not the phone's.
        On the preview map the resident may move the pin up to PIN_MOVE_M from the phone's fix (gps_lat,
        gps_lon); a pin further away is refused. Both points are kept and the inspector sees the move."""
        device = tgapp.check_pass(tg_pass)
        if device is None:
            raise HTTPException(403, detail={"code": "bad_pass", "message": "open the form again from the Lantern bot"})
        if capture != "live":  # no live camera, no report: no file dialog, no gallery
            raise HTTPException(422, detail={"code": "live_only",
                                             "message": "only a photo taken now in the app's camera is accepted"})
        if (gps_lat is None) != (gps_lon is None):
            raise HTTPException(422, detail={"code": "bad_fix", "message": "send gps_lat and gps_lon together"})
        gps = None
        if gps_lat is not None:
            moved = haversine_m(gps_lat, gps_lon, lat, lon)
            # 1.5 m of slack: the map and this formula round a little differently
            if moved > settings.pin_move_m + 1.5:
                raise HTTPException(422, detail={"code": "moved_too_far",
                                                 "message": f"the pin may move at most {settings.pin_move_m:g} m"})
            gps = (gps_lat, gps_lon, round(moved, 1))
        data, ctype = await read_photo(photo)
        # a fix worse than GPS_ACCURACY_M (wifi / cell tower guess) does not count as an exact place
        loc = "gps" if accuracy is not None and accuracy <= settings.gps_accuracy_m else "coarse"
        return await take(data=data, ctype=ctype, filename=photo.filename, lat=lat, lon=lon, device=device,
                          ip_h=guard.ip_hash(sender_ip(request)), trusted=False, chan="telegram",
                          location_source=loc, capture=capture, gps=gps)

    @app.get("/reports/ticket/{ticket}", tags=["resident"])
    def ticket_status(ticket: str):
        st = views.ticket_status(ticket.strip().upper())
        if st is None:
            raise HTTPException(404, "unknown ticket")
        return st

    @app.get("/reports", tags=["inspector"])
    def list_reports(role: str = "inspector", relevant: Optional[str] = None):
        if role != "inspector":
            raise HTTPException(403, "inspector only")
        return views.reports_list(relevant)

    class Moderation(BaseModel):
        decision: Literal["accept", "reject"]
        actor: str = "inspector"

    @app.post("/reports/{report_id}/moderate", tags=["inspector"])
    def moderate(report_id: int, body: Moderation):
        try:
            r = engine.moderate_report(report_id, body.decision, f"inspector:{body.actor}")
            if body.decision == "reject":
                guard.strike(r["device_id"])
        except KeyError:
            raise HTTPException(404, "unknown report")
        except RuleError as exc:
            raise HTTPException(409, str(exc))
        return views.report(r, "inspector")

    # ------------------------------------------------------------------ spam (inspector)
    @app.get("/spam", tags=["inspector"])
    def spam_summary(role: str = "inspector", hours: float = Query(24, gt=0)):
        if role != "inspector":
            raise HTTPException(403, "inspector only")
        return guard.summary(hours)

    class BlockIn(BaseModel):
        hours: float = Field(24, gt=0, le=24 * 365)
        actor: str = "inspector"
        reason: str = Field("blocked by inspector", max_length=200)

    @app.post("/reports/{report_id}/block-sender", tags=["inspector"])
    def block_sender(report_id: int, body: BlockIn):
        r = db.one("SELECT device_id FROM reports WHERE id = ?", (report_id,))
        if r is None:
            raise HTTPException(404, "unknown report")
        guard.block(r["device_id"], body.hours, f"inspector:{body.actor}", body.reason)
        return guard.summary()

    class UnblockIn(BaseModel):
        device_id: str

    @app.post("/devices/unblock", tags=["inspector"])
    def unblock(body: UnblockIn):
        if not guard.unblock(body.device_id):
            raise HTTPException(404, "device is not blocked")
        return guard.summary()

    # ------------------------------------------------------------------ alerts
    def _role_scope(role: str, district: Optional[str], contractor: Optional[str]):
        if role not in ("inspector", "contractor"):
            raise HTTPException(400, "role must be inspector or contractor")
        if role == "contractor":
            districts = views.contractor_districts(district, contractor)
            if not districts:
                raise HTTPException(400, "contractor view needs district= or contractor=")
            return districts
        return None

    @app.get("/alerts", tags=["alerts"])
    def list_alerts(role: str = "inspector", district: Optional[str] = None, contractor: Optional[str] = None,
                    status: Optional[str] = None, active: bool = False):
        districts = _role_scope(role, district, contractor)
        engine.tick()  # deadline check on every read too, in case the background loop lags
        if role == "inspector" and district:
            districts_rows = [a for a in views.alert_rows("inspector", status=status, include_closed=not active)
                              if a["district"] == district]
        else:
            districts_rows = views.alert_rows(role, districts, status, include_closed=not active)
        return {"now": fmt_ts(clock.now()), "settings": engine.runtime_view(),
                "alerts": [views.alert(a, role) for a in districts_rows]}

    @app.get("/alerts/{alert_id}", tags=["alerts"])
    def get_alert(alert_id: int, role: str = "inspector", district: Optional[str] = None,
                  contractor: Optional[str] = None):
        districts = _role_scope(role, district, contractor)
        a = engine.alert(alert_id)
        if a is None:
            raise HTTPException(404, "unknown alert")
        if role == "contractor":
            visible = {r["id"] for r in views.alert_rows("contractor", districts)}
            if alert_id not in visible:
                raise HTTPException(404, "unknown alert")
        return views.alert(a, role, detail=True)

    class StatusChange(BaseModel):
        status: Optional[Literal["watch", "cleared_in_time", "open", "done_reported", "verified", "reopened"]] = None
        severity: Optional[Literal["act", "notice"]] = Field(None, description="inspector only")
        role: Literal["inspector", "contractor"]
        actor: str = ""
        contractor: Optional[str] = None
        note: str = Field("", max_length=500)
        false_alarm: bool = Field(False, description="inspector only, with status verified: no snow on site (KPI 1)")

    @app.post("/alerts/{alert_id}/status", tags=["alerts"])
    def change_status(alert_id: int, body: StatusChange):
        """Change the status and/or (inspector) the severity; who and when go to status_history."""
        if body.status is None and body.severity is None:
            raise HTTPException(422, "status or severity is required")
        if body.severity is not None and body.role != "inspector":
            raise HTTPException(403, "only the inspector changes the severity")
        if body.false_alarm and (body.role != "inspector" or body.status not in ("verified", "cleared_in_time")):
            raise HTTPException(403, "only the inspector closes an alert as a false alarm (status verified)")
        try:
            a = None
            if body.severity is not None:
                a = engine.set_severity(alert_id, body.severity, body.actor, body.note if body.status is None else "")
            if body.status is not None:
                a = engine.change_status(alert_id, body.status, body.role, body.actor, body.note, body.contractor,
                                         false_alarm=body.false_alarm)
        except KeyError:
            raise HTTPException(404, "unknown alert")
        except RuleError as exc:
            raise HTTPException(409, str(exc))
        return views.alert(a, body.role, detail=True)

    class WarningIn(BaseModel):
        role: Literal["inspector"]
        message: str = Field(..., min_length=1, max_length=500)
        actor: str = ""

    @app.post("/alerts/{alert_id}/warning", tags=["inspector"])
    def send_warning(alert_id: int, body: WarningIn):
        """The inspector writes a warning to the contractor of an open job; the contractor sees it on the
        job card and it goes to the status history (evidence)."""
        try:
            a = engine.send_warning(alert_id, body.message, body.actor)
        except KeyError:
            raise HTTPException(404, "unknown alert")
        except RuleError as exc:
            raise HTTPException(409, str(exc))
        return views.alert(a, "inspector", detail=True)

    @app.get("/alerts/{alert_id}/evidence", tags=["inspector"], response_class=HTMLResponse)
    def alert_evidence(alert_id: int, role: str = "inspector", format: Literal["html", "json"] = "html",
                       lang: Literal["en", "lv"] = "en"):
        """Evidence package: frame + time + place + history. Inspector only, never the contractor."""
        if role != "inspector":
            raise HTTPException(403, "inspector only")
        a = engine.alert(alert_id)
        if a is None:
            raise HTTPException(404, "unknown alert")
        ev = views.evidence(a)
        if format == "json":
            return JSONResponse(ev)
        return HTMLResponse(evidence_mod.render(ev, settings.tile_url, settings.tile_attribution,
                                                settings.images_credit, settings.source_url, lang),
                            headers={"Cache-Control": "no-store"})

    @app.get("/sections", tags=["inspector"])
    def street_sections(role: str = "inspector"):
        """Street sections for the inspector map: blocks with a camera alert or 2+ residents, coloured
        by their worst alert (app/segments.py). Single complaints stay dots."""
        if role != "inspector":
            raise HTTPException(403, "inspector only")
        engine.tick()
        return {"source": "osm" if views.sidewalks else "cluster", "sections": views.sections()}

    net_cache: dict = {}

    @app.get("/map/network", tags=["map"])
    def map_network(request: Request):
        """The sidewalk network both maps draw first, like Riga's pGIS: every stretch of sidewalk (or street
        where OpenStreetMap has no sidewalk beside it) and every square, geometry only. It changes only with
        config/riga_sidewalks.geojson, so it is built once and sent gzipped."""
        if "plain" not in net_cache:
            sw = views.sidewalks
            body = {"attribution": (sw.attribution if sw and sw.attribution else "© OpenStreetMap contributors, ODbL"),
                    "blocks": sw.network() if sw else []}
            net_cache["plain"] = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            net_cache["gzip"] = gzip.compress(net_cache["plain"], 6)
            net_cache["etag"] = '"' + hashlib.sha1(net_cache["plain"]).hexdigest()[:16] + '"'
        # the browser keeps it but asks each time (304 when unchanged), so a new sidewalk file shows at once
        if request.headers.get("if-none-match") == net_cache["etag"]:
            return Response(status_code=304, headers={"ETag": net_cache["etag"]})
        gz = "gzip" in (request.headers.get("accept-encoding") or "")
        headers = {"Cache-Control": "private, no-cache", "Vary": "Accept-Encoding", "ETag": net_cache["etag"]}
        if gz:
            headers["Content-Encoding"] = "gzip"
        return Response(net_cache["gzip" if gz else "plain"], media_type="application/json", headers=headers)

    @app.get("/map/status", tags=["map"])
    def map_status(role: str = "inspector", district: Optional[str] = None, contractor: Optional[str] = None):
        """The colour of each stretch: the state of its latest alert - registered (open, reopened),
        started (watch, done_reported), finished (verified, cleared_in_time); a stretch not listed has no
        task (blue). Plus every alert's dot on its line. A contractor gets only their own jobs."""
        districts = _role_scope(role, district, contractor)
        engine.tick()
        return views.network_status(role, districts)

    @app.get("/inspection/today", tags=["inspector"])
    def inspection_today(limit: int = Query(10, ge=1, le=100)):
        engine.tick()
        return {"now": fmt_ts(clock.now()), "alerts": views.inspection_today(limit)}

    @app.get("/stats/response", tags=["inspector"])
    def stats(within_hours: Optional[float] = Query(None, gt=0, description="default FIX_HOURS (24)")):
        return views.response_stats(within_hours)

    @app.get("/export.geojson", tags=["export"])
    def export_geojson():
        return JSONResponse(views.export_geojson(), media_type="application/geo+json",
                            headers={"Content-Disposition": 'attachment; filename="lantern_alerts.geojson"'})

    @app.get("/export.csv", tags=["export"])
    def export_csv():
        return PlainTextResponse(views.export_csv(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="lantern_alerts.csv"'})

    # ------------------------------------------------------------------ snowfalls (deadline source)
    class SnowfallIn(BaseModel):
        start: Optional[str] = Field(None, description='ISO 8601 UTC or "now"')
        end: Optional[str] = Field(None, description='ISO 8601 UTC, "now", or empty while it is still snowing')
        source: str = Field("api", max_length=40)

    @app.post("/snowfalls", status_code=201, tags=["deadline"])
    def post_snowfall(body: SnowfallIn):
        """End of a snowfall -> clearing deadline 08:00 / 22:00 Riga (regulation RD-24-270-sn)."""
        try:
            start = clock.now() if body.start == "now" else parse_ts(body.start)
            end = clock.now() if body.end == "now" else parse_ts(body.end)
            sf = engine.add_snowfall(start, end, body.source)
        except (RuleError, ValueError) as exc:
            raise HTTPException(422, str(exc))
        return {**sf, "settings": engine.runtime_view()}

    @app.get("/snowfalls", tags=["deadline"])
    def list_snowfalls():
        return [engine.snowfall_view(r) for r in db.q("SELECT * FROM snowfalls ORDER BY id DESC")]

    @app.get("/settings", tags=["inspector"])
    def get_settings():
        return engine.runtime_view()

    # ------------------------------------------------------------------ demo controls
    class DemoClockIn(BaseModel):
        scenario_start: Optional[str] = Field(None, description="scenario time at real_start (ISO UTC); empty = real time")
        real_start: Optional[str] = Field(None, description="real time the scenario starts (ISO UTC), default now")
        factor: float = Field(1.0, gt=0, le=100000, description="scenario seconds per real second (1 h = 6 s -> 600)")

    def _demo_only():
        if not settings.demo_endpoints:
            raise HTTPException(404, "demo endpoints are off (DEMO_ENDPOINTS=0)")

    @app.post("/demo/clock", tags=["demo"])
    def demo_clock(body: DemoClockIn):
        """Demo only: accelerated clock. now = scenario_start + (real now - real_start) * factor."""
        _demo_only()
        try:
            if not body.scenario_start:
                clock.reset()
                db.run("DELETE FROM settings WHERE key = 'demo_clock'")
            else:
                clock.configure(parse_ts(body.scenario_start),
                                parse_ts(body.real_start) if body.real_start else None, body.factor)
                d = clock.describe()
                db.run("INSERT INTO settings(key, value) VALUES('demo_clock', ?) ON CONFLICT(key) DO UPDATE SET "
                       "value = excluded.value", (f"{d['scenario_start']}|{d['real_start']}|{d['factor']}",))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        engine.tick()
        return engine.runtime_view()

    @app.get("/demo/clock", tags=["demo"])
    def get_demo_clock():
        return clock.describe()

    @app.post("/admin/reset", tags=["demo"])
    def reset(keep_clock: bool = True):
        """Demo only: wipe alerts, signals, reports, snowfalls and history (the demo clock is kept)."""
        _demo_only()
        db.reset()
        if not keep_clock:
            clock.reset()
            db.run("DELETE FROM settings WHERE key = 'demo_clock'")
        return {"ok": True, "settings": engine.runtime_view()}

    return app


def _restore_demo_clock(db) -> None:
    """Keep the demo clock across a server restart (a test that froze the clock is left alone)."""
    if clock.describe()["mode"] == "frozen":
        return
    row = db.one("SELECT value FROM settings WHERE key = 'demo_clock'")
    if row and row["value"]:
        try:
            start, real, factor = row["value"].split("|")
            clock.configure(parse_ts(start), parse_ts(real), float(factor))
        except ValueError:
            pass
    else:
        clock.reset()


app = build_app()
