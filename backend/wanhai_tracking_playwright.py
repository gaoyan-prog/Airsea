import argparse
import json
import os
import sys
import time
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def normalize_date_text(s: str) -> str:
                import re
                s = (s or '').strip()
                if not s: return s
                s = re.sub(r"\(.*?\)", "", s)  # remove (Local Time) etc.
                s = s.replace('/', '-').replace(',', ' ').strip()
                m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
                if m:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                months = {'JAN':'01','FEB':'02','MAR':'03','APR':'04','MAY':'05','JUN':'06','JUL':'07','AUG':'08','SEP':'09','OCT':'10','NOV':'11','DEC':'12'}
                su = s.upper()
                m = re.match(r"^([0-3]?\d)[-\s](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s](\d{4})$", su)
                if m:
                    return f"{m.group(3)}-{months[m.group(2)]}-{int(m.group(1)):02d}"
                m = re.match(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s]([0-3]?\d)[-\s](\d{4})$", su)
                if m:
                    return f"{m.group(3)}-{months[m.group(1)]}-{int(m.group(2)):02d}"
                return s

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 将日志写到 stderr，避免干扰 stdout 的 JSON
    print(f"[wanhai] {ts} {msg}", file=sys.stderr, flush=True)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

# --- 工具：打印链接信息 ---
def debug_link_info(p, el):
    try:
        href = p.evaluate("e => e.getAttribute('href')", el)
        onclick = p.evaluate("e => e.getAttribute('onclick')", el)
        tgt  = p.evaluate("e => e.target || ''", el)
        rect = p.evaluate("e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,vis:!!(e.offsetParent)}}", el)
        log(f"link info: href={href} onclick={onclick} target={tgt} rect={rect}")
    except Exception as e:
        log(f"link info failed: {e}")
def click_detail_link(curr_page, link_locator, ctx):
    el = link_locator.first
    try:
        link_locator.first.scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass
    debug_link_info(curr_page, el)

    # 1) 同页导航优先
    try:
        curr_page.evaluate("e => e.target = '_self'", el)
    except Exception:
        pass
    try:
        with curr_page.expect_navigation(timeout=12000):
            el.click()
        log(f"same-page navigation to {curr_page.url}")
        return curr_page
    except Exception as e:
        log(f"no same-page nav: {e}")

    # 2) 弹窗
    try:
        with curr_page.expect_popup(timeout=8000) as pinfo:
            el.click()
        new_pg = pinfo.value
        new_pg.wait_for_load_state("domcontentloaded", timeout=15000)
        log(f"popup opened: {new_pg.url}")
        return new_pg
    except Exception as e:
        log(f"no popup: {e}")

    # 3) 直接执行 onclick / 跟随 href
    try:
        onclick = curr_page.evaluate("e => e.getAttribute('onclick')", el)
        if onclick:
            log(f"eval onclick: {onclick[:120]}")
            curr_page.evaluate("(el)=>{el.target='_self'; el.click();}", el)
            try:
                curr_page.wait_for_load_state("domcontentloaded", timeout=12000)
            except Exception:
                pass
            return curr_page
    except Exception as e:
        log(f"onclick eval failed: {e}")

    try:
        href = curr_page.evaluate("e => e.getAttribute('href')", el)
        if href and href != '#':
            abs_url = curr_page.evaluate("(u)=>new URL(u, location.href).toString()", href)
            log(f"goto href: {abs_url}")
            curr_page.goto(abs_url, wait_until="domcontentloaded")
            return curr_page
    except Exception as e:
        log(f"goto href failed: {e}")

    log("click attempts exhausted for this link")
    return None
