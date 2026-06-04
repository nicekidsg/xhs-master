from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


BASE_URL = "http://127.0.0.1:8000"
SCREENSHOT = Path("app/data/generated/smoke-dashboard.png")


def main() -> None:
    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.goto(BASE_URL, wait_until="networkidle")
        expect(page.get_by_role("heading", name="今日内容生产台")).to_be_visible()
        page.screenshot(path=str(SCREENSHOT), full_page=True)

        page.get_by_role("main").get_by_role("link", name="新建主题").click()
        page.get_by_label("核心主题").fill("AI 帮我 15 分钟完成竞品分析")
        first_hotspot = page.locator("input[name=hotspot_ids]").first
        first_hotspot.check()
        page.get_by_role("button", name="生成脚本与文案").click()
        expect(page.locator("h1").filter(has_text="竞品分析")).to_be_visible()
        expect(page.get_by_role("button", name="生成图片/视频包")).to_be_visible()
        browser.close()


if __name__ == "__main__":
    main()
