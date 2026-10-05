"""
Cross-browser UI smoke test for the compiled Flutter web app (Chromium, Firefox, WebKit/Safari)
at phone, tablet and desktop sizes. Flutter draws on a canvas, so the test switches on Flutter's
accessibility tree and drives the app through it - the same tree screen readers use.

  cd frontend && flutter build web --release && python -m http.server 8080 -d build/web   # or docker compose
  python -m playwright install chromium firefox webkit
  python tests/browser/app_smoke.py --url http://localhost:8080 --browsers chromium,firefox,webkit

Needs the API running with the demo data. Screenshots land in tests/browser/screenshots/.
"""
import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import expect, sync_playwright

SHOTS = Path(__file__).with_name("screenshots")
VIEWPORTS = {"phone": (390, 844), "tablet": (820, 1180), "desktop": (1440, 900)}
FLOWS = [
    # (account, password, text expected on the home screen, pages to open by nav label)
    ("hotel@foodbridge.dev", "Demo@12345", "Stock value", ["Inventory", "Surplus", "Pickup"]),
    ("hope@foodbridge.dev", "Demo@12345", "Matched donations", ["Live", "Pickup"]),
    ("admin@foodbridge.dev", "Admin@12345", "Listings Active", ["NGO", "Impact"]),
]


def enable_semantics(page):
    page.wait_for_selector("flt-semantics-placeholder, flutter-view, flt-glass-pane", timeout=60_000, state="attached")
    ph = page.locator("flt-semantics-placeholder")
    if ph.count():
        ph.first.dispatch_event("click")
    page.wait_for_timeout(800)


def login(page, email, password):
    email_box = page.get_by_role("textbox", name=re.compile("Email", re.I))
    email_box.click()
    email_box.fill(email)
    pw = page.get_by_role("textbox", name=re.compile("Password", re.I))
    pw.click()
    pw.fill(password)
    page.get_by_role("button", name=re.compile("^Sign in$", re.I)).click()


def run(url, browsers):
    SHOTS.mkdir(exist_ok=True)
    failures = []
    with sync_playwright() as p:
        for bname in browsers:
            browser = getattr(p, bname).launch()
            for vp, (w, h) in VIEWPORTS.items():
                for email, pw, home_text, pages in FLOWS:
                    tag = f"{bname}-{vp}-{email.split('@')[0]}"
                    ctx = browser.new_context(viewport={"width": w, "height": h},
                                              is_mobile=(vp == "phone" and bname != "firefox"))
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    try:
                        page.goto(url, wait_until="load")
                        enable_semantics(page)
                        login(page, email, pw)
                        expect(page.get_by_text(home_text).first).to_be_visible(timeout=30_000)
                        page.screenshot(path=str(SHOTS / f"{tag}-home.png"))
                        for label in pages:
                            if vp == "phone":        # items outside the bottom bar live in the drawer
                                target = page.get_by_role("button", name=re.compile(label, re.I)).first
                                if not target.is_visible():
                                    page.get_by_role("button", name=re.compile("Open navigation menu", re.I)).click()
                            page.get_by_role("button", name=re.compile(label, re.I)).first.click()
                            page.wait_for_timeout(1500)
                            page.screenshot(path=str(SHOTS / f"{tag}-{label.lower()}.png"))
                        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
                        if overflow:
                            raise AssertionError("page scrolls horizontally")
                        if errors:
                            raise AssertionError(f"JS errors: {errors[:2]}")
                        print(f"  PASS  {tag}")
                    except (AssertionError, PWTimeout, Exception) as exc:  # noqa: BLE001
                        failures.append((tag, str(exc)[:200]))
                        page.screenshot(path=str(SHOTS / f"{tag}-FAILED.png"))
                        print(f"  FAIL  {tag}: {str(exc)[:160]}")
                    finally:
                        ctx.close()
            browser.close()
    print(f"\n{len(failures)} failure(s); screenshots in {SHOTS}")
    return failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--browsers", default="chromium,firefox,webkit")
    a = ap.parse_args()
    sys.exit(1 if run(a.url, a.browsers.split(",")) else 0)
