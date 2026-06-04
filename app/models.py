from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


DRAFTED = "drafted"
ASSET_READY = "asset_ready"
APPROVED = "approved"
SCHEDULED = "scheduled"
PREPARED = "prepared"
PUBLISHED = "published"
FAILED = "failed"

VALID_TRANSITIONS = {
    DRAFTED: {ASSET_READY, FAILED},
    ASSET_READY: {APPROVED, FAILED},
    APPROVED: {SCHEDULED, FAILED},
    SCHEDULED: {PREPARED, FAILED},
    PREPARED: {PUBLISHED, FAILED},
    PUBLISHED: set(),
    FAILED: set(),
}


def assert_transition(current: str, target: str) -> None:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid status transition: {current} -> {target}")


@dataclass(frozen=True)
class ScheduleDefaults:
    publish_time: str = "20:30"
    timezone: str = "Asia/Shanghai"


def today_publish_at(now: datetime, defaults: ScheduleDefaults) -> str:
    hour, minute = [int(part) for part in defaults.publish_time.split(":", 1)]
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= now:
        scheduled = scheduled + timedelta(days=1)
    return scheduled.isoformat(timespec="minutes")


def dedupe_key(source: str, title: str) -> str:
    normalized = " ".join(title.strip().lower().split())
    return f"{source.strip().lower()}::{normalized}"


def comma_tags(tags: Iterable[str]) -> str:
    return ", ".join(tag.strip().lstrip("#") for tag in tags if tag.strip())
