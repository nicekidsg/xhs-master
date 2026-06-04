from __future__ import annotations

from dataclasses import dataclass

from app.db import Store


@dataclass(frozen=True)
class HotspotSeed:
    source: str
    title: str
    url: str
    heat: str
    tags: str


DEFAULT_HOTSPOTS = [
    HotspotSeed("公开热榜", "AI 浏览器助手如何改变资料搜集流程", "", "趋势", "AI工具,效率"),
    HotspotSeed("公开热榜", "多模态模型在短视频脚本生产中的新用法", "", "上升", "AI视频,内容创作"),
    HotspotSeed("人工补充", "打工人如何用自动化减少重复汇报", "", "选题", "效率工具,职场"),
    HotspotSeed("公开热榜", "知识库和个人工作流正在成为 AI 应用入口", "", "讨论", "知识管理,AI应用"),
]


def seed_default_hotspots(store: Store) -> int:
    before = len(store.list_hotspots(limit=200))
    for item in DEFAULT_HOTSPOTS:
        store.add_hotspot(item.source, item.title, item.url, item.heat, item.tags)
    after = len(store.list_hotspots(limit=200))
    return max(after - before, 0)