def scrape(config: dict) -> dict:
    
    search_url = config.get("search_url")
    search_input_xpath = config.get("search_input_xpath")
    search_button_xpath = config.get("search_button_xpath")
    more_details_button_xpath = config.get("more_details_button_xpath")
    list_bl_data_xpath = config.get("list_bl_data_xpath")  # 列表页中的 B/L Data 按钮（可选）
    result_xpath = config.get("result_xpath")
    search_number = config.get("search_number")
    headless = bool(config.get("headless", True))
    manual_verify = bool(config.get("manual_verify", False))
    user_data_dir = config.get("user_data_dir")

    if not search_url or not search_input_xpath or not search_button_xpath or not result_xpath:
        raise ValueError("配置缺少必要字段：search_url / search_input_xpath / search_button_xpath / result_xpath")
    if not more_details_button_xpath:
        raise ValueError("配置缺少必要字段：more_details_button_xpath")

    if not user_data_dir:
        # fallback 到项目内目录
        user_data_dir = os.path.join(os.path.dirname(__file__), "app", "userdata")
    # 为每次运行创建独立会话目录，避免并发互相锁定/干扰
    provider_root = os.path.join(user_data_dir, "wanhai")
    session_dir = os.path.join(provider_root, f"session_{int(time.time()*1000)}_{os.getpid()}")
    ensure_dir(session_dir)

    # 调试目录（用于截图与 HAR）
    debug_dir = os.path.join(os.path.dirname(__file__), "app", "debug")
    ensure_dir(debug_dir)

    # 仅保留 after_open_detail 的多页面截图
    only_detail_snaps = True

    # 通用截图工具：为每一步保存带序号和编号的截图
    screenshot_seq = 0
    def _san_label(s: str) -> str:
        try:
            return re.sub(r"[^a-zA-Z0-9._-]+", "_", str(s))[:80]
        except Exception:
            return "snap"
    def snap(page, label: str):
        nonlocal screenshot_seq
        if only_detail_snaps and not str(label).startswith("all_after_open_detail__"):
            return None
        try:
            screenshot_seq += 1
            fname = f"wanhai_{str(search_number)}_{screenshot_seq:03d}_{_san_label(label)}.png"
            out_path = os.path.join(debug_dir, fname)
            page.screenshot(path=out_path, full_page=True)
            return out_path
        except Exception:
            return None

    log(f"launch chromium persistent context, headless={headless}, user_data_dir={session_dir}")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            record_har_path=os.path.join(debug_dir, "wanhai.har")
        )
        # 截取当前上下文内所有已打开页面的工具
        def snap_all_pages(label: str) -> None:
            try:
                for idx, pg in enumerate(context.pages):
                    try:
                        url_ok = getattr(pg, "url", None)
                        if url_ok and url_ok != "about:blank":
                            snap(pg, f"all_{label}__{idx}")
                    except Exception:
                        continue
            except Exception:
                pass
        # 监听新页面出现，自动截图（禁用，避免产生非 after_open_detail 的截图）
        try:
            def _on_new_page(pg):
                return
            context.on("page", _on_new_page)
        except Exception:
            pass
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            log("tracing started")
        except Exception as e:
            log(f"tracing start failed: {e}")
        
        # 等待页面从加载态恢复为稳定态的工具（解决截图时仍在转圈的问题）
        def _is_loader_visible(pg) -> bool:
            try:
                res = pg.evaluate(
                    """
                    () => {
                        const visible = el => el && !!(el.offsetParent);
                        const sels = [
                          '.ui-widget-overlay', '.ui-blockui', '.ui-blockui-content', '.blockUI',
                          '.loading', '.spinner', '.fa-spinner', 'img[src*="loading"]'
                        ];
                        for (const s of sels) {
                          const el = document.querySelector(s);
                          if (visible(el)) return true;
                        }
                        return false;
                    }
                    """
                )
                return bool(res)
            except Exception:
                return False

        def wait_page_stable(pg, max_wait_sec: int = 12):
            deadline = time.time() + max_wait_sec
            last_len = -1
            stable_hits = 0
            while time.time() < deadline:
                try:
                    pg.wait_for_load_state('domcontentloaded', timeout=1500)
                except Exception:
                    pass
                try:
                    pg.wait_for_load_state('networkidle', timeout=1200)
                except Exception:
                    pass
                try:
                    cur_len = pg.evaluate("() => (document.body && document.body.innerText || '').length")
                except Exception:
                    cur_len = -1
                has_loader = _is_loader_visible(pg)
                if not has_loader and cur_len == last_len and cur_len > 0:
                    stable_hits += 1
                    if stable_hits >= 2:
                        break
                else:
                    stable_hits = 0
                last_len = cur_len
                time.sleep(0.4)
        try:
            context.set_default_timeout(15000)
            page = context.new_page()
            page.set_default_timeout(15000)
            try:
                page.on("dialog", lambda d: (log(f"dialog: {d.message}"), d.accept()))
                page.on("console", lambda m: log(f"console[{m.type}] {m.text}"))
                page.on("pageerror", lambda e: log(f"pageerror: {e}"))
            except Exception:
                pass

            start_ts = time.time()
            def elapsed_ms() -> int:
                try:
                    return int((time.time() - start_ts) * 1000)
                except Exception:
                    return -1
            def expired(limit: int = 90) -> bool:
                return (time.time() - start_ts) > limit
            log(f"goto: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")
            # 禁用早期截图：wanhai_after_goto.png
            snap(page, "after_goto")

            # 等待与输入
            page.locator(f"xpath={search_input_xpath}").wait_for(timeout=15000)
            page.locator(f"xpath={search_input_xpath}").fill(str(search_number))
            log(f"filled search number: {search_number}")
            # 禁用早期截图：wanhai_after_fill.png
            snap(page, "after_fill")

            # 点击前记录页面信息
            try:
                page_title_before = page.title()
            except Exception:
                page_title_before = ""
            url_before = page.url
            log(f"before search click: url={url_before} title={page_title_before}")

            # 第一次点击：查询按钮，可能新开窗口或当前页跳转
            search_btn = page.locator(f"xpath={search_button_xpath}")
            vis = search_btn.is_visible()
            en = search_btn.is_enabled()
            log(f"search button state: visible={vis} enabled={en}")
            log("click search button ...")
            new_page = None
            clicked_search_ok = False
            # 优先捕获新页
            try:
                with context.expect_page(timeout=8000) as pinfo:
                    search_btn.click()
                new_page = pinfo.value
                new_page.wait_for_load_state("domcontentloaded", timeout=30000)
                clicked_search_ok = True
                log("new page opened after search click")
                snap(new_page, "popup_after_search")
            except Exception as e:
                log(f"no new page after search click: {e}")
                # 退回本页导航
                try:
                    with page.expect_navigation(timeout=15000):
                        search_btn.click()
                    clicked_search_ok = True
                    log("navigated on same page after search click")
                    snap(page, "after_search_nav")
                except Exception as e2:
                    log(f"no navigation after search click, fallback no_wait_after: {e2}")
                    try:
                        search_btn.click(no_wait_after=True)
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                        clicked_search_ok = True
                        snap(page, "after_search_nowait")
                    except Exception as e3:
                        log(f"search click failed: {e3}")
            current_page = new_page or page
            # 禁用早期截图：wanhai_after_search_click.png
            snap_all_pages("after_search_click")

            # 点击后记录页面信息
            try:
                cur_title = current_page.title()
            except Exception:
                cur_title = ""
            log(f"after search click: new_page={bool(new_page)} url={current_page.url} title={cur_title} clicked_ok={clicked_search_ok}")

            # 第二次点击：更多详情（优先点击 "B/L Data"/"Booking Data"），同样可能新开窗口或当前页跳转
            final_page = None
            clicked_more_ok = False
            # 多策略查找 detail 链接
            link_clicked = False
            # === 调试：打印当前页所有可见含 Data/Detail 的元素，方便看为什么点不到 ===
            try:
                names = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a,button'))
                        .filter(el => el.offsetParent !== null)
                        .map(el => (el.innerText||'').trim())
                        .filter(t => /data|detail/i.test(t))
                        .slice(0,50)
                """)
                log(f"visible action texts: {names}")
            except Exception:
                pass
            # === 调试结束 ===
            # 跟踪这次点击对应的 ref_type（B/L=MFT，Booking=BKG）
            ref_type_detected = "MFT"
            clicked_kind = None
            try:
                patterns = [(r"B\s*/?\s*L\s*Data", "MFT"),
                            (r"Booking\s*Data",     "BKG")]
                for pat, tag in patterns:
                    try:
                        link = current_page.get_by_role("link", name=re.compile(pat, re.I))
                        cnt = link.count()
                        log(f"detail link '{pat}' count={cnt}")
                        if cnt > 0:
                            ref_type_detected = tag
                            clicked_kind = pat
                            try:
                                link.first.scroll_into_view_if_needed(timeout=2000)
                            except Exception:
                                pass
                            # 依次尝试：popup → navigation → href goto
                            el = link.first
                            try:
                                with current_page.expect_popup(timeout=8000) as ppop:
                                    el.click()
                                final_page = ppop.value
                                final_page.wait_for_load_state("domcontentloaded", timeout=30000)
                                clicked_more_ok = True
                                link_clicked = True
                                log("opened popup after detail link click")
                                snap(final_page, "popup_after_detail")
                            except Exception as e_pop:
                                log(f"no popup on detail link: {e_pop}")
                                if not link_clicked:
                                    try:
                                        try:
                                            current_page.evaluate("el => el.target='_self'", el)
                                        except Exception:
                                            pass
                                        with current_page.expect_navigation(timeout=15000):
                                            el.click()
                                        clicked_more_ok = True
                                        link_clicked = True
                                        log("navigated on same page after detail link click")
                                        snap(current_page, "after_detail_nav")
                                    except Exception as e_nav:
                                        log(f"no navigation after detail link: {e_nav}")
                            if not link_clicked:
                                try:
                                    href = current_page.evaluate("el => el.href || el.getAttribute('href')", el)
                                    if href and href != '#':
                                        current_page.goto(href, wait_until="domcontentloaded")
                                        clicked_more_ok = True
                                        link_clicked = True
                                        log(f"goto href after detail link: {href}")
                                        snap(current_page, "after_detail_goto")
                                except Exception as e_goto:
                                    log(f"goto href failed: {e_goto}")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if not link_clicked:
                # 退回 XPath
                try:
                    log("wait more-details button (xpath) ...")
                    current_page.locator(f"xpath={more_details_button_xpath}").wait_for(timeout=15000)
                    more_btn = current_page.locator(f"xpath={more_details_button_xpath}")
                    m_vis = more_btn.is_visible()
                    m_en = more_btn.is_enabled()
                    log(f"more-details button state: visible={m_vis} enabled={m_en}")
                    # 捕捉 popup → 本页导航 → href goto
                    el2 = more_btn.first
                    try:
                        with current_page.expect_popup(timeout=8000) as ppop2:
                            el2.click()
                        final_page = ppop2.value
                        final_page.wait_for_load_state("domcontentloaded", timeout=30000)
                        clicked_more_ok = True
                        log("opened popup after more-details click")
                        snap(final_page, "popup_after_more_details")
                    except Exception as e:
                        log(f"no popup after more-details click: {e}")
                        try:
                            try:
                                current_page.evaluate("el => el.target='_self'", el2)
                            except Exception:
                                pass
                            with current_page.expect_navigation(timeout=15000):
                                el2.click()
                            clicked_more_ok = True
                            log("navigated on same page after more-details click")
                            snap(current_page, "after_more_details_nav")
                        except Exception as e2:
                            log(f"no navigation after more-details, try goto href: {e2}")
                            try:
                                href2 = current_page.evaluate("el => el.href || el.getAttribute('href')", el2)
                                if href2 and href2 != '#':
                                    current_page.goto(href2, wait_until="domcontentloaded")
                                    clicked_more_ok = True
                                    log(f"goto href after more-details: {href2}")
                                    snap(current_page, "after_more_details_goto")
                            except Exception as e3:
                                log(f"goto href failed: {e3}")
                except Exception as e:
                    log(f"xpath more-details click error: {e}")
                    # 最后兜底：JS 查找包含文本的链接
                    try:
                        current_page.evaluate("""
                            () => {
                              const as = Array.from(document.querySelectorAll('a'));
                              const target = as.find(a => /B\s*\/?.?\s*L\s*Data|Booking\s*Data/i.test(a.textContent||''));
                              if (target) { target.click(); return true; }
                              return false;
                            }
                        """)
                        clicked_more_ok = True
                    except Exception:
                        pass

            # 如果新开了页，切换；否则沿用当前页
            try:
                candidate = next((pg for pg in context.pages if pg is not current_page and pg.url != "about:blank"), None)
                if candidate:
                    final_page = candidate
                    snap(candidate, "candidate_selected")
            except Exception:
                pass
            last_page = final_page or current_page
            try:
                last_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            snap(last_page, "after_last_page_ready")
            # 如果当前是列表页（tracking_data_list），继续点击 "B/L Data" 进入详情页
            # 如果当前是列表页（tracking_data_list），继续点击 "B/L Data" 进入详情页
            # ========= PATCH: 强化版 - 打开 B/L Data 详情页 =========
            try:
                if re.search(r"tracking_data_list", (last_page.url or ""), re.I):
                    log("list page detected, trying to open 'B/L Data' detail page ...")

                    clicked = False
                    found_detail = None

                    # Step 1️⃣: 尝试直接调用 JS 函数 formblSubmit(ref_no,'MFT')
                    try:
                        ok_eval = last_page.evaluate("""
                            (refNo, rt) => {
                                try {
                                    if (typeof window.formblSubmit === 'function') {
                                        window.formblSubmit(refNo, rt);
                                        return true;
                                    }
                                    return false;
                                } catch(e) { return false; }
                            }
                        """, str(search_number), ref_type_detected)
                        if ok_eval:
                            clicked = True
                            log(f"invoked window.formblSubmit(ref_no,'{ref_type_detected}')")

                    except Exception as e:
                        log(f"formblSubmit invoke error: {e}")

                    # Step 2️⃣: 如果页面函数没执行，就尝试点击“B/L Data”链接
                    if not clicked:
                        try:
                            if list_bl_data_xpath:
                                bl_btn = last_page.locator(f"xpath={list_bl_data_xpath}")
                                if bl_btn.count() > 0:
                                    bl_btn.first.scroll_into_view_if_needed(timeout=2000)
                                    with last_page.context.expect_page(timeout=8000) as ppop:
                                        bl_btn.first.click()
                                    found_detail = ppop.value
                                    clicked = True
                                    log("clicked list B/L via config xpath -> popup appeared")
                            if not clicked:
                                xp = "//a[contains(normalize-space(.),'B/L Data')]"
                                l = last_page.locator(f"xpath={xp}")
                                if l.count() > 0:
                                    l.first.scroll_into_view_if_needed(timeout=2000)
                                    with last_page.context.expect_page(timeout=8000) as ppop2:
                                        l.first.click()
                                    found_detail = ppop2.value
                                    clicked = True
                                    log("clicked list B/L via fallback xpath -> popup appeared")
                        except Exception as e:
                            log(f"click B/L link error: {e}")

                    # Step 3️⃣: 等待 JS 打开的弹窗
                    if clicked and not found_detail:
                        log("waiting for popup detail window (including JS-opened) ...")
                        target_url_part = "tracking_data_page_by_bl_redirect"
                        for _ in range(12):  # 最多12秒
                            for p in context.pages:
                                if target_url_part in (p.url or ""):
                                    found_detail = p
                                    break
                            if found_detail:
                                break
                            time.sleep(1)

                    # Step 4️⃣: 如果仍未检测到弹窗，强制构造 URL 跳转
                    # Step 4️⃣: 如果仍未检测到弹窗，强制构造 URL 跳转
                    if not found_detail:
                        try:
                            # 第一层：旧的中转页（可能立即302跳回列表）
                            redirect_page = ("tracking_data_page_by_bl_redirect"
                                             if ref_type_detected == "MFT"
                                             else "tracking_data_page_by_booking_redirect")
                            forced_url = (
                                f"https://www.wanhai.com/views/cargo_track_v2/"
                                f"{redirect_page}.xhtml?ref_no={search_number}&ref_type={ref_type_detected}"
                            )
                            log(f"force goto detail page: {forced_url}")
                            last_page.goto(forced_url, wait_until="domcontentloaded", timeout=20000)
                            log("force goto success (detail page in same tab)")
                            snap(last_page, "after_force_redirect")

                            # ⚠️ 第二层：直接跳真正的结果页（绕过redirect）
                            real_detail_url = (
                                f"https://www.wanhai.com/views/cargo_track_v2/"
                                f"tracking_data_page.xhtml?ref_no={search_number}&ref_type={ref_type_detected}"
                            )
                            log(f"manual goto REAL detail page: {real_detail_url}")
                            last_page.goto(real_detail_url, wait_until="domcontentloaded", timeout=25000)
                            log("navigated to REAL detail page successfully")
                            snap(last_page, "after_force_real_detail")

                        except Exception as e:
                            log(f"force goto REAL detail page failed: {e}")

                    # Step 5️⃣: 调试截图
                    # 保留 after_open_detail 的多页面快照，由 snap_all_pages 统一生成

            except Exception as e:
                log(f"list B/L open section failed: {e}")
            # ========= PATCH END =========


            # 不再依赖 URL 变化；Wan Hai 常为 JSF 同页局部更新
            # 禁用早期截图：wanhai_after_more_details.png

            try:
                last_title = last_page.title()
            except Exception:
                last_title = ""
            # 记录 frame 信息，便于排查
            try:
                frs = getattr(last_page, "frames", [])
                log(f"final page frames: count={len(frs)} urls={[getattr(f, 'url', None) for f in frs][:5]}")
            except Exception:
                pass
            log(f"after more-details click: new_page={bool(final_page)} url={last_page.url} title={last_title} clicked_ok={clicked_more_ok}")

            # URL 守卫：若误落回查询页，则强制走同页导航重试一次（先 B/L Data 再 Booking Data）
            
            # ========= FINAL PATCH: 稳定版 打开 B/L Data 并强制进入真实页面 =========
            try:
                if re.search(r"tracking_data_list", (last_page.url or ""), re.I):
                    log("list page detected, trying to open 'B/L Data' detail page ...")

                    clicked = False
                    found_detail = None

                    # Step 1️⃣: 调用 JS 函数 formblSubmit(ref_no,'MFT')
                    try:
                        ok_eval = last_page.evaluate("""
                            (refNo, rt) => {
                                try {
                                    if (typeof window.formblSubmit === 'function') {
                                        window.formblSubmit(refNo, rt);
                                        return true;
                                    }
                                    return false;
                                } catch(e) { return false; }
                            }
                        """, str(search_number), ref_type_detected)
                        if ok_eval:
                            clicked = True
                            log(f"invoked window.formblSubmit(ref_no,'{ref_type_detected}')")

                    except Exception as e:
                        log(f"formblSubmit invoke error: {e}")

                    # Step 2️⃣: 尝试点击 "B/L Data" 链接
                    if not clicked:
                        try:
                            xp = "//a[contains(normalize-space(.),'B/L Data')]"
                            l = last_page.locator(f"xpath={xp}")
                            if l.count() > 0:
                                l.first.scroll_into_view_if_needed(timeout=2000)
                                with last_page.context.expect_page(timeout=8000) as ppop:
                                    l.first.click()
                                found_detail = ppop.value
                                clicked = True
                                log("clicked list B/L via fallback xpath -> popup appeared")
                                snap(found_detail, "detail_popup_v2")
                        except Exception as e:
                            log(f"click B/L link error: {e}")

                    # Step 3️⃣: 等待 window.open 弹窗
                    if clicked and not found_detail:
                        log("waiting for popup detail window (including JS-opened) ...")
                        target_url_part = "tracking_data_page_by_bl_redirect"
                        for _ in range(12):
                            for p in context.pages:
                                if target_url_part in (p.url or ""):
                                    found_detail = p
                                    break
                            if found_detail:
                                break
                            time.sleep(1)

                    # Step 4️⃣: 如果仍未检测到弹窗 -> 强制进入真实页面
                    if not found_detail:
                        try:
                            redirect_page = ("tracking_data_page_by_bl_redirect"
                                             if ref_type_detected == "MFT"
                                             else "tracking_data_page_by_booking_redirect")
                            forced_url = (
                                f"https://www.wanhai.com/views/cargo_track_v2/"
                                f"{redirect_page}.xhtml?ref_no={search_number}&ref_type={ref_type_detected}"
                            )
                            log(f"force goto redirect page: {forced_url}")
                            last_page.goto(forced_url, wait_until="domcontentloaded", timeout=20000)
                            log("force goto redirect success")
                            snap(last_page, "after_force_redirect_v2")

                            # 直接进入真实页面（绕过redirect）
                            real_detail_url = (
                                f"https://www.wanhai.com/views/cargo_track_v2/"
                                f"tracking_data_page.xhtml?ref_no={search_number}&ref_type={ref_type_detected}"
                            )
                            log(f"manual goto REAL detail page: {real_detail_url}")
                            last_page.goto(real_detail_url, wait_until="domcontentloaded", timeout=25000)
                            log("navigated to REAL detail page successfully")
                            snap(last_page, "after_force_real_detail_v2")

                            # 🔍 调试截图
                            # 禁用早期截图：wanhai_after_real_detail.png

                        except Exception as e:
                            log(f"force goto REAL detail page failed: {e}")
                    else:
                        log(f"found new detail page: {found_detail.url}")
                        last_page = found_detail
                        try:
                            last_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass

                    # Step 5️⃣: 调试截图
                    # 保留 after_open_detail 的多页面快照，由 snap_all_pages 统一生成

            except Exception as e:
                log(f"list B/L open section failed: {e}")
            # ========= FINAL PATCH END =========

            # ✅ fallback：若 ETA 未出现在列表页，立即强制进入真实 detail 页面
            try:
                if re.search(r"tracking_data_list", (last_page.url or ""), re.I):
                    def extract_eta_from_list(page):
                        try:
                            page.wait_for_selector("table.ui-datatable, .ui-datatable-tablewrapper table", timeout=8000)
                        except Exception:
                            return '', 'datatable not found'

                        js = """
                        () => {
                        const norm = s => (s||'').replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim().toUpperCase();
                        const wrap = document.querySelector('.ui-datatable-tablewrapper') || document;
                        const table = wrap.querySelector('table');
                        if (!table) return ['', 'no table'];
                        const ths = Array.from(table.querySelectorAll('thead th'));
                        const isETA = (t) => {
                            const x = norm(t);
                            return x === 'ETA' || (x.includes('EST') && x.includes('ARRIVAL'));
                        };
                        let etaIdx = -1;
                        ths.forEach((th,i)=>{ if (etaIdx<0 && isETA(th.textContent||'')) etaIdx = i; });
                        if (etaIdx < 0) return ['', 'eta header not found'];
                        const rows = Array.from(table.querySelectorAll('tbody tr')).filter(r => r.offsetParent !== null);
                        if (!rows.length) return ['', 'no rows'];
                        const tds = Array.from(rows[0].querySelectorAll('td'));
                        if (!tds.length || etaIdx >= tds.length) return ['', 'eta td out of range'];
                        const val = (tds[etaIdx].textContent||'').replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
                        return [val, 'ok'];
                        }
                        """
                        try:
                            eta_text, reason = page.evaluate(js)
                            if eta_text:
                                return eta_text, 'ok'
                            return '', reason
                        except Exception as e:
                            return '', f'eval error: {e}'

                    eta_from_list, why = extract_eta_from_list(last_page)
                    if not eta_from_list:
                        log(f"list page ETA not found: {why}; fallback to detail/poller strategy")
                        try:
                            real_detail_url = (
                                f"https://www.wanhai.com/views/cargo_track_v2/"
                                f"tracking_data_page.xhtml?ref_no={search_number}&ref_type={ref_type_detected}"
                            )
                            log(f"fallback: manually goto REAL detail page: {real_detail_url}")
                            last_page.goto(real_detail_url, wait_until="domcontentloaded", timeout=25000)
                            log("fallback: navigated to REAL detail page successfully")
                            # 禁用早期截图：wanhai_after_real_detail_fallback.png
                        except Exception as e:
                            log(f"fallback: manual goto REAL detail failed: {e}")
            except Exception as e:
                log(f"list ETA extraction failed: {e}")
            # ========= FINAL PATCH END =========

            # 列表页优先：若当前为 tracking_data_list.xhtml，先尝试直接从列表表格提取 ETA
            try:
                if re.search(r"tracking_data_list", (last_page.url or ""), re.I):
                    def extract_eta_from_list(page):
                        # 返回 (eta_text, debug)；找不到返回 ('', why)
                        try:
                            page.wait_for_selector("table.ui-datatable, .ui-datatable-tablewrapper table", timeout=8000)
                        except Exception:
                            return '', 'datatable not found'

                        js = """
                        () => {
                          const norm = s => (s||'').replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim().toUpperCase();
                          const wrap = document.querySelector('.ui-datatable-tablewrapper') || document;
                          const table = wrap.querySelector('table');
                          if (!table) return ['', 'no table'];
                          const ths = Array.from(table.querySelectorAll('thead th'));
                          if (!ths.length) return ['', 'no thead'];
                          // 找 ETA 列，兼容 "ETA", "EST ARRIVAL", "EST. ARRIVAL", "ESTIMATED ARRIVAL"
                          const isETA = (t) => {
                            const x = norm(t);
                            return x === 'ETA' || (x.includes('EST') && x.includes('ARRIVAL'));
                          };
                          let etaIdx = -1;
                          ths.forEach((th,i)=>{ if (etaIdx<0 && isETA(th.textContent||'')) etaIdx = i; });
                          if (etaIdx < 0) return ['', 'eta header not found'];

                          const rows = Array.from(table.querySelectorAll('tbody tr')).filter(r => r.offsetParent !== null);
                          if (!rows.length) return ['', 'no rows'];
                          // 取第一条或包含 “B/L No” 匹配的行，这里先拿第一条
                          const tds = Array.from(rows[0].querySelectorAll('td'));
                          if (!tds.length || etaIdx >= tds.length) return ['', 'eta td out of range'];
                          const val = (tds[etaIdx].textContent||'').replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
                          return [val, 'ok'];
                        }
                        """
                        try:
                            eta_text, reason = page.evaluate(js)
                            if eta_text:
                                return eta_text, 'ok'
                            return '', reason
                        except Exception as e:
                            return '', f'eval error: {e}'

                    eta_from_list, why = extract_eta_from_list(last_page)
                    if eta_from_list:
                        # 规范化并直接返回
                        def _norm_list_date(s: str) -> str:
                            s = (s or '').strip()
                            if not s:
                                return s
                            s = re.sub(r"\(.*?\)", "", s)
                            s = s.replace('/', '-').replace(',', ' ').strip()
                            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
                            if m:
                                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                            months = {'JAN':'01','FEB':'02','MAR':'03','APR':'04','MAY':'05','JUN':'06','JUL':'07','AUG':'08','SEP':'09','OCT':'10','NOV':'11','DEC':'12'}
                            su = s.upper()
                            m = re.match(r"^([0-3]?\d)[-\s](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s](\d{4})$", su)
                            if m:
                                return f"{m.group(3)}-{months[m.group(2)]}-{int(m.group(1)):02d}"
                            m = re.match(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s]([0-3]?\d)[-\s](\d{4})$", su)
                            if m:
                                return f"{m.group(3)}-{months[m.group(1)]}-{int(m.group(2)):02d}"
                            return s

                        before_norm = eta_from_list
                        eta_norm = _norm_list_date(eta_from_list)
                        log(f"ETA from list: before='{before_norm}' after='{eta_norm}'")
                        out_obj = {
                            "status": "ok",
                            "number": str(search_number),
                            "result": eta_norm,
                            "clickedSearch": clicked_search_ok,
                            "clickedMoreDetails": clicked_more_ok,
                        }
                        print(json.dumps(out_obj, ensure_ascii=False), flush=True)
                        out_file = os.path.join(debug_dir, "wanhai_result.json")
                        with open(out_file, "w", encoding="utf-8") as f:
                            json.dump({"timestamp": datetime.now().isoformat(), **out_obj}, f, ensure_ascii=False, indent=2)
                        log(f"written debug: {out_file}")
                        return out_obj
                    else:
                        log(f"list page ETA not found: {why}; fallback to detail/poller strategy")
            except Exception:
                pass
            # ---- 强制打开详情页的工具函数（放在守卫前面）----
            def open_detail_via_query_form(pg, ref_no: str, ref_type: str):
                try:
                    pg.wait_for_selector("#cargoType", timeout=8000)
                    # 对于 Booking/BL 都选 value=2（Book No. / BL no.）
                    try:
                        pg.select_option("#cargoType", "2")
                    except Exception:
                        pg.evaluate("() => document.getElementById('cargoType').value='2'")
                    # 填编号
                    try:
                        pg.fill("#q_ref_no1", ref_no)
                    except Exception:
                        pg.evaluate("(v)=>{const el=document.getElementById('q_ref_no1'); if(el){el.value=v;}}", ref_no)

                    # Query 按钮会 target=_blank -> 新开页
                    try:
                        with pg.context.expect_page(timeout=20000) as pinfo:
                            pg.click("input#Query")
                        np = pinfo.value
                        np.wait_for_load_state("domcontentloaded", timeout=25000)
                        log(f'query form opened new page: {np.url}')
                        return np
                    except Exception as e1:
                        log(f"query click no new page: {e1}")
                        # 兜底：同页导航
                        try:
                            with pg.expect_navigation(timeout=20000):
                                pg.click("input#Query")
                            log("query form navigated on same page")
                            return pg
                        except Exception as e2:
                            log(f"query same-page nav failed: {e2}")
                            # 终极兜底：直接调用 mojarra.jsfcljs
                            try:
                                pg.evaluate("""
                                    () => {
                                        const f = document.getElementById('cargoTrackV2Bean');
                                        if (f && window.mojarra && window.mojarra.jsfcljs) {
                                            window.mojarra.jsfcljs(f, {'Query':'Query','skipValidate':'true'}, '');
                                        }
                                    }
                                """)
                                # 再试抓新页
                                try:
                                    with pg.context.expect_page(timeout=20000) as p2:
                                        pass
                                except Exception:
                                    pass
                                # 等待任意可见结果表/详情
                                pg.wait_for_load_state("domcontentloaded", timeout=20000)
                                return pg
                            except Exception as e3:
                                log(f"mojarra submit failed: {e3}")
                                return None
                except Exception as e:
                    log(f"open_detail_via_query_form error: {e}")
                    return None

            def force_open_detail(pg, ref_no: str, ref_type: str) -> bool:
                base = "https://www.wanhai.com/views/cargo_track_v2"
                try:
                    url = f"{base}/tracking_data_page.xhtml?ref_no={ref_no}&ref_type={ref_type}"
                    log(f"force goto REAL detail: {url}")
                    pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                    return True
                except Exception as e1:
                    log(f"real detail goto failed: {e1}")
                    try:
                        page_name = ("tracking_data_page_by_bl_redirect"
                                     if ref_type == "MFT" else
                                     "tracking_data_page_by_booking_redirect")
                        url2 = f"{base}/{page_name}.xhtml?ref_no={ref_no}&ref_type={ref_type}"
                        log(f"fallback redirect goto: {url2}")
                        pg.goto(url2, wait_until="domcontentloaded", timeout=20000)
                        return True
                    except Exception as e2:
                        log(f"redirect goto failed: {e2}")
                        return False
          
            # ---- 如果还在查询页或列表页，立刻强制进入真实详情页 ----
                        # ---- 优先策略：如果还在查询页 -> 用表单提交；列表页再考虑强制跳 ----
            if re.search(r"tracking_query\.xhtml", (last_page.url or ""), re.I):
                np = open_detail_via_query_form(last_page, str(search_number), ref_type_detected)
                if np:
                    last_page = np
                    try:
                        last_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    # 禁用早期截图：wanhai_after_query_submit.png
                else:
                    log("query-form submit failed; fallback to force_open_detail()")
                    ok_force = force_open_detail(last_page, str(search_number), ref_type_detected)
                    if ok_force:
                        try:
                            last_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        try:
                            last_page.screenshot(path=os.path.join(debug_dir, "wanhai_after_force_detail.png"))
                        except Exception:
                            pass
                    else:
                        log("force_open_detail failed; still on query page")

            elif re.search(r"tracking_data_list\.xhtml", (last_page.url or ""), re.I):
                # 列表页可继续尝试强制进入真实详情（或后面已有列表点击逻辑）
                ok_force = force_open_detail(last_page, str(search_number), ref_type_detected)
                if ok_force:
                    try:
                        last_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    # 禁用早期截图：wanhai_after_force_detail.png
                    # 禁用早期截图：wanhai_after_force_detail.png

                        # ---- 通过 tracking_query.xhtml 表单提交打开详情（避免WAF/JSF校验）----
            
            # 在最终页面等待结果并提取（轮询，兼容 JSF 局部更新 / frames / XHTML 命名空间）
            log("waiting result on final page ...")
            # 截取所有页面前，等待页面稳定，避免加载态
            try:
                for pg in context.pages:
                    try:
                        wait_page_stable(pg, max_wait_sec=10)
                    except Exception:
                        pass
            except Exception:
                pass
            # 截取所有页面，并对以 __3 结尾的那张做 OCR 提取文字
            taken = []
            try:
                for idx, pg in enumerate(context.pages):
                    try:
                        url_ok = getattr(pg, "url", None)
                        if url_ok and url_ok != "about:blank":
                            p = snap(pg, f"all_after_open_detail__{idx}")
                            if p:
                                taken.append((idx, p))
                    except Exception:
                        continue
            except Exception:
                pass
            # 选择 idx==3 的图片（若存在），否则选择最后一张
            target_path = None
            for idx, p in taken:
                if idx == 3:
                    target_path = p
                    break
            if target_path is None and taken:
                target_path = taken[-1][1]
            # OCR 提取并立即结束（不再继续等待/轮询）
            out_obj_early = None
            ocr_text = None
            if target_path:
                try:
                    import pytesseract
                    from PIL import Image
                    img = Image.open(target_path)
                    # 若系统已安装中文语言包，可改为 eng+chi_sim
                    ocr_text = pytesseract.image_to_string(img, lang="eng")
                    txt_path = os.path.join(debug_dir, "wanhai_ocr_detail.txt")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(ocr_text)
                    log(f"OCR extracted to: {txt_path}")
                    # 简单正则从 OCR 中提取 ETA 日期并规范化
                    eta_raw = None
                    try:
                        m = re.search(r"ESTIMATED\s*ARRIVAL\s*DATE[^\n\r]*?(\d{4}[\/-]\d{1,2}[\/-]\d{1,2}|[A-Z]{3}[\-\s]\d{1,2}[\-\s]\d{4}|\d{1,2}[\-\s][A-Z]{3}[\-\s]\d{4})", ocr_text, flags=re.I)
                        if not m:
                            m = re.search(r"ETA[^\n\r]*?(\d{4}[\/-]\d{1,2}[\/-]\d{1,2}|[A-Z]{3}[\-\s]\d{1,2}[\-\s]\d{4}|\d{1,2}[\-\s][A-Z]{3}[\-\s]\d{4})", ocr_text, flags=re.I)
                        if m:
                            eta_raw = m.group(1)
                    except Exception:
                        eta_raw = None
                    if eta_raw:
                        eta_norm = normalize_date_text(eta_raw)
                        out_obj_early = {"status": "ok", "number": str(search_number), "result": eta_norm, "source": "ocr"}
                        # 也写入文件便于核对
                        with open(os.path.join(debug_dir, "wanhai_ocr_eta.txt"), "w", encoding="utf-8") as f:
                            f.write(eta_norm)
                    else:
                        out_obj_early = {"status": "ok", "number": str(search_number), "ocr": True, "result": "", "source": "ocr"}
                except Exception as e:
                    log(f"OCR failed: {e}")
                    out_obj_early = {"status": "ok", "number": str(search_number), "ocr_error": str(e)}

            if out_obj_early is None:
                out_obj_early = {"status": "ok", "number": str(search_number), "note": "screenshot saved, no ocr"}
            # 打印并保存结果，然后立刻返回，避免继续等待
            try:
                print(json.dumps(out_obj_early, ensure_ascii=False), flush=True)
                out_file = os.path.join(debug_dir, "wanhai_result.json")
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": datetime.now().isoformat(), **out_obj_early}, f, ensure_ascii=False, indent=2)
                log(f"written early result: {out_file}")
            except Exception:
                pass
            return out_obj_early
                        # 在最终页面等待结果并提取（轮询，兼容 JSF 局部更新 / frames / XHTML 命名空间）
           

            # ---------- BEGIN: 即刻取 ETA 的轻量兜底 ----------
            def get_text_by_xpath(page, xpath: str, timeout=8000) -> str:
                """根据XPath取文本"""
                try:
                    loc = page.locator(f"xpath={xpath}")
                    loc.wait_for(state="visible", timeout=timeout)
                    txt = loc.first.text_content() or ""
                    return re.sub(r"\s+", " ", txt.replace("\u00A0"," ")).strip()
                except Exception:
                    return ""

            # === Step 1: 尝试相对XPath抓ETA ===
            eta_xpath_label = "(//td[translate(normalize-space(.),'abcdefghijklmnopqrstuvwxyz.','ABCDEFGHIJKLMNOPQRSTUVWXYZ ')='ESTIMATED ARRIVAL DATE']/following-sibling::td[1])[last()]"
            eta_text = get_text_by_xpath(last_page, eta_xpath_label, timeout=6000)

            # 如果找到了就直接返回结果
            if eta_text:
                before_norm = eta_text
                eta_text = normalize_date_text(eta_text)
                log(f"ETA (via relative XPath): before='{before_norm}' after='{eta_text}'")

                out_obj = {
                    "status": "ok",
                    "number": str(search_number),
                    "result": eta_text,
                    "clickedSearch": clicked_search_ok,
                    "clickedMoreDetails": clicked_more_ok,
                }
                print(json.dumps(out_obj, ensure_ascii=False), flush=True)
                out_file = os.path.join(debug_dir, "wanhai_result.json")
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": datetime.now().isoformat(), **out_obj}, f, ensure_ascii=False, indent=2)
                log(f"written debug: {out_file}")
                return out_obj

            # === Step 2: 如果还没拿到，就尝试用config中配置的 result_xpath ===
            if result_xpath:
                eta_text = get_text_by_xpath(last_page, result_xpath, timeout=4000)
                if eta_text:
                    before_norm = eta_text
                    eta_text = normalize_date_text(eta_text)
                    log(f"ETA (via config result_xpath): before='{before_norm}' after='{eta_text}'")

                    out_obj = {
                        "status": "ok",
                        "number": str(search_number),
                        "result": eta_text,
                        "clickedSearch": clicked_search_ok,
                        "clickedMoreDetails": clicked_more_ok,
                    }
                    print(json.dumps(out_obj, ensure_ascii=False), flush=True)
                    out_file = os.path.join(debug_dir, "wanhai_result.json")
                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump({"timestamp": datetime.now().isoformat(), **out_obj}, f, ensure_ascii=False, indent=2)
                    log(f"written debug: {out_file}")
                    return out_obj

            # === Step 3: 再兜底，用全文正则匹配 ETA 日期 ===
            try:
                fulltxt = last_page.evaluate("() => document.body ? document.body.innerText : ''") or ""
            except Exception:
                fulltxt = ""
            if fulltxt.strip():
                m = re.search(
                    r"(?:ETA|EST\.?\s*ARRIVAL|ESTIMATED\s*ARRIVAL)[^\d]{0,30}"
                    r"(\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}|[A-Z]{3}[\-\s]\d{1,2}[\-\s]\d{4}|\d{1,2}[\-\s][A-Z]{3}[\-\s]\d{4})",
                    fulltxt,
                    flags=re.I
                )
                if m:
                    before_norm = m.group(1)
                    eta_text = normalize_date_text(before_norm)
                    log(f"ETA (via full-text regex): before='{before_norm}' after='{eta_text}'")

                    out_obj = {
                        "status": "ok",
                        "number": str(search_number),
                        "result": eta_text,
                        "clickedSearch": clicked_search_ok,
                        "clickedMoreDetails": clicked_more_ok,
                    }
                    print(json.dumps(out_obj, ensure_ascii=False), flush=True)
                    out_file = os.path.join(debug_dir, "wanhai_result.json")
                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump({"timestamp": datetime.now().isoformat(), **out_obj}, f, ensure_ascii=False, indent=2)
                    log(f"written debug: {out_file}")
                    return out_obj
            # ---------- END: 即刻取 ETA 的轻量兜底 ----------

            def scan_eta_in_page(p):
                # Returns ETA text or '' if not found
                try:
                    return p.evaluate("""
                        () => {
                          const norm = s => (s||'').replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
                          const isDateish = s => {
                            if (!s) return false;
                            const t = norm(s).toUpperCase();
                            // very permissive: 2025-10-10, 10/10/2025, 10-OCT-2025, OCT-10-2025, 2025/10/10, etc.
                            return (
                              /^\d{4}[-\/.]\d{1,2}[-\/.]\d{1,2}/.test(t) ||
                              /^\d{1,2}[-\/.][A-Z]{3}[-\/.]\d{4}/.test(t) ||
                              /^[A-Z]{3}[-\/.]\d{1,2}[-\/.]\d{4}/.test(t)
                            );
                          };

                          // Fast exit: No Data.
                          const noData = Array.from(document.querySelectorAll('td')).some(td => norm(td.textContent) === 'No Data.');
                          if (noData) return '__NO_DATA__';

                          const labels = ['ESTIMATED ARRIVAL DATE','EST. ARRIVAL DATE','EST ARRIVAL DATE','ETA'];
                          const tds = Array.from(document.querySelectorAll('td'));
                          for (const td of tds) {
                            const txt = norm(td.textContent).toUpperCase();
                            if (labels.includes(txt)) {
                              const sib = td.nextElementSibling;
                              if (sib) {
                                const val = norm(sib.textContent);
                                if (txt === 'ETA') {
                                  if (isDateish(val)) return val;
                                } else {
                                  if (val) return val;
                                }
                              }
                            }
                          }
                          return '';
                        }
                    """)
                except Exception:
                    return ''

            def scan_eta_everywhere(page):
                # Scan root + frames
                val = scan_eta_in_page(page)
                if val: return val
                try:
                    for fr in page.frames:
                        try:
                            if fr is page.main_frame:
                                continue
                            _ = fr.evaluate_handle("() => document")  # touch frame
                            res = scan_eta_in_page(fr)
                            if res: return res
                        except Exception:
                            continue
                except Exception:
                    pass
                return ''


            # Poll up to ~30s, tolerant to JSF partial updates & iframes
            deadline = time.time() + 30
            eta_text = ''
            while time.time() < deadline:
                # quick no-data check & ETA scan
                val = scan_eta_everywhere(last_page)
                if val == '__NO_DATA__':
                    log("detected 'No Data.' during polling, exit as no result")
                    return {"status": "no_data", "error": "No Data."}
                if val:
                    eta_text = val
                    break
                # small sleep, also nudge network to 'idle'
                try:
                    last_page.wait_for_load_state('networkidle', timeout=2000)
                except Exception:
                    pass
                time.sleep(0.4)

            if not eta_text:
                # Save for debug and return
                try:
                    with open(os.path.join(debug_dir, "wanhai_final_page.html"), "w", encoding="utf-8") as f:
                        f.write(last_page.content())
                    log("saved wanhai_final_page.html for debug; ETA not found within polling window")
                except Exception:
                    pass
                # 额外保存最终页面截图
                try:
                    last_page.screenshot(path=os.path.join(debug_dir, "wanhai_final_page.png"), full_page=True)
                except Exception:
                    pass
                return {"status": "timeout", "error": "ETA not found (no visible label or JSF fragment not rendered)"}

            before_norm = eta_text
            eta_text = normalize_date_text(eta_text)
            log(f"ETA normalize: before='{before_norm}' after='{eta_text}'")

            out_obj = {
                "status": "ok",
                "number": str(search_number),
                "result": eta_text,
                "clickedSearch": clicked_search_ok,
                "clickedMoreDetails": clicked_more_ok,
            }
            print(json.dumps(out_obj, ensure_ascii=False), flush=True)
            out_file = os.path.join(debug_dir, "wanhai_result.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump({"timestamp": datetime.now().isoformat(), **out_obj}, f, ensure_ascii=False, indent=2)
            log(f"written debug: {out_file}")
            # 额外保存最终页面截图
            try:
                last_page.screenshot(path=os.path.join(debug_dir, "wanhai_final_page.png"), full_page=True)
            except Exception:
                pass
            return out_obj
        except PlaywrightTimeoutError as e:
            try:
                page.screenshot(path=os.path.join(debug_dir, "wanhai_timeout.png"))
            except Exception:
                pass
            log(f"timeout exception after {elapsed_ms()}ms: {e}")
            return {"status": "timeout", "error": str(e)}
        except Exception as e:
            try:
                page.screenshot(path=os.path.join(debug_dir, "wanhai_error.png"))
            except Exception:
                pass
            log(f"unexpected exception after {elapsed_ms()}ms: {e}")
            return {"status": "error", "error": str(e)}
            
        finally:
            try:
                if context and not context.is_closed():
                    context.close()
                else:
                    log("context already closed or None, skip closing.")
            except Exception as e:
                log(f"ignore context close error: {e}")
  

def main():
    parser = argparse.ArgumentParser(description="WanHai tracking scraper using Playwright")
    parser.add_argument("--config", default=os.path.join("backend", "app", "config", "wanhai.json"),
                        help="path to json config")
    parser.add_argument("--number", help="override search_number from config", default=None)
    args = parser.parse_args()

    cfg_path = args.config
    if not os.path.isabs(cfg_path):
        # 相对路径以项目根目录运行时兼容
        root = os.path.dirname(os.path.dirname(__file__))
        cfg_path = os.path.abspath(os.path.join(root, os.path.relpath(cfg_path)))

    log(f"using config: {cfg_path}")
    config = load_config(cfg_path)
    if args.number:
        config["search_number"] = str(args.number)
        log(f"override search_number via --number: {config['search_number']}")
    ensure_dir(os.path.join(os.path.dirname(__file__), "app", "debug"))

    # 执行（scrape 内部已负责打印与写调试文件）
    _ = scrape(config)


if __name__ == "__main__":
    sys.exit(main())


