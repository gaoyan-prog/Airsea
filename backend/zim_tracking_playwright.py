import argparse, json, os, sys, time, re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT_DIR = os.path.dirname(__file__)
DEBUG_DIR = os.path.join(ROOT_DIR, "app", "debug")
USER_DATA_DIR = os.path.join(ROOT_DIR, "app", "userdata_zim")  # ← 固定目录（重要）

def ensure_dir(p): os.makedirs(p, exist_ok=True)
def log(msg): print(f"[zim] {time.strftime('%F %T')} {msg}", file=sys.stderr, flush=True)

def scrape(number: str, headless: bool = True) -> dict:
    ensure_dir(DEBUG_DIR)
    ensure_dir(USER_DATA_DIR)

    url = f"https://www.zim.com/tools/track-a-shipment?consnumber={quote(str(number))}"
    out_png  = os.path.join(DEBUG_DIR, f"zim_{number}_final.png")
    out_html = os.path.join(DEBUG_DIR, f"zim_{number}_final.html")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless,
            viewport={"width": 1366, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        try:
            # 更“像人”的指纹
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ctx.set_default_timeout(25000)
            ctx.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
            })
            for page in ctx.pages:
                page.set_default_timeout(25000)
            page = ctx.new_page()
            page.set_user_agent(ua)

            # 去掉 webdriver 痕迹、补充常见属性
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
            """)

            # 监听 XHR，尝试捕获追踪 JSON（可选）
            captured = {}
            def on_response(resp):
                try:
                    url = resp.url
                    if "track" in url.lower() or "consign" in url.lower():
                        if "application/json" in (resp.headers or {}).get("content-type", ""):
                            captured[url] = resp.json()
                except Exception:
                    pass
            page.on("response", on_response)

            log(f"goto: {url}")
            page.goto(url, wait_until="domcontentloaded")
            try:
                # 处理 Cookie 弹窗（多写几个名字的兜底）
                for name in ["Accept All", "Accept all", "I Agree", "Agree", "Accept"]:
                    btn = page.get_by_role("button", name=name)
                    if btn and btn.is_visible():
                        btn.click(timeout=3000)
                        break
            except Exception:
                pass

            # 等结果渲染：尝试等待常见的追踪结果容器（自己可换成更精确选择器）
            # 例如包含你的提单号/订舱号的文本出现：
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
                page.wait_for_selector(f"text={number}", timeout=15000)
            except Exception:
                # 如果节点等不到，但我们抓到了 XHR，也算成功
                pass

            # 保存页面
            try:
                with open(out_html, "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            page.screenshot(path=out_png, full_page=True)
            log(f"saved screenshot -> {out_png}")

            result = {"status": "ok", "screenshot": out_png}
            if captured:
                # 返回一份抓到的 JSON，方便你后处理
                # 只带第一条，避免过大
                first_url = next(iter(captured))
                result["api_url"] = first_url
                result["data"] = captured[first_url]
            return result

        except PlaywrightTimeoutError as e:
            log(f"timeout: {e}")
            return {"status": "timeout", "error": str(e)}
        except Exception as e:
            log(f"error: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            try:
                ctx.close()
            except Exception:
                pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--number", required=True)
    ap.add_argument("--headless", default="false")
    args = ap.parse_args()
    headless = str(args.headless).lower() not in ("false","0","no")
    print(json.dumps(scrape(args.number, headless=headless), ensure_ascii=False))

if __name__ == "__main__":
    sys.exit(main())
