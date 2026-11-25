"""Lantern app: backend + inspector, contractor and resident screens (port 8000).

Run from the repo root:  uvicorn app.main:app --port 8000
"""
import asyncio
import contextlib
import secrets
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analyze as analyze_mod
from .config import settings
from .db import Database
from .engine import PASSABLE, PLACE_TYPES, REPORT_HAZARDS, Engine, RuleError
from .registry import Registry
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
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

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
    app.state.engine, app.state.views, app.state.db = engine, views, db

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
        passable: str = Form(...),
        hazard: Optional[str] = Form(None),
        place_type: Optional[str] = Form(None),
        comment: Optional[str] = Form(None),
        device_id: Optional[str] = Form(None),
        timestamp: Optional[str] = Form(None),
        channel: Optional[str] = Form(None),
    ):
        if passable not in PASSABLE:
            raise HTTPException(422, f"passable must be one of {PASSABLE}")
        hazard = hazard or None
        place_type = place_type or None
        if hazard is not None and hazard not in REPORT_HAZARDS:
            raise HTTPException(422, f"hazard must be one of {REPORT_HAZARDS}")
        if place_type is not None and place_type not in PLACE_TYPES:
            raise HTTPException(422, f"place_type must be one of {PLACE_TYPES}")
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

        device = (device_id or request.cookies.get(DEVICE_COOKIE) or "").strip()[:64]
        if not device:
            device = secrets.token_hex(8)
        if not request.cookies.get(DEVICE_COOKIE) and not device_id:
            response.set_cookie(DEVICE_COOKIE, device, max_age=3600 * 24 * 365, httponly=True, samesite="lax")

        analysis = await asyncio.to_thread(
            analyze_mod.analyze, settings.analyze_url, settings.analyze_timeout, data, photo.filename or "photo",
            ctype, comment)
        name = f"{fmt_ts(clock.now()).replace(':', '').replace('-', '')}_{secrets.token_hex(4)}{IMAGE_TYPES[ctype]}"
        (settings.upload_dir / name).write_bytes(data)
        chan = channel if channel in ("web", "telegram", "replay") else ("web" if not device_id else "replay")
        rep = engine.ingest_report(
            {"lat": lat, "lon": lon, "passable": passable, "hazard": hazard, "place_type": place_type,
             "comment": comment, "device_id": device, "timestamp": timestamp}, analysis, name, chan)
        return {"report_id": rep["id"], "ticket": rep["ticket"], "relevant": rep["relevant"],
                "alert_id": rep["alert_id"], "duplicate": bool(rep["duplicate"]),
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
        except KeyError:
            raise HTTPException(404, "unknown report")
        except RuleError as exc:
            raise HTTPException(409, str(exc))
        return views.report(r, "inspector")

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
        status: Literal["watch", "open", "done_reported", "verified", "reopened"]
        role: Literal["inspector", "contractor"]
        actor: str = ""
        contractor: Optional[str] = None
        note: str = Field("", max_length=500)

    @app.post("/alerts/{alert_id}/status", tags=["alerts"])
    def change_status(alert_id: int, body: StatusChange):
        try:
            a = engine.change_status(alert_id, body.status, body.role, body.actor, body.note, body.contractor)
        except KeyError:
            raise HTTPException(404, "unknown alert")
        except RuleError as exc:
            raise HTTPException(409, str(exc))
        return views.alert(a, body.role, detail=True)

    @app.get("/inspection/today", tags=["inspector"])
    def inspection_today(limit: int = Query(10, ge=1, le=100)):
        return {"now": fmt_ts(clock.now()), "alerts": views.inspection_today(limit)}

    @app.get("/stats/response", tags=["inspector"])
    def stats(within_hours: float = Query(6.0, gt=0)):
        return views.response_stats(within_hours)

    @app.get("/export.geojson", tags=["export"])
    def export_geojson():
        return JSONResponse(views.export_geojson(), media_type="application/geo+json",
                            headers={"Content-Disposition": 'attachment; filename="lantern_alerts.geojson"'})

    @app.get("/export.csv", tags=["export"])
    def export_csv():
        return PlainTextResponse(views.export_csv(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="lantern_alerts.csv"'})

    # ------------------------------------------------------------------ settings (demo controls)
    @app.get("/settings", tags=["inspector"])
    def get_settings():
        return engine.runtime_view()

    class SettingsIn(BaseModel):
        snowfall_end: Optional[str] = Field(None, description='ISO time, "now", or "" to clear')
        hour_seconds: Optional[float] = Field(None, gt=0)
        clearing_hours: Optional[float] = Field(None, ge=0)
        clearing_seconds: Optional[float] = Field(None, gt=0, description="sets hour_seconds = this / clearing_hours")

    @app.post("/settings", tags=["inspector"])
    def post_settings(body: SettingsIn):
        fields = body.model_fields_set
        hour = body.hour_seconds
        if body.clearing_seconds is not None:
            ch = body.clearing_hours if body.clearing_hours is not None else engine.runtime()["clearing_hours"]
            if ch <= 0:
                raise HTTPException(422, "clearing_hours must be > 0 to derive hour_seconds")
            hour = body.clearing_seconds / ch
        try:
            if body.snowfall_end not in (None, "", "now"):
                parse_ts(body.snowfall_end)
            return engine.update_runtime(
                snowfall_end=body.snowfall_end if "snowfall_end" in fields else ...,
                hour_seconds=hour, clearing_hours=body.clearing_hours)
        except (RuleError, ValueError) as exc:
            raise HTTPException(422, str(exc))

    @app.post("/admin/reset", tags=["inspector"])
    def reset(keep_settings: bool = True):
        """Demo only: wipe alerts, signals, reports and history."""
        db.reset()
        if not keep_settings:
            db.run("DELETE FROM settings")
        return {"ok": True}

    return app


app = build_app()
