from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.db import Store
from app.models import APPROVED, ASSET_READY, SCHEDULED, ScheduleDefaults, assert_transition, dedupe_key, today_publish_at
from app.services.assets import generate_assets
from app.services.content import MockContentProvider
from app.services.hotspots import seed_default_hotspots


class CoreWorkflowTests(unittest.TestCase):
    def test_hotspot_dedupe_key_normalizes_source_and_title(self):
        self.assertEqual(
            dedupe_key(" 公开热榜 ", " AI   浏览器助手 "),
            dedupe_key("公开热榜", "ai 浏览器助手"),
        )

    def test_invalid_status_transition_raises(self):
        with self.assertRaises(ValueError):
            assert_transition("drafted", SCHEDULED)

    def test_default_schedule_moves_to_tomorrow_after_publish_time(self):
        scheduled = today_publish_at(
            datetime(2026, 6, 4, 21, 0),
            ScheduleDefaults("20:30", "Asia/Shanghai"),
        )
        self.assertEqual(scheduled, "2026-06-05T20:30")

    def test_store_generates_complete_workflow_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            seed_default_hotspots(store)
            hotspots = store.list_hotspots()
            topic_id = store.create_topic("AI 自动生成周报", "图文+短视频", [hotspots[0]["id"]])
            topic = store.get_topic(topic_id)
            draft_id = store.create_draft(topic_id, MockContentProvider().generate(topic, hotspots[:1]))

            draft = store.get_draft(draft_id)
            self.assertEqual(draft["status"], "drafted")
            self.assertTrue(draft["title_options"])
            self.assertTrue(draft["video_script"])

            store.update_draft_status(draft_id, ASSET_READY)
            store.update_draft_status(draft_id, APPROVED)
            schedule_id = store.create_schedule(draft_id, "2026-06-04T20:30", "Asia/Shanghai")
            store.update_draft_status(draft_id, SCHEDULED)

            schedule = store.get_schedule(schedule_id)
            self.assertEqual(schedule["draft_id"], draft_id)
            self.assertEqual(store.get_draft(draft_id)["status"], SCHEDULED)

    def test_asset_generation_creates_publish_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = MockContentProvider().generate(
                {"core_theme": "AI 竞品分析"},
                [{"title": "AI 工具热榜"}],
            )
            draft["id"] = 7
            assets = generate_assets(draft, Path(tmp))

            self.assertEqual(len(assets), 3)
            for item in assets:
                self.assertTrue(Path(item["path"]).exists())


if __name__ == "__main__":
    unittest.main()

