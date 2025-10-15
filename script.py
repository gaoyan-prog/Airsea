import sys
import time
import random
import logging
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import stealth_sync
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
logger = logging.getLogger("zim")

DEBUG_DIR = Path(__file__).parent / "app" / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def human_like_navigate(page, url: str) -> None:
    try:
        page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
    except Exception:
        pass

    for key in ("Alt+d", "Control+l", "F6"):
        try:
            page.keyboard.press(key)
            page.wait_for_timeout(200)
            for ch in url:
                page.keyboard.type(ch, delay=random.randint(40, 120))
            with page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
                page.keyboard.press("Enter")
            return
        except Exception:
            # 清空再试
            try:
                page.keyboard.down("Control")
                page.keyboard.press("a")
                page.keyboard.up("Control")
                page.keyboard.press("Backspace")
            except Exception:
                pass

    # 兜底
    page.goto(url, wait_until="domcontentloaded", timeout=15000)


def save_debug(page, label: str) -> None:
    ts = time.strftime("%Y%m%d_%H%M%S")
    png = DEBUG_DIR / f"{ts}_{label}.png"
    html = DEBUG_DIR / f"{ts}_{label}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
    except Exception:
        pass
    try:
        html.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    logger.info("Saved debug: %s %s", png.name, html.name)


def main() -> int:
    # 参数：consnumber 可选；headless 可选；user_data_dir 可选
    cons = "ZIMUXIA8449359"
    headless = False
    user_data_dir: Optional[str] = str((Path(__file__).parent / "app" / "userdata_zim").resolve())
    url_tpl = "https://www.zim.com/tools/track-a-shipment?consnumber={}"

    if len(sys.argv) >= 2 and sys.argv[1]:
        cons = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2]:
        headless = sys.argv[2].lower() not in {"0", "false", "no"}
    if len(sys.argv) >= 4 and sys.argv[3]:
        user_data_dir = sys.argv[3]

    target_url = url_tpl.format(cons)
    logger.info("Open ZIM tracking cons=%s headless=%s user_data_dir=%s", cons, headless, user_data_dir)

    with sync_playwright() as p:
        launch_args = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }

        if user_data_dir:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/Los_Angeles",
                **launch_args,
            )
        else:
            browser = p.chromium.launch(**launch_args)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )

        page = ctx.new_page()

        try:
            try:
                stealth_sync(page)
            except Exception:
                pass

            # 地址栏式导航
            human_like_navigate(page, target_url)

            # Cookie 按钮（如果有）
            try:
                page.get_by_role("button", name="I Agree").click(timeout=3000)
            except Exception:
                pass

            # 兜底：如果 cons 参数没触发自动搜索，尝试在输入框填入并回车
            try:
                inp = page.get_by_label("shipping tracking")
                inp.fill("")
                inp.fill(cons)
                inp.dispatch_event("input")
                inp.dispatch_event("change")
                try:
                    inp.press("Enter")
                except Exception:
                    pass
                try:
                    page.get_by_role("button", name="Search", exact=True).click(timeout=3000)
                except Exception:
                    pass
            except Exception:
                pass

            # 等待结果区域出现（尽量宽松）
            try:
                page.wait_for_selector("text=Tracking", timeout=15000)
            except Exception:
                pass

            save_debug(page, "zim_done")
        except PWTimeout:
            save_debug(page, "zim_timeout")
            return 1
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
