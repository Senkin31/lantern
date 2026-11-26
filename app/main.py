"""Lantern app: backend + inspector, contractor and resident screens (port 8000).

Run from the repo root:  uvicorn app.main:app --port 8000
"""
import asyncio
import contextlib
import secrets
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analyze as analyze_mod
from . import evidence as evidence_mod
from .config import settings
from .db import Database
from .engine import PASSABLE, PLACE_TYPES, REPORT_HAZARDS, Engine, RuleError
from .registry import Registry
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
        comment = (comment or "").strip()
        if len(comment) > 200:
            raise HTTPException(422, "comment is limited to 200 characters")
        if timestamp:
            try:
                parse_ts(timestamp)
            except ValueError:
                raise HTTPException(422, "timestamp must be ISO 8601 UTC")
        data = await photo.read(MAX_PHOTO_BYTES + 1)
        if not data:
            raise HTTPException(422, "photo is required")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo is larger than 10 MB")
        ctype = (photo.content_type or "").lower()
        if ctype not in IMAGE_TYPES:
            raise HTTPException(415, "photo must be a JPEG, PNG, WebP or HEIC image")

        # --- who is sending: only trusted callers (bot / replay on this machine, or INTERNAL_API_KEY)
        # may name their own device_id; web users always get the random cookie id.
        host = request.client.host if request.client else None
        trusted = guard.trusted(host, request.headers.get("x-lantern-key"))
        cookie = request.cookies.get(DEVICE_COOKIE)
        if device_id and trusted:
            device = device_id.strip()[:64]
        else:
            device = cookie or secrets.token_hex(8)
            if not cookie:
                response.set_cookie(DEVICE_COOKIE, device, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
        ip_h = guard.ip_hash(host)

        # --- spam checks, all before the photo is sent to /analyze (see app/spam.py)
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
                photo.filename or "photo", ctype, comment)
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
        chan = channel if channel in ("web", "telegram", "whatsapp", "replay") else ("replay" if device_id else "web")
        rep = engine.ingest_report(
            {"lat": lat, "lon": lon, "passable": passable, "passable_by": passable_by, "hazard": hazard,
             "place_type": place_type,
             "comment": comment, "device_id": device, "timestamp": timestamp}, analysis, name, chan,
            photo_sha256=sha, photo_dhash=dhash, ip_hash=ip_h, reuse_of=reuse_of, registration_no=registration_no)
        if rep["relevant"] == "reject" or rep["duplicate"] or rep["reuse_of"]:
            guard.strike(device)  # repeated rejects/duplicates -> sender muted for a day
        return {"report_id": rep["id"], "ticket": rep["ticket"], "relevant": rep["relevant"],
                "alert_id": rep["alert_id"], "duplicate": bool(rep["duplicate"]),
                "same_photo": rep["reuse_of"] is not None,
                "ai_hint": rep["ai_hint"], "ai_note": rep["ai_note"]}

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
