from __future__ import annotations

from pathlib import Path

from app.config import settings


class PublishPreparationError(RuntimeError):
    pass


async def prepare_xhs_publish(draft: dict, assets: list[dict], scheduled_at: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PublishPreparationError("Playwright is not installed. Run pip install -r requirements.txt first.") from exc

    image_paths = [item["path"] for item in assets if item["kind"] == "image"]
    if not image_paths:
        raise PublishPreparationError("No image assets found for this draft.")

    settings.browser_profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_profile),
            headless=False,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(settings.creator_publish_url, wait_until="domcontentloaded")

        # Selectors on the creator platform change. These guarded attempts fill
        # obvious fields and then leave the browser open for final human review.
        await _try_upload(page, image_paths)
        await _try_fill_text(page, ["标题", "title"], draft["selected_title"])
        await _try_fill_text(page, ["正文", "描述", "content", "textarea"], _compose_body(draft))
        await _try_fill_text(page, ["定时", "发布时间", "schedule"], scheduled_at)
        return "浏览器已打开并尝试填入发布信息。请在小红书页面人工核对，确认无误后再点击最终发布/定时按钮。"


async def _try_upload(page, paths: list[str]) -> None:
    file_inputs = page.locator("input[type=file]")
    count = await file_inputs.count()
    if count:
        await file_inputs.first.set_input_files([str(Path(path)) for path in paths])


async def _try_fill_text(page, labels: list[str], value: str) -> None:
    for label in labels:
        try:
            target = page.get_by_label(label)
            if await target.count():
                await target.first.fill(value)
                return
        except Exception:
            pass
    for selector in ["textarea", "input[type=text]", "[contenteditable=true]"]:
        try:
            target = page.locator(selector)
            if await target.count():
                await target.first.fill(value)
                return
        except Exception:
            pass


def _compose_body(draft: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in draft["tags"])
    return f"{draft['body']}\n\n{draft['cta']}\n\n{tags}"

