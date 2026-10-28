"""Generate static/og-image.png (1200x630) for WhatsApp/LinkedIn preview."""
import pathlib, textwrap

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{width:1200px;height:630px;background:#f8f9ff;font-family:'Inter',system-ui,sans-serif;overflow:hidden;display:flex;flex-direction:column}
  .top{background:#fff;border-bottom:1.5px solid #e8eaf0;padding:32px 52px;display:flex;align-items:center;gap:16px}
  .mark{width:44px;height:44px;background:#1a1a1a;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .mark svg{width:24px;height:24px}
  .brand-text{display:flex;flex-direction:column;gap:2px}
  .brand-name{font-size:22px;font-weight:800;color:#1a1a1a;letter-spacing:-0.3px}
  .brand-sub{font-size:10px;font-weight:600;color:#6366f1;letter-spacing:0.8px;text-transform:uppercase}
  .url{margin-left:auto;font-size:13px;color:#9094a0;font-weight:500}
  .body{flex:1;display:flex;padding:0 52px;gap:64px;align-items:center}
  .left{flex:1;display:flex;flex-direction:column;gap:24px}
  .tag{display:inline-flex;align-items:center;gap:6px;background:#ede9fe;color:#6366f1;font-size:12px;font-weight:600;padding:5px 12px;border-radius:20px;width:fit-content;letter-spacing:0.2px}
  .headline{font-size:42px;font-weight:800;color:#0f0f1a;line-height:1.15;letter-spacing:-1px}
  .headline span{color:#6366f1}
  .desc{font-size:16px;color:#5a5f72;line-height:1.6;max-width:480px}
  .stats{display:flex;gap:32px;margin-top:4px}
  .stat-num{font-size:28px;font-weight:800;color:#1a1a1a}
  .stat-label{font-size:12px;color:#9094a0;font-weight:500;margin-top:2px}
  .right{width:380px;flex-shrink:0;display:flex;flex-direction:column;gap:10px}
  .chip-row{display:flex;flex-wrap:wrap;gap:8px}
  .chip{display:flex;align-items:center;gap:6px;background:#fff;border:1.5px solid #e8eaf0;border-radius:20px;padding:7px 14px;font-size:13px;font-weight:500;color:#2d3042}
  .chip.active{background:#6366f1;border-color:#6366f1;color:#fff}
  .chip-dot{width:7px;height:7px;border-radius:50%;background:currentColor;opacity:.4}
  .chip.active .chip-dot{opacity:1;background:#fff}
  .export-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
  .exp{background:#f1f0fe;color:#6366f1;font-size:11px;font-weight:600;padding:4px 10px;border-radius:6px}
  .section-label{font-size:10px;font-weight:700;color:#9094a0;letter-spacing:0.8px;text-transform:uppercase;margin-top:6px}
</style>
</head>
<body>
<div class="top">
  <div class="mark">
    <svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
      <rect x="12" y="9" width="5" height="22" fill="white"/>
      <rect x="12" y="26" width="16" height="5" fill="white"/>
      <rect x="23" y="9" width="5" height="12" fill="white"/>
      <rect x="17" y="17" width="6" height="5" fill="white"/>
    </svg>
  </div>
  <div class="brand-text">
    <div class="brand-name">AlyxLabs</div>
    <div class="brand-sub">Data Tools</div>
  </div>
  <div class="url">scraper.alyxlabs.tech</div>
</div>
<div class="body">
  <div class="left">
    <div class="tag">Multi-Platform Web Scraper</div>
    <div class="headline">Scrape data dari<br><span>10 platform</span><br>sekaligus</div>
    <div class="desc">Berita, jurnal, Wikipedia, YouTube - satu klik, banyak sumber. Export langsung ke CSV, JSON, XLSX, BibTeX.</div>
    <div class="stats">
      <div><div class="stat-num">10</div><div class="stat-label">Platform</div></div>
      <div><div class="stat-num">6</div><div class="stat-label">Format export</div></div>
      <div><div class="stat-num">100%</div><div class="stat-label">Gratis</div></div>
    </div>
  </div>
  <div class="right">
    <div class="section-label">Pilih Platform</div>
    <div class="chip-row">
      <div class="chip active"><div class="chip-dot"></div>Google News</div>
      <div class="chip active"><div class="chip-dot"></div>News Sites</div>
      <div class="chip"><div class="chip-dot"></div>GDELT</div>
    </div>
    <div class="chip-row">
      <div class="chip"><div class="chip-dot"></div>Kompas</div>
      <div class="chip"><div class="chip-dot"></div>Liputan6</div>
      <div class="chip"><div class="chip-dot"></div>YouTube</div>
    </div>
    <div class="chip-row">
      <div class="chip"><div class="chip-dot"></div>Wikipedia</div>
      <div class="chip"><div class="chip-dot"></div>OpenAlex</div>
      <div class="chip"><div class="chip-dot"></div>Kaskus</div>
    </div>
    <div class="section-label" style="margin-top:12px">Export Format</div>
    <div class="export-row">
      <div class="exp">CSV</div>
      <div class="exp">JSON</div>
      <div class="exp">XLSX</div>
      <div class="exp">Markdown</div>
      <div class="exp">RIS</div>
      <div class="exp">BibTeX</div>
    </div>
  </div>
</div>
</body>
</html>"""

out = pathlib.Path("static/og-image.html")
out.write_text(HTML, encoding="utf-8")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 630})
    page.set_content(HTML, wait_until="load")
    page.add_style_tag(content="@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');")
    page.wait_for_timeout(1500)
    page.screenshot(path="static/og-image.png", clip={"x": 0, "y": 0, "width": 1200, "height": 630})
    browser.close()

print("og-image.png generated OK")
