from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class ContentProvider(Protocol):
    def generate(self, topic: dict, hotspots: list[dict]) -> dict:
        ...


@dataclass
class MockContentProvider:
    vertical: str = "AI/效率工具"

    def generate(self, topic: dict, hotspots: list[dict]) -> dict:
        theme = topic["core_theme"].strip()
        hotspot_titles = [item["title"] for item in hotspots[:3]]
        trend_line = "、".join(hotspot_titles) if hotspot_titles else "近期 AI 效率工具讨论"
        title_options = [
            f"{theme}：普通人也能用起来的 3 个效率变化",
            f"我用 {theme} 跑了一遍工作流，最有用的是这一步",
            f"别再只收藏工具清单了，{theme} 应该这样落地",
        ]
        body = (
            f"最近看到一个很明显的趋势：{trend_line}。\n\n"
            f"如果你的核心主题是「{theme}」，不要先追求把工具堆满，先把一个重复场景拆清楚：\n"
            "1. 哪一步每天都在重复？\n"
            "2. 哪些输入是固定的？\n"
            "3. 产出要给谁看？\n\n"
            "我的建议是先做一个 15 分钟小实验：选一个真实任务，用 AI 生成初稿，再人工补事实、删夸张表达、补自己的判断。"
            "这样既能提速，也不会把账号内容做成一眼模板化。\n\n"
            "适合今天就试的场景：会议纪要、资料摘要、选题拆解、竞品对比、短视频分镜。"
        )
        video_script = [
            {"scene": 1, "visual": "桌面上打开资料、日程和待办", "voiceover": f"你有没有发现，{theme} 真正省时间的地方不是替你思考，而是替你整理重复输入。", "subtitle": "AI 不是魔法，是工作流加速器"},
            {"scene": 2, "visual": "三栏画面：输入、处理、输出", "voiceover": "先固定输入，再让 AI 产出第一版，最后由人做判断和修改。", "subtitle": "输入固定，输出才稳定"},
            {"scene": 3, "visual": "发布前检查清单", "voiceover": "发布前一定检查事实、利益承诺和夸大表达，账号长期价值比单条爆文更重要。", "subtitle": "别让效率牺牲可信度"},
        ]
        return {
            "title_options": title_options,
            "selected_title": title_options[0],
            "body": body,
            "tags": ["AI工具", "效率工具", "小红书起号", "内容自动化", "工作流"],
            "cover_text": f"{theme}\n3 个可落地用法",
            "video_script": video_script,
            "risk_notes": [
                "避免承诺收益、涨粉、变现等确定性结果。",
                "热点只作为选题参考，正文需要补充自己的体验或判断。",
                "发布前核对工具名称、功能和时间敏感信息。",
            ],
            "cta": "你想把哪个重复工作流交给 AI 先跑一版？评论区可以丢给我。",
        }


@dataclass
class OpenAIContentProvider:
    fallback: ContentProvider
    api_key: str
    model: str = "gpt-4.1-mini"

    def generate(self, topic: dict, hotspots: list[dict]) -> dict:
        prompt = {
            "vertical": "AI/效率工具",
            "core_theme": topic["core_theme"],
            "content_format": topic.get("content_format", "图文+短视频"),
            "hotspots": hotspots,
            "required_json_keys": [
                "title_options",
                "selected_title",
                "body",
                "tags",
                "cover_text",
                "video_script",
                "risk_notes",
                "cta",
            ],
        }
        try:
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(
                    {
                        "model": self.model,
                        "input": [
                            {
                                "role": "system",
                                "content": (
                                    "你是小红书 AI/效率工具垂直账号的内容策划。"
                                    "只输出 JSON，不要 Markdown。video_script 必须是 scene/visual/voiceover/subtitle 对象数组。"
                                    "避免夸大收益、涨粉承诺和无法核验的事实。"
                                ),
                            },
                            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                        ],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = _extract_response_text(payload)
            return _normalize_generated_json(json.loads(text), self.fallback.generate(topic, hotspots))
        except Exception:
            return self.fallback.generate(topic, hotspots)


def build_provider() -> ContentProvider:
    fallback = MockContentProvider()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback
    return OpenAIContentProvider(
        fallback=fallback,
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    )


def _extract_response_text(payload: dict) -> str:
    if "output_text" in payload:
        return payload["output_text"]
    chunks = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def _normalize_generated_json(generated: dict, fallback: dict) -> dict:
    result = fallback.copy()
    for key in result:
        if key in generated and generated[key]:
            result[key] = generated[key]
    if not isinstance(result["title_options"], list):
        result["title_options"] = fallback["title_options"]
    if not isinstance(result["tags"], list):
        result["tags"] = fallback["tags"]
    if not isinstance(result["video_script"], list):
        result["video_script"] = fallback["video_script"]
    if not isinstance(result["risk_notes"], list):
        result["risk_notes"] = fallback["risk_notes"]
    return result
