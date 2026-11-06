#!/usr/bin/env python3
"""Audits the built site. Usage: python3 verify_site.py dist [--site https://9xenai.com]"""
import sys, json, re, threading, functools, http.server, socketserver, pathlib
from playwright.sync_api import sync_playwright

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
site = (sys.argv[sys.argv.index("--site") + 1] if "--site" in sys.argv else "https://9xenai.com").rstrip("/")
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)); H.log_message = lambda *x: None
srv = socketserver.TCPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % port
routes = sorted(str(p.parent.relative_to(root)).replace("\\", "/") for p in root.rglob("index.html"))
routes = ["" if r == "." else r + "/" for r in routes]
fails, warns = [], []
def F(m): fails.append(m)
def W(m): warns.append(m)

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(locale="en-US"); pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    for r in routes:
        errs.clear(); pg.goto("%s/%s" % (base, r)); pg.wait_for_timeout(600)
        t = pg.title(); d = pg.evaluate("(document.querySelector('meta[name=description]')||{}).content||''")
        can = pg.evaluate("(document.querySelector('link[rel=canonical]')||{}).href||''")
        exp = site + "/" + r
        h1 = pg.locator(".page.on h1").count()
        tag = "/" + r
        if not 25 <= len(t) <= 70: W("%s title length %d: %s" % (tag, len(t), t))
        if not 70 <= len(d) <= 175: W("%s description length %d" % (tag, len(d)))
        if can != exp: F("%s canonical is %r, expected %r" % (tag, can, exp))
        if h1 != 1: F("%s has %d visible h1" % (tag, h1))
        if errs: F("%s JS errors: %s" % (tag, errs[:2]))
        if pg.evaluate("document.querySelectorAll('.tg9').length") != 1: F("%s duplicated theme toggle" % tag)
        ld = pg.evaluate("[...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s=>s.textContent)")
        types = set()
        for x in ld:
            try:
                j = json.loads(x)
                for n in (j.get("@graph") or [j]): types.add(str(n.get("@type")))
            except Exception as e: F("%s invalid JSON-LD: %s" % (tag, e))
        for need in ("Organization", "WebSite", "BreadcrumbList"):
            if need not in types: F("%s missing schema %s" % (tag, need))
        if re.search(r"^(sla|security|nda|dpa|procurement|services/)", r) and r != "services/" and "FAQPage" not in types: W("%s no FAQPage schema" % tag)
        if pg.evaluate("document.documentElement.lang") != "en": W("%s html lang not en" % tag)
        # links
        for h in pg.evaluate("[...new Set([...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')))]"):
            if h.startswith("/") and not h.startswith("//"):
                pth = h.split("#")[0].split("?")[0].lstrip("/")
                if pth and not ((root / pth).exists() or (root / pth / "index.html").exists()): F("%s broken link %s" % (tag, h))
            elif h.startswith("#") and len(h) > 1: W("%s leftover hash link %s" % (tag, h))
        # raw HTML (what a non-JS crawler sees)
        raw = (root / r / "index.html").read_text(encoding="utf-8")
        if "<h1" not in raw or len(re.sub(r"<[^>]+>", " ", raw)) < 3000: F("%s raw HTML has too little content" % tag)
    b.close()
srv.shutdown()
for f in ("sitemap.xml", "robots.txt", "llms.txt", "_headers", "404.html"):
    if not (root / f).exists(): F("missing %s" % f)
if not (root / ".well-known/security.txt").exists(): W("no .well-known/security.txt (rebuild with --email)")
html = (root / "index.html").read_text(encoding="utf-8")
m = re.search(r'var CFG=\{([^}]*)\}', html)
if m:
    for k in ("EMAIL", "PHONE", "FORM_ENDPOINT", "LINKEDIN", "CALENDAR", "WHATSAPP"):
        if re.search(k + r':""', m.group(1)): W("CFG.%s is empty%s" % (k, " (contact form delivers nowhere if EMAIL and FORM_ENDPOINT are both empty)" if k in ("EMAIL", "FORM_ENDPOINT") else ""))
print("Pages checked: %d" % len(routes))
print("FAILURES (%d):" % len(fails)); [print("  x", x) for x in fails]
print("WARNINGS (%d):" % len(warns)); [print("  !", x) for x in warns]
sys.exit(1 if fails else 0)
