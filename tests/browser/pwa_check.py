"""
PWA audit in real browsers (Playwright): manifest, icons, installability, service worker,
offline app shell, SPA deep links offline, API offline cache and cache clearing on logout.

  # against your real Flutter build (after `flutter build web` and serving build/web):
  python tests/browser/pwa_check.py --url http://localhost:8080 --browser chromium
  # self-contained check of the PWA layer only (uses a stub instead of the compiled Flutter app):
  python tests/browser/pwa_check.py --self-test

Firefox/WebKit: `python -m playwright install firefox webkit`, then --browser firefox|webkit
(installability via CDP is Chromium-only and is skipped there).
"""
import argparse
import functools
import http.server
import json
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[2] / "frontend" / "web"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  - ' + str(detail)) if detail else ''}")


def build_stub_site():
    """web/ + a tiny stand-in for the compiled Flutter bundle."""
    d = Path(tempfile.mkdtemp(prefix="fbpwa-"))
    shutil.copytree(WEB, d, dirs_exist_ok=True)
    (d / "index.html").write_text((d / "index.html").read_text().replace("$FLUTTER_BASE_HREF", "/"))
    (d / "flutter.js").write_text("// stub")
    (d / "main.dart.js").write_text("// stub")
    (d / "flutter_bootstrap.js").write_text(
        "document.body.insertAdjacentHTML('beforeend','<main id=app>FoodBridge app</main>');"
        "window.dispatchEvent(new Event('flutter-first-frame'));")
    (d / "api" / "demo").mkdir(parents=True)
    (d / "api" / "demo" / "data").write_text(json.dumps({"hello": "cached"}))
    return d


def serve(root, port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run(url, browser_name, self_test, go_offline=None, go_online=None):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(url, wait_until="load")

        # manifest
        man = page.evaluate("""async () => { const l = document.querySelector('link[rel=manifest]');
            const r = await fetch(l.href); return {status: r.status, body: await r.json()}; }""")
        m = man["body"]
        check("manifest served", man["status"] == 200)
        check("manifest has name/short_name/start_url/display",
              all(m.get(k) for k in ("name", "short_name", "start_url", "display")) and m["display"] == "standalone")
        sizes = {i["sizes"] + ":" + i.get("purpose", "any") for i in m["icons"]}
        check("192 + 512 icons, incl. maskable", {"192x192:any", "512x512:any", "512x512:maskable"} <= sizes, sorted(sizes))
        for icon in m["icons"]:
            dims = page.evaluate("""async (src) => { const img = new Image(); img.src = src; await img.decode();
                return img.naturalWidth + 'x' + img.naturalHeight; }""", icon["src"])
            check(f"icon {icon['src']} is {icon['sizes']}", dims == icon["sizes"], dims)
        check("theme-color meta", page.locator("meta[name=theme-color]").count() == 1)
        check("apple-touch-icon", page.locator("link[rel=apple-touch-icon]").count() == 1)

        # service worker
        state = page.evaluate("""async () => { const reg = await navigator.serviceWorker.ready;
            return reg.active ? reg.active.state : 'none'; }""")
        check("service worker active", state in ("activated", "activating"), state)
        page.reload(wait_until="load")
        check("page controlled by service worker", page.evaluate("!!navigator.serviceWorker.controller"))
        cached = page.evaluate("""async () => { const keys = await caches.keys(); let n = [];
            for (const k of keys) { const c = await caches.open(k); n = n.concat((await c.keys()).map(r => r.url)); }
            return n; }""")
        check("app shell precached (index, offline page, bootstrap)",
              any(u.endswith("/index.html") for u in cached) and any("offline.html" in u for u in cached)
              and any("flutter_bootstrap.js" in u for u in cached), f"{len(cached)} entries")

        if browser_name == "chromium":
            cdp = ctx.new_cdp_session(page)
            errs = cdp.send("Page.getInstallabilityErrors").get("installabilityErrors", [])
            check("installable (no Chrome installability errors)", not errs, errs)

        if self_test:
            page.evaluate("fetch('/api/demo/data').then(r => r.json())")
            page.wait_for_timeout(300)

        # offline. Playwright's set_offline() does not cover service-worker fetches, so the self-test really
        # stops the web server; against your own server we emulate it (and you can confirm in DevTools → Offline).
        (go_offline or (lambda: ctx.set_offline(True)))()
        page.reload(wait_until="load")
        check("app shell loads offline", page.locator("#app, flt-glass-pane, flutter-view").count() > 0
              or "FoodBridge" in page.content())
        page.goto(url.rstrip("/") + "/pickups", wait_until="load")
        check("deep link (/pickups) opens offline", "FoodBridge" in page.content())
        if self_test:
            data = page.evaluate("fetch('/api/demo/data').then(r => r.json())")
            check("API GET served from cache when offline", data.get("hello") == "cached", data)
            page.evaluate("window.fbClearApiCache()")
            page.wait_for_timeout(300)
            st = page.evaluate("fetch('/api/demo/data').then(r => r.status)")
            check("logout clears offline API cache (503 afterwards)", st == 503, st)
        (go_online or (lambda: ctx.set_offline(False)))()

        # responsive smoke: no horizontal scroll at phone / tablet / desktop widths
        for w, h in [(360, 740), (768, 1024), (1440, 900)]:
            page.set_viewport_size({"width": w, "height": h})
            page.goto(url, wait_until="load")
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            check(f"no horizontal overflow at {w}px", not overflow)
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    httpd = {"s": None}
    kw = {}
    if a.self_test or not a.url:
        root = build_stub_site()
        httpd["s"] = serve(root, 0)                    # any free port
        port = httpd["s"].server_address[1]
        a.url, a.self_test = f"http://127.0.0.1:{port}/", True

        def off():
            httpd["s"].shutdown()
            httpd["s"].server_close()
            httpd["s"] = None
        # stays "offline" for the rest of the run: the remaining checks are served by the service worker
        kw = {"go_offline": off, "go_online": lambda: None}
    print(f"PWA audit · {a.browser} · {a.url}")
    try:
        run(a.url, a.browser, a.self_test, **kw)
    finally:
        if httpd["s"]:
            httpd["s"].shutdown()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
