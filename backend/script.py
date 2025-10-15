from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
try:
    from playwright_stealth import stealth_sync  # type: ignore
except Exception:  # noqa: S110
    def stealth_sync(page):  # type: ignore
        return None
