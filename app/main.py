from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import settings
from app.db import Store
from app.models import APPROVED, ASSET_READY, PREPARED, SCHEDULED, ScheduleDefaults, today_publish_at
from app.services.assets import generate_assets
from app.services.content import build_provider
from app.services.hotspots import seed_default_hotspots
from app.services.publisher import PublishPreparationError, prepare_xhs_publish


app = FastAPI(title="小红书内容生成与发布控制台")
settings.asset_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.mount("/generated", StaticFiles(directory=str(settings.asset_dir)), name="generated")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
store = Store()


class TopicIn(BaseModel):
    core_theme: str
    content_format: str = "图文+短视频"
    hotspot_ids: List[int] = Field(default_factory=list)


class DraftGenerateIn(BaseModel):
    topic_id: int


class AssetGenerateIn(BaseModel):
    draft_id: int


class ScheduleIn(BaseModel):
    draft_id: int
    scheduled_at: Optional[str] = None
    timezone: str = settings.timezone


def _context(request: Request, **kwargs):
    base = {
        "request": request,
        "settings": settings,
        "asset_url": asset_url,
    }
    base.update(kwargs)
    return base


def asset_url(path: str) -> str:
    try:
        relative = Path(path).resolve().relative_to(settings.asset_dir.resolve())
        return f"/generated/{relative.as_posix()}"
    except ValueError:
        return path


@app.on_event("startup")
def startup() -> None:
    settings.asset_dir.mkdir(parents=True, exist_ok=True)
    seed_default_hotspots(store)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        _context(
            request,
            hotspots=store.list_hotspots(8),
            drafts=store.list_drafts(8),
            schedules=store.list_schedules(8),
        ),
    )


@app.get("/topics/new", response_class=HTMLResponse)
def new_topic(request: Request):
    return templates.TemplateResponse(
        "new_topic.html",
        _context(request, hotspots=store.list_hotspots(30)),
    )


