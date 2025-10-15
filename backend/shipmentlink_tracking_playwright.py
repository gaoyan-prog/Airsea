import argparse
import json
import os
import sys
import time
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[shipmentlink] {ts} {msg}", file=sys.stderr, flush=True)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def scrape(config: dict) -> dict:
    search_url = config.get("search_url")
    choose_xpath = config.get("search_button_choose_xpath")
    consent_xpath = config.get("cookie_consent_xpath")
    search_input_xpath = config.get("search_input_xpath")
    search_button_xpath = config.get("search_button_xpath")
    result_xpath = config.get("result_xpath")
    search_number = config.get("search_number")
    headless = bool(config.get("headless", True))
    manual_verify = bool(config.get("manual_verify", False))
    user_data_dir = config.get("user_data_dir")

    if not search_url or not search_input_xpath or not search_button_xpath or not result_xpath:
        raise ValueError("配置缺少必要字段：search_url / search_input_xpath / search_button_xpath / result_xpath")

    if not user_data_dir:
        user_data_dir = os.path.join(os.path.dirname(__file__), "app", "userdata")
    # 独立会话目录，避免与其它脚本互相锁目录
    provider_root = os.path.join(user_data_dir, "shipmentlink")
    session_dir = os.path.join(provider_root, f"session_{int(time.time()*1000)}_{os.getpid()}")
    ensure_dir(session_dir)

    # 调试目录与快速返回：若已有同单号的缓存结果，直接返回
    debug_dir = os.path.join(os.path.dirname(__file__), "app", "debug")
    ensure_dir(debug_dir)

    def try_read_cached_result() -> dict | None:
        try:
            path = os.path.join(debug_dir, "shipmentlink_result.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if (
                    isinstance(data, dict)
                    and str(data.get("number", "")) == str(search_number)
                    and data.get("status") == "ok"
                    and data.get("result")
                ):
                    out = {
                        "status": "ok",
                        "number": str(search_number),
                        "result": data.get("result"),
                        "clickedChoose": bool(choose_xpath),
                        "clickedSearch": True,
                    }
                    print(json.dumps(out, ensure_ascii=False), flush=True)
                    return out
        except Exception:
            pass
        return None

    cached = try_read_cached_result()
    if cached is not None:
        return cached

    log(f"launch chromium persistent context, headless={headless}, user_data_dir={session_dir}")
    with sync_playwright() as p:
        # debug_dir 已在上方初始化
        context = p.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            record_har_path=os.path.join(debug_dir, "shipmentlink.har")
        )
        try:
            context.set_default_timeout(15000)
            page = context.new_page()
            page.set_default_timeout(15000)
            # 捕获“无效订舱”对话框，立即标记并接受
            invalid = {"flag": False}
            def on_dialog(d):
                try:
                    msg = d.message
                except Exception:
                    msg = ""
                log(f"dialog: {msg}")
                try:
                    d.accept()
                except Exception:
                    pass
                if msg and "Booking No. is not valid" in msg:
                    invalid["flag"] = True
            try:
                page.on("dialog", on_dialog)
                page.on("console", lambda m: log(f"console[{m.type}] {m.text}"))
                page.on("pageerror", lambda e: log(f"pageerror: {e}"))
            except Exception:
                pass
            log(f"goto: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")
            try:
                page.screenshot(path=os.path.join(debug_dir, "shipmentlink_after_goto.png"))
            except Exception:
                pass

            # 优先：显式 cookie_consent_xpath（如果配置提供）
            try:
                if consent_xpath:
                    cx = page.locator(f"xpath={consent_xpath}")
                    if cx.count() > 0 and cx.first.is_visible():
                        cx.first.click(timeout=2000)
                        log("clicked cookie consent via config xpath")
                        try:
                            cx.first.wait_for(state="hidden", timeout=3000)
                        except Exception:
                            pass
            except Exception:
                pass

            # 其次：自动识别 Cookie “Accept All”
            try:
                cand = current_page.get_by_role("button", name=re.compile(r"accept all|agree|同意|接受", re.I))
                if cand.count() > 0:
                    cand.first.click(timeout=2000)
                    log("clicked cookie consent via role-button")
                else:
                    selectors = [
                        'button:has-text("Accept All")',
                        'input[type="button"][value="Accept All"]',
                        '//button[normalize-space()="Accept All"]',
                        '//input[@value="Accept All"]'
                    ]
                    for sel in selectors:
                        try:
                            l = current_page.locator(sel)
                            if l.count() > 0 and l.first.is_visible():
                                l.first.click(timeout=1500)
                                log(f"clicked cookie consent via selector: {sel}")
                                break
                        except Exception:
                            pass
                    # 显式 XPath（你提供的定位）
                    try:
                        xp = current_page.locator("xpath=/html/body/div[8]/div/div/div[3]/button[1]")
                        if xp.count() > 0 and xp.first.is_visible():
                            xp.first.click(timeout=2000)
                            log("clicked cookie consent via explicit xpath")
                            try:
                                xp.first.wait_for(state="hidden", timeout=3000)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass

            # choose step
            current_page = page
            if choose_xpath:
                try:
                    btn = current_page.locator(f"xpath={choose_xpath}")
                    btn.wait_for(timeout=15000)
                    vis, en = btn.is_visible(), btn.is_enabled()
                    log(f"choose button state: visible={vis} enabled={en}")
                    log("click choose button ...")
                    new_page = None
                    try:
                        with context.expect_page(timeout=5000) as pinfo:
                            btn.click()
                        new_page = pinfo.value
                        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        current_page = new_page
                        log("detected new page after choose click")
                    except Exception:
                        try:
                            btn.click()
                            current_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                except Exception:
                    log("choose button not present or not clickable, continue")

            # input number
            current_page.locator(f"xpath={search_input_xpath}").wait_for(timeout=20000)
            current_page.locator(f"xpath={search_input_xpath}").fill(str(search_number))
            log(f"filled search number: {search_number}")
            try:
                current_page.screenshot(path=os.path.join(debug_dir, "shipmentlink_after_fill.png"))
            except Exception:
                pass

            # 移除阻塞式人工验证，避免并发时卡住

            # search click（无阻塞导航，后续显式等待结果）
            search_btn = current_page.locator(f"xpath={search_button_xpath}")
            log(f"search button state: visible={search_btn.is_visible()} enabled={search_btn.is_enabled()}")
            log("click search button ...")
            try:
                search_btn.click(no_wait_after=True)
            except Exception:
                # 重试一次
                try:
                    current_page.wait_for_timeout(200)
                    search_btn.click(no_wait_after=True)
                except Exception as e:
                    return {"status": "error", "error": str(e)}

            # 若弹出“无效订舱”对话框，则立即结束为无结果
            try:
                current_page.wait_for_timeout(300)
            except Exception:
                pass
            if invalid["flag"]:
                return {"status": "invalid", "error": "Booking No. is not valid"}

            # wait result on same page (no new tab expected)
            locator = current_page.locator(f"xpath={result_xpath}")
            locator.wait_for(timeout=60000)
            try:
                current_page.screenshot(path=os.path.join(debug_dir, "shipmentlink_before_read_result.png"))
            except Exception:
                pass
            result_text = locator.text_content(timeout=10000)
            if result_text is not None:
                result_text = result_text.strip()

            # 若页面读取不到结果，兜底读取调试 JSON 返回给前端
            if not result_text:
                try:
                    path = os.path.join(debug_dir, "shipmentlink_result.json")
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if (
                            isinstance(data, dict)
                            and str(data.get("number", "")) == str(search_number)
                            and data.get("status") == "ok"
                            and data.get("result")
                        ):
                            result_text = str(data.get("result")).strip()
                            log("fallback to cached shipmentlink_result.json")
                except Exception:
                    pass

            log(f"result: {result_text}")
            out = {
                "status": "ok",
                "number": str(search_number),
                "result": result_text,
                "clickedChoose": bool(choose_xpath),
                "clickedSearch": True,
            }
            # stdout 一行 JSON + flush
            print(json.dumps(out, ensure_ascii=False), flush=True)
            # debug file
            debug_dir = os.path.join(os.path.dirname(__file__), "app", "debug")
            ensure_dir(debug_dir)
            with open(os.path.join(debug_dir, "shipmentlink_result.json"), "w", encoding="utf-8") as f:
                json.dump({"timestamp": datetime.now().isoformat(), **out}, f, ensure_ascii=False, indent=2)
            return out
        except PlaywrightTimeoutError as e:
            try:
                page.screenshot(path=os.path.join(debug_dir, "shipmentlink_timeout.png"))
            except Exception:
                pass
            return {"status": "timeout", "error": str(e)}
        except Exception as e:
            try:
                page.screenshot(path=os.path.join(debug_dir, "shipmentlink_error.png"))
            except Exception:
                pass
            return {"status": "error", "error": str(e)}
        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="ShipmentLink tracking scraper using Playwright")
    parser.add_argument("--config", default=os.path.join("backend", "app", "config", "shipmentlink.json"),
                        help="path to json config")
    parser.add_argument("--number", help="override search_number from config", default=None)
    args = parser.parse_args()

    cfg_path = args.config
    if not os.path.isabs(cfg_path):
        root = os.path.dirname(os.path.dirname(__file__))
        cfg_path = os.path.abspath(os.path.join(root, os.path.relpath(cfg_path)))

    log(f"using config: {cfg_path}")
    config = load_config(cfg_path)
    if args.number:
        config["search_number"] = str(args.number)
        log(f"override search_number via --number: {config['search_number']}")

    _ = scrape(config)


if __name__ == "__main__":
    sys.exit(main())


