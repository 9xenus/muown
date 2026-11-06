#!/usr/bin/env python3
"""Builds a crawlable site from index.html.
Usage: python3 build_static.py --src index.html --out dist --site https://9xenai.com [--email security@your-domain]
Needs: pip install playwright && playwright install chromium"""
import argparse, re, shutil, threading, datetime, pathlib, functools, http.server, socketserver
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="index.html"); ap.add_argument("--out", default="dist")
ap.add_argument("--site", default="https://9xenai.com"); ap.add_argument("--email", default="")
a = ap.parse_args()
site = a.site.rstrip("/"); out = pathlib.Path(a.out); src = pathlib.Path(a.src)
today = datetime.date.today().isoformat()

html = src.read_text(encoding="utf-8")
html = re.sub(r'<meta name="9x-site" content="[^"]*">', '<meta name="9x-site" content="%s">' % site, html)
if '<meta name="9x-clean"' not in html:
    html = html.replace('<meta name="9x-site"', '<meta name="9x-clean" content="1">\n<meta name="9x-base" content="/">\n<meta name="9x-site"', 1)

# route list taken from the page itself
pages = re.search(r'pages=\[([^\]]+)\]', html).group(1).replace('"', '').split(",")
svcs = re.findall(r'^(\w+):\{name:"', html, re.M)
routes = [p for p in pages] + ["service-" + k for k in svcs]
def path(r): return "" if r == "home" else ("services/%s/" % r[8:] if r.startswith("service-") else r + "/")

# serve a temp tree where every route folder holds the template
tmp = pathlib.Path("_tpl"); shutil.rmtree(tmp, ignore_errors=True)
for r in routes:
    d = tmp / path(r); d.mkdir(parents=True, exist_ok=True); (d / "index.html").write_text(html, encoding="utf-8")
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
H.log_message = lambda *x: None
srv = socketserver.TCPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
titles = {}
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(locale="en-US", viewport={"width": 1280, "height": 900}); pg = ctx.new_page()
    for r in routes:
        pg.goto("http://127.0.0.1:%d/%s" % (port, path(r))); pg.wait_for_timeout(700)
        pg.evaluate("""()=>{document.querySelectorAll('.tg9,.fx-top,.fx-stk,.fx-aura').forEach(e=>e.remove());
          const d=document.documentElement;d.removeAttribute('data-theme');d.classList.remove('on-contact');
          const h=document.querySelector('header');if(h)h.classList.remove('stuck');}""")
        titles[r] = pg.title()
        (out / path(r)).mkdir(parents=True, exist_ok=True)
        (out / path(r) / "index.html").write_text("<!DOCTYPE html>\n" + pg.evaluate("document.documentElement.outerHTML"), encoding="utf-8")
    b.close()
srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
shutil.copy(out / "index.html", out / "404.html")
if pathlib.Path(src.parent, "logo.png").exists(): shutil.copy(src.parent / "logo.png", out / "logo.png")

url = lambda r: site + "/" + path(r)
(out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    ''.join("<url><loc>%s</loc><lastmod>%s</lastmod></url>\n" % (url(r), today) for r in routes) + "</urlset>\n", encoding="utf-8")
bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "PerplexityBot", "Google-Extended", "Applebot-Extended", "CCBot"]
(out / "robots.txt").write_text("User-agent: *\nAllow: /\n\n" + ''.join("User-agent: %s\nAllow: /\n\n" % x for x in bots) + "Sitemap: %s/sitemap.xml\n" % site, encoding="utf-8")

def line(r, desc): return "- [%s](%s): %s\n" % (titles[r].split(" | ")[0] if " | " in titles[r] else titles[r], url(r), desc)
llms = ("# 9xenai\n\n> 9xenai is an AI consulting, automation and software company based in Dhaka, Bangladesh, working remote-first with organisations in Bangladesh, "
        "the Middle East, Europe and other markets. It designs, builds and operates governed AI, starting from a fixed-scope assessment and a measurable KPI.\n\n"
        "## Services\n" + ''.join("- [%s](%s)\n" % (titles["service-" + k].split(" | ")[0], url("service-" + k)) for k in svcs) +
        "\n## Trust and contracting\n" + line("sla", "Support plans, severities, response and availability targets, service credits, escalation") +
        line("security", "Security controls, AI-specific controls, compliance status stated plainly") + line("nda", "Mutual NDA terms and handling of confidential data") +
        line("dpa", "Data processing terms") + line("procurement", "Documents and process for vendor onboarding") + line("ai-use", "AI use policy") +
        line("privacy", "Privacy policy") + line("terms", "Terms of service") +
        "\n## About\n" + line("about", "Company overview") + line("approach", "Assess, pilot, scale, operate with decision gates") +
        line("cases", "Illustrative scenarios, not named client results") + line("global", "Regions, time zones, languages") + line("contact", "Request an assessment") +
        "\n## Notes\n- Case studies and calculators on the site are illustrative planning aids, not guaranteed results.\n- Certification status is stated in proposals; practices are aligned to ISO/IEC 27001 and 42001 but not certified unless a page says otherwise.\n")
(out / "llms.txt").write_text(llms, encoding="utf-8")
(out / "_headers").write_text("/*\n  Strict-Transport-Security: max-age=31536000; includeSubDomains\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: DENY\n"
    "  Referrer-Policy: strict-origin-when-cross-origin\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n", encoding="utf-8")
if a.email:
    wk = out / ".well-known"; wk.mkdir()
    exp = (datetime.date.today() + datetime.timedelta(days=365)).isoformat() + "T00:00:00.000Z"
    (wk / "security.txt").write_text("Contact: mailto:%s\nExpires: %s\nPreferred-Languages: en, bn\nCanonical: %s/.well-known/security.txt\n" % (a.email, exp, site), encoding="utf-8")
else:
    print("WARNING: no --email given, security.txt not written (the Trust centre page links to it).")
print("Built %d pages into %s/" % (len(routes), out))