@app.post("/topics")
def create_topic_form(
    core_theme: Annotated[str, Form()],
    content_format: Annotated[str, Form()] = "图文+短视频",
    hotspot_ids: Annotated[Optional[List[int]], Form()] = None,
):
    topic_id = store.create_topic(core_theme, content_format, hotspot_ids or [])
    draft_id = _generate_draft_for_topic(topic_id)
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.post("/hotspots/manual")
def add_hotspot_form(
    source: Annotated[str, Form()],
    title: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    heat: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    store.add_hotspot(source, title, url, heat, tags)
    return RedirectResponse("/", status_code=303)


@app.post("/hotspots/refresh")
def refresh_hotspots():
    seed_default_hotspots(store)
    return RedirectResponse("/", status_code=303)


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def review_draft(request: Request, draft_id: int):
    draft = _draft_or_404(draft_id)
    assets = store.list_assets(draft_id)
    return templates.TemplateResponse("review.html", _context(request, draft=draft, assets=assets))


@app.post("/drafts/{draft_id}/assets")
def create_assets_form(draft_id: int):
    draft = _draft_or_404(draft_id)
    created = generate_assets(draft)
    for item in created:
        store.add_asset(draft_id, item["kind"], item["path"], item["description"])
    if draft["status"] == "drafted":
        store.update_draft_status(draft_id, ASSET_READY)
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.post("/drafts/{draft_id}/approve")
def approve_form(draft_id: int):
    draft = _draft_or_404(draft_id)
    if draft["status"] == "drafted":
        raise HTTPException(400, "请先生成素材，再审核通过。")
    if draft["status"] == ASSET_READY:
        store.update_draft_status(draft_id, APPROVED)
    return RedirectResponse(f"/schedule/{draft_id}", status_code=303)


@app.get("/schedule/{draft_id}", response_class=HTMLResponse)
def schedule_page(request: Request, draft_id: int):
    draft = _draft_or_404(draft_id)
    default_at = today_publish_at(datetime.now(), ScheduleDefaults(settings.default_publish_time, settings.timezone))
    return templates.TemplateResponse("schedule.html", _context(request, draft=draft, default_at=default_at))


@app.post("/schedule/{draft_id}")
def create_schedule_form(
    draft_id: int,
    scheduled_at: Annotated[str, Form()],
    timezone: Annotated[str, Form()] = settings.timezone,
):
    draft = _draft_or_404(draft_id)
    if draft["status"] == APPROVED:
        schedule_id = store.create_schedule(draft_id, scheduled_at, timezone)
        store.update_draft_status(draft_id, SCHEDULED)
    else:
        existing = store.list_schedules(100)
        schedule_id = next((item["id"] for item in existing if item["draft_id"] == draft_id), None)
        if schedule_id is None:
            raise HTTPException(400, "只有审核通过的草稿可以创建排期。")
    return RedirectResponse(f"/publish/{schedule_id}", status_code=303)


@app.get("/publish/{schedule_id}", response_class=HTMLResponse)
def publish_page(request: Request, schedule_id: int):
    schedule = _schedule_or_404(schedule_id)
    draft = _draft_or_404(schedule["draft_id"])
    assets = store.list_assets(draft["id"])
    return templates.TemplateResponse(
        "publish.html",
        _context(request, draft=draft, schedule=schedule, assets=assets, message=""),
    )


@app.post("/publish/{schedule_id}/prepare")
def prepare_publish_form(schedule_id: int):
    schedule = _schedule_or_404(schedule_id)
    draft = _draft_or_404(schedule["draft_id"])
    assets = store.list_assets(draft["id"])
    try:
        notes = asyncio.run(prepare_xhs_publish(draft, assets, schedule["scheduled_at"]))
        if draft["status"] == SCHEDULED:
            store.update_draft_status(draft["id"], PREPARED)
        store.create_publish_job(draft["id"], schedule_id, PREPARED, notes)
    except PublishPreparationError as exc:
        store.create_publish_job(draft["id"], schedule_id, "failed", str(exc))
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(f"/publish/{schedule_id}", status_code=303)


@app.get("/mock/xhs-publish", response_class=HTMLResponse)
def mock_publish(request: Request):
    return templates.TemplateResponse("mock_publish.html", _context(request))


@app.post("/api/topics")
def api_create_topic(payload: TopicIn):
    topic_id = store.create_topic(payload.core_theme, payload.content_format, payload.hotspot_ids)
    return {"topic_id": topic_id}


@app.post("/api/drafts/generate")
def api_generate_draft(payload: DraftGenerateIn):
    return {"draft_id": _generate_draft_for_topic(payload.topic_id)}


@app.post("/api/assets/generate")
def api_generate_assets(payload: AssetGenerateIn):
    draft = _draft_or_404(payload.draft_id)
    created = generate_assets(draft)
    for item in created:
        store.add_asset(payload.draft_id, item["kind"], item["path"], item["description"])
    if draft["status"] == "drafted":
        store.update_draft_status(payload.draft_id, ASSET_READY)
    return {"assets": created}


@app.post("/api/reviews/{draft_id}/approve")
def api_approve(draft_id: int):
    draft = _draft_or_404(draft_id)
    if draft["status"] == ASSET_READY:
        store.update_draft_status(draft_id, APPROVED)
    else:
        raise HTTPException(400, "Draft must be asset_ready before approval.")
    return {"draft_id": draft_id, "status": APPROVED}


@app.post("/api/schedules")
def api_schedule(payload: ScheduleIn):
    draft = _draft_or_404(payload.draft_id)
    if draft["status"] != APPROVED:
        raise HTTPException(400, "Draft must be approved before scheduling.")
    scheduled_at = payload.scheduled_at or today_publish_at(
        datetime.now(),
        ScheduleDefaults(settings.default_publish_time, payload.timezone),
    )
    schedule_id = store.create_schedule(payload.draft_id, scheduled_at, payload.timezone)
    store.update_draft_status(payload.draft_id, SCHEDULED)
    return {"schedule_id": schedule_id, "scheduled_at": scheduled_at}


@app.post("/api/publish-jobs/{schedule_id}/prepare")
def api_prepare_publish(schedule_id: int):
    schedule = _schedule_or_404(schedule_id)
    draft = _draft_or_404(schedule["draft_id"])
    assets = store.list_assets(draft["id"])
    try:
        notes = asyncio.run(prepare_xhs_publish(draft, assets, schedule["scheduled_at"]))
    except PublishPreparationError as exc:
        store.create_publish_job(draft["id"], schedule_id, "failed", str(exc))
        raise HTTPException(400, str(exc)) from exc
    if draft["status"] == SCHEDULED:
        store.update_draft_status(draft["id"], PREPARED)
    job_id = store.create_publish_job(draft["id"], schedule_id, PREPARED, notes)
    return {"publish_job_id": job_id, "status": PREPARED, "notes": notes}


def _generate_draft_for_topic(topic_id: int) -> int:
    topic = store.get_topic(topic_id)
    all_hotspots = store.list_hotspots(100)
    selected = [item for item in all_hotspots if item["id"] in topic["selected_hotspot_ids"]]
    provider = build_provider()
    content = provider.generate(topic, selected)
    return store.create_draft(topic_id, content)


def _draft_or_404(draft_id: int) -> dict:
    try:
        return store.get_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _schedule_or_404(schedule_id: int) -> dict:
    try:
        return store.get_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
