from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from threading import Thread, Lock, Semaphore
from functools import wraps
from datetime import datetime, timezone, timedelta
from collections import Counter
import ipaddress
import uuid
import io
import time
import json
import os

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load .env in dev; production uses systemd Environment= directives instead.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests as _requests

from scraper import UnifiedScraper, SCRAPERS
from image_scraper_module import ImageScraper
from database import (log_audit, get_audit_logs, get_usage_stats, get_top_keywords,
                       get_top_platforms, get_summary_stats,
                       submit_feedback, get_feedback, update_feedback_status)

app = Flask(__name__, static_folder='static', template_folder='templates')
# ProxyFix lets request.remote_addr reflect the real client IP when behind nginx.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Per-IP rate limiter. ProxyFix resolves X-Forwarded-For into remote_addr before
# flask-limiter reads it, so get_remote_address sees the real client IP.
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])
# KeyError is intentional: app must not start without a secret key set.
app.secret_key = os.environ['SECRET_KEY']
app.permanent_session_lifetime = timedelta(hours=8)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,   # served over HTTPS in prod; disabled for local dev in __main__
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # 5 MB upload cap
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

_DEFAULT_CONFIG = {
    'twitter': {
        'use_twikit': False,
        'nitter_instances': [
            'https://nitter.privacydev.net',
            'https://nitter.poast.org'
        ]
    }
}

# Single lock for all config.json reads and writes so concurrent requests
# cannot interleave a partial write with a read.
_config_lock = Lock()


def load_config():
    with _config_lock:
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            return _DEFAULT_CONFIG.copy()


def save_config(cfg):
    with _config_lock:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)


def enabled_platforms():
    """Platforms the admin has left on (not in config 'platforms_disabled')."""
    disabled = set(load_config().get('platforms_disabled', []))
    return [p for p in SCRAPERS.keys() if p not in disabled]

jobs = {}
jobs_lock = Lock()

# Hard cap on concurrent scraping jobs; the 6th request gets a 429.
_job_semaphore = Semaphore(5)

# Rate-limit state for /api/forgot-password (per-IP, in-memory)
_forgot_hits = {}
_forgot_lock = Lock()

# Brute-force guard for admin login (per-IP failed attempts, in-memory)
_login_fails = {}
_login_lock = Lock()
_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW = 300  # seconds


def _login_blocked(ip):
    now = time.time()
    with _login_lock:
        fails = [t for t in _login_fails.get(ip, []) if now - t < _LOGIN_WINDOW]
        _login_fails[ip] = fails
        return len(fails) >= _LOGIN_MAX_FAILS


def _record_login_fail(ip):
    with _login_lock:
        _login_fails.setdefault(ip, []).append(time.time())


def _clear_login_fails(ip):
    with _login_lock:
        _login_fails.pop(ip, None)


def get_client_ip():
    # ProxyFix already resolved X-Forwarded-For into remote_addr.
    return request.remote_addr or '127.0.0.1'


def _is_safe_url(url: str) -> bool:
    """Block URLs that could reach internal infrastructure (SSRF guard)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.hostname or ''
        if not host:
            return False
        if host.lower() in ('localhost', '0.0.0.0'):
            return False
        try:
            addr = ipaddress.ip_address(host)
            if (addr.is_loopback or addr.is_private or
                    addr.is_link_local or addr.is_reserved):
                return False
        except ValueError:
            pass  # hostname, not an IP literal
        return True
    except Exception:
        return False


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File terlalu besar, maksimum 5MB'}), 413


def _prune_jobs(max_age=3600):
    """Drop finished jobs older than max_age so the in-memory dict does not grow forever."""
    now = time.time()
    with jobs_lock:
        stale = [jid for jid, r in jobs.items()
                 if r.get('finished_at') and now - r['finished_at'] > max_age]
        for jid in stale:
            jobs.pop(jid, None)


def create_job_record():
    _prune_jobs()
    job_id = str(uuid.uuid4())
    rec = {
        'status': 'queued',
        'message': 'Job queued',
        'results': [],
        'started_at': None,
        'finished_at': None,
        'keywords': [],
        'locations': [''],
        'location': '',
        'platforms': [],
        'cancelled': False,
        'notify_email': '',
        'notify_webhook': '',
        'notify_format': 'csv',
    }
    with jobs_lock:
        jobs[job_id] = rec
    return job_id


def run_scraper_job(job_id, keywords, locations, platforms, ip, ua, full_text=False, date_from=None, date_to=None):
    with jobs_lock:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['message'] = 'Starting scraper...'
        jobs[job_id]['started_at'] = time.time()

    try:
        def cb(msg):
            with jobs_lock:
                if jobs[job_id].get('cancelled'):
                    raise RuntimeError('__CANCELLED__')
                jobs[job_id]['message'] = msg

        scraper = UnifiedScraper(gui_callback=cb)
        results = scraper.scrape_keywords(keywords, locations, platforms,
                                          date_from=date_from, date_to=date_to)

        if date_from or date_to:
            from datetime import date as _date
            def _parse_date(s):
                try:
                    return _date.fromisoformat(s[:10])
                except Exception:
                    return None
            df = _parse_date(date_from) if date_from else None
            dt = _parse_date(date_to) if date_to else None
            filtered = []
            for r in results:
                rd = _parse_date(r.get('date', '') or '')
                if rd is None:
                    filtered.append(r)
                    continue
                if df and rd < df:
                    continue
                if dt and rd > dt:
                    continue
                filtered.append(r)
            results = filtered

        if full_text:
            cb('Mengambil teks lengkap artikel...')
            from scraper import enrich_full_text
            enrich_full_text(results, gui_callback=cb)

        with jobs_lock:
            jobs[job_id]['results'] = results
            jobs[job_id]['status'] = 'finished'
            jobs[job_id]['message'] = f'Finished: {len(results)} results'
            jobs[job_id]['finished_at'] = time.time()
            # Read inside the same lock so we never touch jobs outside a lock.
            duration = jobs[job_id]['finished_at'] - jobs[job_id]['started_at']
            _notify_email   = jobs[job_id].get('notify_email', '')
            _notify_webhook = jobs[job_id].get('notify_webhook', '')
            _notify_format  = jobs[job_id].get('notify_format', 'csv')
        location_str = ', '.join(loc for loc in locations if loc)
        for kw in keywords:
            log_audit(
                session_id=job_id, action='scrape',
                keyword=kw, platform=','.join(platforms),
                location=location_str, results_count=len(results),
                duration_seconds=round(duration, 2),
                ip_address=ip, user_agent=ua
            )
        if _notify_email or _notify_webhook:
            _send_notification(_notify_email, _notify_webhook, len(results), keywords,
                               results=results, notify_format=_notify_format, job_id=job_id)
    except Exception as e:
        with jobs_lock:
            if jobs[job_id].get('cancelled'):
                jobs[job_id]['status'] = 'cancelled'
                jobs[job_id]['message'] = 'Scraping dihentikan'
            else:
                jobs[job_id]['status'] = 'error'
                jobs[job_id]['message'] = f'Error: {str(e)}'
            jobs[job_id]['finished_at'] = time.time()
    finally:
        # Always release the slot so new jobs can be accepted.
        _job_semaphore.release()


def _send_email_smtp(sender, password, recipient, subject, html_body, attachments=None):
    """Send email via SMTP with optional attachments.
    attachments: list of (filename, bytes, mimetype) tuples.
    Supports port 587 (STARTTLS) and 465/others (SSL)."""
    import smtplib, ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders as _enc
    from email.utils import formataddr
    cfg_email = load_config().get('email', {})
    host = cfg_email.get('smtp_host', 'smtp.gmail.com').strip() or 'smtp.gmail.com'
    port = int(cfg_email.get('smtp_port', 465) or 465)
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = formataddr(('No Reply - AlyxLabs Support', sender))
    msg['To'] = recipient
    msg.attach(MIMEText(html_body, 'html'))
    for fname, fbytes, fmime in (attachments or []):
        part = MIMEBase(*fmime.split('/', 1))
        part.set_payload(fbytes)
        _enc.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=fname)
        msg.attach(part)
    ctx = ssl.create_default_context()
    if port == 587:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(sender, password)
            s.sendmail(sender, recipient, msg.as_string())
    else:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
            s.login(sender, password)
            s.sendmail(sender, recipient, msg.as_string())


def _generate_export_bytes(results, meta, fmt):
    """Return (file_bytes, filename, mimetype) for the chosen export format."""
    import csv as _csv, io as _io
    stamp = 'scraping'
    if fmt == 'json':
        content = json.dumps({'metadata': meta, 'data': results}, ensure_ascii=False, indent=2)
        return content.encode('utf-8'), f'hasil_{stamp}.json', 'application/json'
    elif fmt == 'xlsx':
        import pandas as _pd
        buf = _io.BytesIO()
        meta_df = _pd.DataFrame(_meta_rows(meta), columns=['Field', 'Value'])
        df = _pd.DataFrame(results)
        with _pd.ExcelWriter(buf, engine='openpyxl') as writer:
            meta_df.to_excel(writer, index=False, sheet_name='Metadata')
            df.to_excel(writer, index=False, sheet_name='Hasil')
        return buf.getvalue(), f'hasil_{stamp}.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'md':
        lines = ['# Hasil Scraping - AlyxLabs', '']
        for k, v in _meta_rows(meta):
            lines.append(f'- **{k}:** {v}')
        lines += ['', '---', '']
        for i, r in enumerate(results, 1):
            lines.append(f"## {i}. {r.get('title', '')}")
            meta_line = f"**Platform:** {r.get('platform', '')}"
            if r.get('source'): meta_line += f" | **Sumber:** {r.get('source')}"
            if r.get('date'):   meta_line += f" | **Tanggal:** {r.get('date')}"
            lines.append(meta_line)
            if r.get('url'):     lines.append(f"URL: {r.get('url')}")
            lines.append('')
            if r.get('content'): lines.append(r.get('content'))
            lines += ['', '---', '']
        return '\n'.join(lines).encode('utf-8'), f'hasil_{stamp}.md', 'text/markdown'
    elif fmt == 'ris':
        academic = {'OpenAlex', 'Semantic Scholar'}
        lines = []
        for r in results:
            ty = 'JOUR' if r.get('platform', '') in academic else 'NEWS'
            lines += [f'TY  - {ty}']
            if r.get('title'):   lines.append(f"TI  - {r['title']}")
            if r.get('source'):  lines.append(f"AU  - {r['source']}")
            dv = r.get('date', '')
            if dv and len(dv) >= 4 and dv[:4].isdigit(): lines.append(f'PY  - {dv[:4]}')
            if dv: lines.append(f'DA  - {dv}')
            if r.get('url'):     lines.append(f"UR  - {r['url']}")
            snip = r.get('content') or r.get('full_text') or ''
            if snip: lines.append(f"AB  - {' '.join(snip.split())[:500]}")
            lines += ['DP  - AlyxLabs Scraper', 'ER  - ', '']
        return '\n'.join(lines).encode('utf-8'), f'hasil_{stamp}.ris', 'application/x-research-info-systems'
    elif fmt == 'bibtex':
        _ESC = str.maketrans({'\\':'\\\\','{':'\\{','}':'\\}','&':'\\&','%':'\\%','#':'\\#','_':'\\_','^':'\\^','~':'\\~'})
        entries = []
        for i, r in enumerate(results, 1):
            raw = (r.get('source') or r.get('platform') or 'item').split()[0]
            key = (''.join(c for c in raw if c.isalnum()).lower() or 'item') + f'_{i}'
            dv = r.get('date', '')
            yr = dv[:4] if dv and len(dv) >= 4 and dv[:4].isdigit() else ''
            flds = [f'  title = {{{(r.get("title","")).translate(_ESC)}}}']
            if r.get('source'): flds.append(f'  author = {{{r["source"].translate(_ESC)}}}')
            if yr: flds.append(f'  year = {{{yr}}}')
            if r.get('url'):    flds.append(f'  url = {{{r["url"].translate(_ESC)}}}')
            snip = (r.get('content') or r.get('full_text') or '')
            if snip: flds.append(f'  abstract = {{{(" ".join(snip.split())[:400]).translate(_ESC)}}}')
            flds.append('  note = {Scraped via AlyxLabs Scraper}')
            entries.append('@article{' + key + ',\n' + ',\n'.join(flds) + '\n}')
        return ('\n\n'.join(entries) + '\n').encode('utf-8'), f'hasil_{stamp}.bib', 'application/x-bibtex'
    else:  # csv default
        buf = _io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=['title','url','content','date','platform','source','keyword'], extrasaction='ignore')
        writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k,'') for k in ['title','url','content','date','platform','source','keyword']})
        return buf.getvalue().encode('utf-8-sig'), f'hasil_{stamp}.csv', 'text/csv'


def _build_scrape_email(keywords, results, fmt='csv'):
    """Build rich HTML email body + export file bytes from scraping results."""
    import collections
    import io as _io

    kw_str = ', '.join(keywords)
    total  = len(results)

    # --- derive insights from real data ---
    platform_counts = collections.Counter(r.get('platform','') for r in results if r.get('platform'))
    source_counts   = collections.Counter(r.get('source','')   for r in results if r.get('source'))
    top_platform    = platform_counts.most_common(1)[0] if platform_counts else None
    top_source      = source_counts.most_common(1)[0]   if source_counts   else None
    dates = [r.get('date','') for r in results if r.get('date','')]
    date_range = f"{min(dates)[:10]} - {max(dates)[:10]}" if len(dates) >= 2 else (dates[0][:10] if dates else '-')
    platform_breakdown = ', '.join(f"{p} ({c})" for p, c in platform_counts.most_common(4))

    insights = []
    if top_platform:
        insights.append(f"Platform terbanyak: <strong>{top_platform[0]}</strong> ({top_platform[1]} hasil dari {total})")
    if top_source and top_source[0] != top_platform[0] if top_platform else True:
        insights.append(f"Sumber teratas: <strong>{top_source[0]}</strong> ({top_source[1]} artikel)")
    if len(keywords) > 1:
        insights.append(f"Rata-rata per keyword: <strong>{total // len(keywords)}</strong> hasil")
    if dates:
        insights.append(f"Rentang tanggal publikasi artikel: <strong>{date_range}</strong>")
    if len(platform_counts) > 1:
        insights.append(f"Distribusi platform: {platform_breakdown}")

    def esc(s):
        return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;') if s else ''

    preview_rows = ''
    for r in results[:8]:
        title = esc(r.get('title','') or '')[:90]
        src   = esc(r.get('source', r.get('platform','')) or '')
        date  = esc((r.get('date','') or '')[:10])
        url   = r.get('url','') or ''
        preview_rows += (
            f'<tr>'
            f'<td style="padding:10px 0;border-bottom:1px solid #f1f5f9;vertical-align:top">'
            f'<div style="font-size:13px;font-weight:600;color:#0f172a;line-height:1.4;margin-bottom:3px">'
            f'{"<a href=" + chr(34) + esc(url) + chr(34) + " style=" + chr(34) + "color:#6366f1;text-decoration:none" + chr(34) + ">" + title + "</a>" if url else title}'
            f'</div>'
            f'<div style="font-size:11px;color:#94a3b8">{src}{" &middot; " + date if date else ""}</div>'
            f'</td></tr>'
        )

    insight_items = ''.join(f'<li style="padding:4px 0;font-size:13px;color:#334155">{i}</li>' for i in insights)

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 0">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">

  <!-- header -->
  <tr><td style="background:#0f172a;border-radius:12px 12px 0 0;padding:24px 28px">
    <table cellpadding="0" cellspacing="0" width="100%"><tr>
      <td style="width:56px;vertical-align:middle;padding-right:14px">
        <table cellpadding="0" cellspacing="0" border="0" width="56" height="56" style="border-radius:50%;background:#4f46e5;border:2px solid #6366f1"><tr><td align="center" valign="middle" style="font-family:Arial,sans-serif;font-size:18px;font-weight:bold;color:#ffffff;letter-spacing:1px">AL</td></tr></table>
      </td>
      <td style="vertical-align:middle">
        <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#6366f1;text-transform:uppercase;margin-bottom:4px">AlyxLabs Scraper</div>
        <div style="font-size:20px;font-weight:700;color:#f1f5f9">Scraping Selesai</div>
        <div style="font-size:13px;color:#64748b;margin-top:3px">{esc(kw_str)}</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- stat strip -->
  <tr><td style="background:#6366f1;padding:0">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="padding:16px 28px;text-align:center;border-right:1px solid rgba(255,255,255,.15)">
        <div style="font-size:28px;font-weight:800;color:#fff;line-height:1">{total}</div>
        <div style="font-size:11px;color:rgba(255,255,255,.75);margin-top:3px;text-transform:uppercase;letter-spacing:.5px">Hasil</div>
      </td>
      <td style="padding:16px 28px;text-align:center;border-right:1px solid rgba(255,255,255,.15)">
        <div style="font-size:14px;font-weight:700;color:#fff;line-height:1.2">{esc(top_platform[0]) if top_platform else "-"}</div>
        <div style="font-size:11px;color:rgba(255,255,255,.75);margin-top:3px;text-transform:uppercase;letter-spacing:.5px">Platform Utama</div>
      </td>
      <td style="padding:16px 28px;text-align:center">
        <div style="font-size:14px;font-weight:700;color:#fff;line-height:1.2">{len(keywords)}</div>
        <div style="font-size:11px;color:rgba(255,255,255,.75);margin-top:3px;text-transform:uppercase;letter-spacing:.5px">Keyword</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- body -->
  <tr><td style="background:#fff;padding:28px">

    <!-- preview -->
    <div style="font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px">Pratinjau Hasil ({min(8,total)} dari {total})</div>
    <table width="100%" cellpadding="0" cellspacing="0">{preview_rows}</table>
    {f'<div style="font-size:12px;color:#94a3b8;margin-top:8px">+{total-8} hasil lainnya ada di file lampiran.</div>' if total > 8 else ''}

    <!-- insights -->
    <div style="margin-top:24px;padding:16px 18px;background:#f8fafc;border-left:3px solid #6366f1;border-radius:0 8px 8px 0">
      <div style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Ringkasan</div>
      <ul style="margin:0;padding-left:18px">{insight_items}</ul>
    </div>

    <!-- cta -->
    <div style="text-align:center;margin-top:24px">
      <a href="https://scraper.alyxlabs.tech" style="display:inline-block;background:#6366f1;color:#fff;font-size:13px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none">Buka Scraper</a>
    </div>

  </td></tr>

  <!-- footer -->
  <tr><td style="background:#f8fafc;border-radius:0 0 12px 12px;padding:16px 28px;border-top:1px solid #e2e8f0">
    <div style="font-size:11px;color:#94a3b8;text-align:center">File CSV terlampir berisi semua {total} hasil. &middot; AlyxLabs Scraper &middot; scraper.alyxlabs.tech</div>
  </td></tr>

</table>
</td></tr></table>
</body></html>'''

    # --- update footer line to reflect actual format ---
    fmt_label = {'csv':'CSV','json':'JSON','xlsx':'Excel','md':'Markdown','ris':'RIS','bibtex':'BibTeX'}.get(fmt, fmt.upper())
    html = html.replace('File CSV terlampir berisi semua', f'File {fmt_label} terlampir berisi semua')

    # --- build export bytes for the chosen format ---
    meta = {
        'tool': 'AlyxLabs Scraper',
        'keywords': keywords,
        'location': '',
        'date_range': date_range,
        'sources': list({r.get('platform','') for r in results if r.get('platform')}),
        'collected_at': '',
        'duration_seconds': None,
        'total_results': total,
        'per_source': dict(platform_counts),
        'note': 'Snapshot koleksi; hasil scraping dapat berubah seiring waktu.',
    }
    file_bytes, filename, mimetype = _generate_export_bytes(results, meta, fmt)

    return html, file_bytes, filename, mimetype


def _send_notification(notify_email, notify_webhook, results_count, keywords,
                       results=None, notify_format='csv', job_id=None):
    """Fire email and/or webhook after a scraping job finishes. Best-effort only."""
    email_ok = None
    if notify_email:
        cfg = load_config()
        em = cfg.get('email', {})
        sender = em.get('gmail_user', '').strip()
        app_pw = em.get('gmail_app_password', '').strip()
        if sender and app_pw:
            try:
                html_body, file_bytes, filename, mimetype = _build_scrape_email(
                    keywords, results or [], fmt=notify_format)
                _send_email_smtp(sender, app_pw, notify_email,
                                 f'Scraping selesai: {results_count} hasil - AlyxLabs',
                                 html_body,
                                 attachments=[(filename, file_bytes, mimetype)])
                email_ok = True
            except Exception:
                email_ok = False
    if notify_webhook and _is_safe_url(notify_webhook):
        try:
            import requests as _req_n
            _req_n.post(notify_webhook, json={
                'event': 'scraping_finished',
                'results_count': results_count,
                'keywords': keywords,
                'format': notify_format,
                'results': (results or [])[:500],
            }, timeout=10)
        except Exception:
            pass
    if job_id is not None and email_ok is not None:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]['notify_result'] = 'sent' if email_ok else 'failed'
                jobs[job_id]['notify_email_addr'] = notify_email


# ─── Pages ───────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html', enabled_platforms=enabled_platforms())


@app.route('/docs')
def docs():
    return render_template('docs.html')


@app.route('/alyx-control-panel')
@app.route('/alyx-control-panel/login')
@app.route('/alyx-control-panel/dashboard')
def admin_legacy_redirect():
    return redirect(url_for('admin_login'), 301)


@app.route('/admin')
def admin_login():
    if session.get('admin_auth'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html', error=None)


def _password_ok(pw, cfg):
    """Verify pw against the stored hash in config (set after a password reset),
    or against ADMIN_PASSWORD env var for fresh installs before any reset."""
    stored = cfg.get('admin_password', '')
    if stored:
        if stored.startswith(('pbkdf2:', 'scrypt:')):
            return check_password_hash(stored, pw)
        # Legacy plaintext in config - upgrade to hash on success.
        if pw == stored:
            cfg['admin_password'] = generate_password_hash(pw)
            save_config(cfg)
            return True
        return False
    # No hash in config yet - check the env var (initial deployment).
    env_pw = os.environ.get('ADMIN_PASSWORD', '')
    return bool(env_pw) and pw == env_pw


@app.route('/admin/login', methods=['POST'])
@limiter.limit("5 per 15 minutes")
def admin_login_post():
    ip = get_client_ip()
    if _login_blocked(ip):
        return render_template('admin_login.html',
                               error='Terlalu banyak percobaan gagal. Coba lagi dalam 5 menit.'), 429
    pw = request.form.get('password', '')
    cfg = load_config()
    if pw and _password_ok(pw, cfg):
        _clear_login_fails(ip)
        session.permanent = True
        session['admin_auth'] = True
        return redirect(url_for('admin_dashboard'))
    _record_login_fail(ip)
    return render_template('admin_login.html', error='Password salah. Coba lagi.')


@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html', all_platforms=list(SCRAPERS.keys()))


@app.route('/admin/reset-password')
def admin_reset_password():
    token = request.args.get('token', '')
    # Validate token exists and not expired
    cfg = load_config()
    stored = cfg.get('reset_token', {})
    valid = False
    if token and stored.get('token') == token:
        issued = stored.get('issued_at', 0)
        valid = (time.time() - issued) < 3600  # 1 hour
    return render_template('reset_password.html', token=token, valid=valid)


@app.route('/admin/reset-password', methods=['POST'])
def admin_reset_password_post():
    token = request.form.get('token', '')
    new_pw = request.form.get('password', '')
    confirm_pw = request.form.get('confirm_password', '')

    # Validate token
    cfg = load_config()
    stored = cfg.get('reset_token', {})
    if not (token and stored.get('token') == token and
            (time.time() - stored.get('issued_at', 0)) < 3600):
        return render_template('reset_password.html', token=token, valid=False,
                               error='Link reset tidak valid atau sudah kadaluarsa.')

    if not new_pw or len(new_pw) < 6:
        return render_template('reset_password.html', token=token, valid=True,
                               error='Password minimal 6 karakter.')
    if new_pw != confirm_pw:
        return render_template('reset_password.html', token=token, valid=True,
                               error='Password tidak cocok.')

    # Save new password (hashed) & clear token
    cfg['admin_password'] = generate_password_hash(new_pw)
    cfg.pop('reset_token', None)
    save_config(cfg)
    return render_template('reset_password.html', token='', valid=False, success=True)


@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    """Send reset email. Called from admin_login.html JS."""
    # Rate-limit: max 1 request per IP per 60s (blunts email spam / token churn)
    ip = get_client_ip()
    now = time.time()
    with _forgot_lock:
        if now - _forgot_hits.get(ip, 0) < 60:
            return jsonify({'ok': False, 'error': 'Terlalu sering. Coba lagi dalam 1 menit.'}), 429
        _forgot_hits[ip] = now

    cfg = load_config()
    email_cfg = cfg.get('email', {})
    sender = email_cfg.get('gmail_user', '').strip()
    app_pw = email_cfg.get('gmail_app_password', '').strip()
    recipient = email_cfg.get('reset_recipient', 'alivenata@gmail.com').strip()

    if not sender or not app_pw:
        return jsonify({'ok': False, 'error': 'Email belum dikonfigurasi (gmail_user + gmail_app_password di Settings)'}), 400

    # Generate token
    token = str(uuid.uuid4())
    cfg['reset_token'] = {'token': token, 'issued_at': time.time()}
    save_config(cfg)

    # Build reset URL (detect host from request)
    host = request.host_url.rstrip('/')
    reset_url = f"{host}/alyx-control-panel/reset-password?token={token}"

    try:
        subject = 'Reset Password - AlyxLabs Admin'
        body = f"""
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px">
    <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
      display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.1rem;font-weight:700">A</div>
    <span style="font-weight:800;font-size:1.1rem;color:#6366f1">AlyxLabs Admin</span>
  </div>

  <h2 style="font-size:1.3rem;font-weight:700;color:#0f172a;margin:0 0 8px">Reset Password</h2>
  <p style="color:#64748b;font-size:.92rem;line-height:1.6;margin:0 0 24px">
    Kami menerima permintaan reset password untuk akun AlyxLabs Admin.<br>
    Klik tombol di bawah untuk membuat password baru.
  </p>

  <a href="{reset_url}" style="display:inline-block;padding:13px 28px;
    background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;text-decoration:none;
    border-radius:10px;font-weight:600;font-size:.95rem;
    box-shadow:0 4px 16px rgba(99,102,241,.35)">
    Reset Password Sekarang
  </a>

  <p style="color:#94a3b8;font-size:.78rem;margin-top:24px;line-height:1.6">
    Link ini berlaku selama <strong>1 jam</strong>.<br>
    Jika Anda tidak meminta reset password, abaikan email ini.<br><br>
    <a href="{reset_url}" style="color:#6366f1;word-break:break-all">{reset_url}</a>
  </p>

  <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
  <p style="color:#cbd5e1;font-size:.75rem;margin:0">
    &copy; 2024-2026 AlyxLabs Scraper. Jangan balas email ini.
  </p>
</div>
"""
        _send_email_smtp(sender, app_pw, recipient, subject, body)
        return jsonify({'ok': True, 'recipient': recipient})
    except Exception as e:
        # Clean up token if send fails
        cfg2 = load_config()
        cfg2.pop('reset_token', None)
        save_config(cfg2)
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_auth', None)
    return redirect(url_for('admin_login'))


# ─── Scraper API ─────────────────────────────────────────────────────
@app.route('/api/start', methods=['POST'])
@limiter.limit("10 per minute")
def api_start():
    payload = request.json or {}
    keywords_text = payload.get('keywords', '').strip()
    location_raw  = payload.get('location', '').strip()
    platforms = payload.get('platforms', [])
    full_text = bool(payload.get('full_text', False))
    date_from = (payload.get('date_from') or '').strip() or None
    date_to = (payload.get('date_to') or '').strip() or None
    notify_email   = (payload.get('notify_email') or '').strip()[:254]
    notify_webhook = (payload.get('notify_webhook') or '').strip()
    notify_format  = (payload.get('notify_format') or 'csv').strip().lower()
    if notify_format not in ('csv', 'json', 'xlsx', 'md', 'ris', 'bibtex'):
        notify_format = 'csv'

    # Only allow platforms the admin has enabled
    _enabled = set(enabled_platforms())
    platforms = [p for p in platforms if p in _enabled]

    if not keywords_text or not platforms:
        return jsonify({'ok': False, 'error': 'Keywords and at least one platform required'}), 400

    keywords  = [k.strip() for k in keywords_text.split(',') if k.strip()]
    if not keywords:
        return jsonify({'ok': False, 'error': 'No valid keywords'}), 400

    # Multi-location: "Jakarta, Depok" → ['Jakarta', 'Depok']
    # Empty location → [''] (general, no location filter)
    locations = [l.strip() for l in location_raw.split(',') if l.strip()] if location_raw else ['']

    if not _job_semaphore.acquire(blocking=False):
        return jsonify({'ok': False,
                        'error': 'Server sibuk. Maksimum 5 job berjalan bersamaan. Coba lagi nanti.'}), 429

    try:
        job_id = create_job_record()
        with jobs_lock:
            jobs[job_id]['keywords']  = keywords
            jobs[job_id]['locations'] = locations
            jobs[job_id]['location']  = location_raw
            jobs[job_id]['platforms'] = platforms
            jobs[job_id]['date_from']       = date_from
            jobs[job_id]['date_to']         = date_to
            jobs[job_id]['notify_email']    = notify_email
            jobs[job_id]['notify_webhook']  = notify_webhook
            jobs[job_id]['notify_format']   = notify_format

        ip = get_client_ip()
        ua = request.headers.get('User-Agent', '')

        t = Thread(target=run_scraper_job, args=(job_id, keywords, locations, platforms, ip, ua, full_text, date_from, date_to))
        t.daemon = True
        t.start()
    except Exception:
        _job_semaphore.release()
        raise

    return jsonify({'ok': True, 'job_id': job_id})


@app.route('/api/cancel/<job_id>', methods=['POST'])
def api_cancel(job_id):
    with jobs_lock:
        if job_id not in jobs:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        jobs[job_id]['cancelled'] = True
    return jsonify({'ok': True})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        return jsonify({
            'ok': True,
            'status': rec['status'],
            'message': rec['message'],
            'count': len(rec.get('results', [])),
            'notify_result': rec.get('notify_result'),
            'notify_email_addr': rec.get('notify_email_addr', ''),
        })


WIB = timezone(timedelta(hours=7))


def build_metadata(rec):
    """Collection provenance, for research/methodology documentation."""
    results = rec.get('results', [])
    per_source = dict(Counter(r.get('platform', '?') for r in results))
    fin = rec.get('finished_at') or rec.get('started_at')
    collected_at = (datetime.fromtimestamp(fin, WIB).strftime('%Y-%m-%d %H:%M:%S WIB')
                    if fin else '')
    duration = None
    if rec.get('finished_at') and rec.get('started_at'):
        duration = round(rec['finished_at'] - rec['started_at'], 1)
    return {
        'tool': 'AlyxLabs Scraper',
        'keywords': rec.get('keywords', []),
        'location': rec.get('location', ''),
        'date_range': ' s/d '.join(x for x in [rec.get('date_from'), rec.get('date_to')] if x),
        'sources': rec.get('platforms', []),
        'collected_at': collected_at,
        'duration_seconds': duration,
        'total_results': len(results),
        'per_source': per_source,
        'note': 'Snapshot koleksi; hasil scraping dapat berubah seiring waktu.',
    }


def _meta_rows(meta):
    """Ordered (label, value) pairs for the CSV/XLSX metadata block."""
    return [
        ('Tool', meta['tool']),
        ('Keyword', ', '.join(meta['keywords'])),
        ('Lokasi', meta['location'] or '-'),
        ('Rentang tanggal', meta.get('date_range') or '-'),
        ('Sumber', ', '.join(meta['sources'])),
        ('Waktu koleksi', meta['collected_at']),
        ('Durasi (detik)', meta['duration_seconds']),
        ('Total hasil', meta['total_results']),
        ('Per sumber', '; '.join(f'{k}: {v}' for k, v in meta['per_source'].items())),
        ('Catatan', meta['note']),
    ]


@app.route('/api/results/<job_id>')
def api_results(job_id):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        return jsonify({'ok': True, 'results': rec['results'],
                        'metadata': build_metadata(rec)})


@app.route('/api/download/<job_id>/<fmt>')
def api_download(job_id, fmt):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return "Job not found", 404
        data = rec.get('results', [])
        meta = build_metadata(rec)

    platform_filter = request.args.get('platform', '').strip()
    if platform_filter:
        data = [r for r in data if r.get('platform') == platform_filter]

    if not data:
        return "No data", 400

    df = pd.DataFrame(data)
    stamp = job_id[:8]

    if fmt == 'csv':
        # Metadata as leading comment lines (parse with comment='#')
        header = ''.join(f'# {k}: {v}\n' for k, v in _meta_rows(meta))
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        content = header + buf.getvalue()
        return send_file(
            io.BytesIO(content.encode('utf-8-sig')),
            mimetype='text/csv', as_attachment=True,
            download_name=f'alyx_{stamp}.csv'
        )
    elif fmt == 'json':
        buf = io.BytesIO()
        buf.write(json.dumps({'metadata': meta, 'data': data},
                             ensure_ascii=False, indent=2).encode('utf-8'))
        buf.seek(0)
        return send_file(buf, mimetype='application/json', as_attachment=True,
                         download_name=f'alyx_{stamp}.json')
    elif fmt == 'xlsx':
        buf = io.BytesIO()
        meta_df = pd.DataFrame(_meta_rows(meta), columns=['Field', 'Value'])
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            meta_df.to_excel(writer, index=False, sheet_name='Metadata')
            df.to_excel(writer, index=False, sheet_name='Hasil')
        buf.seek(0)
        return send_file(buf,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=f'alyx_{stamp}.xlsx')
    elif fmt == 'md':
        lines = ['# Hasil Scraping - AlyxLabs', '']
        for k, v in _meta_rows(meta):
            lines.append(f'- **{k}:** {v}')
        lines += ['', '---', '']
        for i, r in enumerate(data, 1):
            lines.append(f"## {i}. {r.get('title', '')}")
            meta_line = f"**Platform:** {r.get('platform', '')}"
            if r.get('source'):
                meta_line += f" | **Sumber:** {r.get('source')}"
            if r.get('date'):
                meta_line += f" | **Tanggal:** {r.get('date')}"
            lines.append(meta_line)
            if r.get('url'):
                lines.append(f"URL: {r.get('url')}")
            lines.append('')
            if r.get('content'):
                lines.append(r.get('content'))
            if r.get('full_text'):
                lines += ['', '**Teks lengkap:**', '', r.get('full_text')]
            lines += ['', '---', '']
        content = '\n'.join(lines)
        return send_file(io.BytesIO(content.encode('utf-8')),
                         mimetype='text/markdown', as_attachment=True,
                         download_name=f'alyx_{stamp}.md')
    elif fmt == 'ris':
        # Academic platforms use JOUR type; news/other use NEWS
        academic = {'OpenAlex', 'Semantic Scholar'}
        lines = []
        for r in data:
            ty = 'JOUR' if r.get('platform', '') in academic else 'NEWS'
            lines.append(f'TY  - {ty}')
            if r.get('title'):
                lines.append(f"TI  - {r['title']}")
            if r.get('source'):
                lines.append(f"AU  - {r['source']}")
            # Year from the first 4 chars of date when available
            date_val = r.get('date', '')
            if date_val and len(date_val) >= 4 and date_val[:4].isdigit():
                lines.append(f'PY  - {date_val[:4]}')
            if date_val:
                lines.append(f'DA  - {date_val}')
            if r.get('url'):
                lines.append(f"UR  - {r['url']}")
            snippet = r.get('content') or r.get('full_text') or ''
            if snippet:
                # RIS abstract is single-line; collapse whitespace
                lines.append(f"AB  - {' '.join(snippet.split())[:500]}")
            lines.append('DP  - AlyxLabs Scraper')
            lines.append('ER  - ')
            lines.append('')
        content = '\n'.join(lines)
        return send_file(
            io.BytesIO(content.encode('utf-8')),
            mimetype='application/x-research-info-systems', as_attachment=True,
            download_name=f'alyx_{stamp}.ris'
        )
    elif fmt == 'bibtex':
        _BIB_ESCAPE = str.maketrans({
            '\\': '\\\\', '{': '\\{', '}': '\\}',
            '&': '\\&', '%': '\\%', '#': '\\#',
            '_': '\\_', '^': '\\^', '~': '\\~',
        })
        def bib_safe(s: str) -> str:
            return (s or '').translate(_BIB_ESCAPE)

        entries = []
        for i, r in enumerate(data, 1):
            # Build a clean key: alphanum only, lowercase
            raw_src = (r.get('source') or r.get('platform') or 'item').split()[0]
            key_base = ''.join(c for c in raw_src if c.isalnum()).lower() or 'item'
            key = f'{key_base}_{i}'

            date_val = r.get('date', '')
            year = date_val[:4] if date_val and len(date_val) >= 4 and date_val[:4].isdigit() else ''

            fields = [f'  title = {{{bib_safe(r.get("title", ""))}}}']
            if r.get('source'):
                fields.append(f'  author = {{{bib_safe(r["source"])}}}')
            if year:
                fields.append(f'  year = {{{year}}}')
            if r.get('url'):
                fields.append(f'  url = {{{bib_safe(r["url"])}}}')
            snippet = r.get('content') or r.get('full_text') or ''
            if snippet:
                short = ' '.join(snippet.split())[:400]
                fields.append(f'  abstract = {{{bib_safe(short)}}}')
            fields.append('  note = {Scraped via AlyxLabs Scraper}')

            entries.append('@article{' + key + ',\n' + ',\n'.join(fields) + '\n}')

        content = '\n\n'.join(entries) + '\n'
        return send_file(
            io.BytesIO(content.encode('utf-8')),
            mimetype='application/x-bibtex', as_attachment=True,
            download_name=f'alyx_{stamp}.bib'
        )
    return "Unsupported format", 400


# ─── Image Scraper API ───────────────────────────────────────────────
@app.route('/api/images/scrape-url', methods=['POST'])
@limiter.limit("20 per minute")
def api_images_scrape_url():
    payload = request.json or {}
    url = payload.get('url', '').strip()
    if not url:
        return jsonify({'ok': False, 'error': 'URL required'}), 400
    if not _is_safe_url(url):
        return jsonify({'ok': False, 'error': 'URL tidak diizinkan'}), 400

    ip = get_client_ip()
    ua = request.headers.get('User-Agent', '')
    start = time.time()

    scraper = ImageScraper()
    images = scraper.scrape_from_url(url, max_images=30)

    log_audit(session_id=str(uuid.uuid4()), action='image_scrape',
              keyword=url, platform='Image Scraper', results_count=len(images),
              duration_seconds=round(time.time() - start, 2), ip_address=ip, user_agent=ua)

    return jsonify({'ok': True, 'images': images})


@app.route('/api/images/search', methods=['POST'])
@limiter.limit("20 per minute")
def api_images_search():
    payload = request.json or {}
    query = payload.get('query', '').strip()
    if not query:
        return jsonify({'ok': False, 'error': 'Query required'}), 400

    ip = get_client_ip()
    ua = request.headers.get('User-Agent', '')
    start = time.time()

    scraper = ImageScraper()
    images = scraper.search_images(query, max_images=30)

    log_audit(session_id=str(uuid.uuid4()), action='image_search',
              keyword=query, platform='Image Scraper', results_count=len(images),
              duration_seconds=round(time.time() - start, 2), ip_address=ip, user_agent=ua)

    return jsonify({'ok': True, 'images': images})


@app.route('/api/images/related', methods=['POST'])
def api_images_related():
    payload = request.json or {}
    image_url = payload.get('image_url', '').strip()
    if not image_url:
        return jsonify({'ok': False, 'error': 'Image URL required'}), 400
    if not _is_safe_url(image_url):
        return jsonify({'ok': False, 'error': 'URL tidak diizinkan'}), 400

    scraper = ImageScraper()
    images = scraper.find_related_images(image_url=image_url)
    return jsonify({'ok': True, 'images': images})


@app.route('/api/images/upload', methods=['POST'])
def api_images_upload():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'No file selected'}), 400

    ip = get_client_ip()
    ua = request.headers.get('User-Agent', '')
    start = time.time()

    import base64
    data = file.read()
    b64 = base64.b64encode(data).decode('utf-8')
    content_type = file.content_type or 'image/jpeg'

    scraper = ImageScraper()
    vision_key = (load_config().get('api_keys', {}).get('google_vision', '').strip()
                  or os.environ.get('GOOGLE_VISION_KEY', '').strip())

    images = []
    method = 'filename'
    if vision_key:
        images = scraper.google_reverse_search(data, vision_key, max_images=30)
        if images:
            method = 'vision'
    if not images:
        # No Vision key or no visual match -> fall back to filename keyword search
        keywords = os.path.splitext(file.filename)[0].replace('-', ' ').replace('_', ' ')
        images = scraper.search_images(keywords, max_images=20)

    log_audit(session_id=str(uuid.uuid4()), action='image_upload',
              keyword=file.filename, platform='Image Scraper', results_count=len(images),
              duration_seconds=round(time.time() - start, 2), ip_address=ip, user_agent=ua)

    return jsonify({
        'ok': True,
        'method': method,
        'uploaded': {'data': b64, 'content_type': content_type, 'filename': file.filename},
        'related_images': images
    })


# ─── Ticker News API ──────────────────────────────────────────────────
_ticker_cache = {'items': [], 'ts': 0.0}
_TICKER_TTL = 900  # 15 minutes

def _fetch_ticker_news():
    import xml.etree.ElementTree as ET
    url = 'https://news.google.com/rss?hl=id&gl=ID&ceid=ID:id'
    try:
        r = _requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall('./channel/item')[:20]:
            title_el = item.find('title')
            source_el = item.find('source')
            link_el = item.find('link')
            if title_el is None:
                continue
            raw = title_el.text or ''
            if ' - ' in raw:
                title, source = raw.rsplit(' - ', 1)
            else:
                title = raw
                source = source_el.text if source_el is not None else ''
            url = ''
            if link_el is not None and link_el.text:
                url = link_el.text.strip()
            elif source_el is not None:
                url = source_el.get('url', '')
            items.append({'title': title.strip(), 'source': source.strip(), 'url': url})
        return items
    except Exception:
        return []

@app.route('/api/ticker-news')
def api_ticker_news():
    global _ticker_cache
    now = time.time()
    if now - _ticker_cache['ts'] > _TICKER_TTL or not _ticker_cache['items']:
        items = _fetch_ticker_news()
        if items:
            _ticker_cache = {'items': items, 'ts': now}
    return jsonify(_ticker_cache['items'])


# ─── Feedback API ─────────────────────────────────────────────────────
@app.route('/api/feedback', methods=['POST'])
@limiter.limit("5 per hour")
def api_submit_feedback():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()[:80]
    email = (data.get('email') or '').strip()[:120]
    type_ = data.get('type', 'saran')
    message = (data.get('message') or '').strip()[:2000]
    if type_ not in ('saran', 'kritik', 'bug', 'lainnya'):
        type_ = 'saran'
    if not message:
        return jsonify({'ok': False, 'error': 'Pesan tidak boleh kosong'}), 400
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    submit_feedback(name, email, type_, message, ip)
    return jsonify({'ok': True})


@app.route('/api/admin/feedback')
def api_admin_feedback():
    if not session.get('admin_auth'):
        return jsonify({'error': 'unauthorized'}), 401
    status_filter = request.args.get('status')
    rows = get_feedback(limit=500, status_filter=status_filter or None)
    return jsonify(rows)


@app.route('/api/admin/feedback/<int:fid>/status', methods=['POST'])
def api_admin_feedback_status(fid):
    if not session.get('admin_auth'):
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    status = data.get('status', 'dibaca')
    if status not in ('baru', 'dibaca', 'ditindaklanjuti'):
        return jsonify({'error': 'invalid status'}), 400
    update_feedback_status(fid, status)
    return jsonify({'ok': True})


# ─── Admin API ────────────────────────────────────────────────────────
@app.route('/api/admin/logs')
def api_admin_logs():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    try:
        limit = min(int(request.args.get('limit', 100)), 500)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0
    action = request.args.get('action')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    logs = get_audit_logs(limit=limit, offset=offset, action_filter=action,
                          date_from=date_from, date_to=date_to)
    return jsonify({'ok': True, 'logs': logs, 'count': len(logs)})


@app.route('/api/admin/stats')
def api_admin_stats():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    period = request.args.get('period', 'daily')
    days = int(request.args.get('days', 90))

    usage = get_usage_stats(period=period, days=days)
    keywords = get_top_keywords(days=days)
    platforms = get_top_platforms(days=days)
    summary = get_summary_stats()

    return jsonify({
        'ok': True,
        'usage': usage,
        'top_keywords': keywords,
        'top_platforms': platforms,
        'summary': summary
    })


# ─── Settings API ─────────────────────────────────────────────────────
@app.route('/api/admin/settings', methods=['GET'])
def api_admin_settings_get():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    return jsonify({'ok': True, 'config': load_config()})


@app.route('/api/admin/settings', methods=['POST'])
def api_admin_settings_post():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    data = request.json or {}
    cfg = load_config()
    if 'email' in data:
        em = data['email']
        cfg['email'] = {
            'gmail_user':         em.get('gmail_user', '').strip(),
            'reset_recipient':    em.get('reset_recipient', 'alivenata@gmail.com').strip(),
            'gmail_app_password': em.get('gmail_app_password', ''),
            # smtp_host/smtp_port support non-Gmail SMTP (e.g. cPanel hosting).
            # Key names gmail_user/gmail_app_password kept for backwards compatibility.
            'smtp_host': em.get('smtp_host', 'smtp.gmail.com').strip() or 'smtp.gmail.com',
            'smtp_port': int(em.get('smtp_port', 465) or 465),
        }
    if 'api_keys' in data:
        ak = data['api_keys']
        cfg.setdefault('api_keys', {})
        for k in ('semantic_scholar', 'youtube', 'google_vision'):
            if k in ak:
                cfg['api_keys'][k] = ak[k].strip()
    if 'platforms_disabled' in data:
        cfg['platforms_disabled'] = [p for p in (data.get('platforms_disabled') or []) if p in SCRAPERS]
    if 'twitter' in data:
        tw = data['twitter']
        cfg.setdefault('twitter', {})
        if 'use_twikit' in tw:
            cfg['twitter']['use_twikit'] = bool(tw['use_twikit'])
        if 'nitter_instances' in tw:
            cfg['twitter']['nitter_instances'] = [s.strip() for s in (tw['nitter_instances'] or []) if s.strip()]
    if 'reddit' in data:
        rd = data['reddit']
        cfg.setdefault('reddit', {})
        if 'client_id' in rd:
            cfg['reddit']['client_id'] = rd['client_id'].strip()
        if 'client_secret' in rd:
            cfg['reddit']['client_secret'] = rd['client_secret'].strip()
    save_config(cfg)
    return jsonify({'ok': True})


@app.route('/api/admin/test-email', methods=['POST'])
def api_admin_test_email():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    cfg = load_config()
    em = cfg.get('email', {})
    sender = em.get('gmail_user', '').strip()
    app_pw = em.get('gmail_app_password', '').strip()
    recipient = em.get('reset_recipient', 'alivenata@gmail.com').strip()
    if not sender or not app_pw:
        return jsonify({'ok': False, 'error': 'Email config belum diisi (gmail_user + gmail_app_password di Settings)'}), 400
    try:
        _send_email_smtp(
            sender, app_pw, recipient,
            'Test Email - AlyxLabs Admin',
            f'<p>Konfigurasi email AlyxLabs berhasil! Pengirim: <strong>{sender}</strong></p>'
        )
        return jsonify({'ok': True, 'recipient': recipient})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/admin/rss-health', methods=['POST'])
def api_admin_rss_health():
    """Check reachability of all ID RSS feeds. Returns status + latency per feed."""
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    from scraper import NewsSitesScraper, KompasScraper, Liputan6Scraper
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import requests as _req

    def check_feed(name, url):
        t0 = time.time()
        try:
            resp = _req.head(url, timeout=8, allow_redirects=True,
                             headers={'User-Agent': 'Mozilla/5.0 (feed-health-check)'})
            if resp.status_code >= 400:
                resp = _req.get(url, timeout=8, stream=True,
                                headers={'User-Agent': 'Mozilla/5.0 (feed-health-check)'})
                resp.close()
            latency = round((time.time() - t0) * 1000)
            ok = resp.status_code < 400
            return {'name': name, 'url': url, 'ok': ok,
                    'status_code': resp.status_code, 'latency_ms': latency, 'error': ''}
        except Exception as e:
            latency = round((time.time() - t0) * 1000)
            return {'name': name, 'url': url, 'ok': False,
                    'status_code': None, 'latency_ms': latency, 'error': str(e)[:120]}

    from urllib.parse import quote_plus as _qp
    feeds = list(NewsSitesScraper.ID_RSS) + [
        ('Kompas', KompasScraper.GNEWS_BASE + _qp('berita site:kompas.com')),
        ('Liputan6', Liputan6Scraper.GNEWS_BASE + _qp('berita site:liputan6.com')),
    ]
    results = [None] * len(feeds)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(check_feed, name, url): i
                   for i, (name, url) in enumerate(feeds)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()

    ok_count = sum(1 for r in results if r and r['ok'])
    return jsonify({'ok': True, 'feeds': results,
                    'summary': {'total': len(results), 'healthy': ok_count}})


@app.route('/api/admin/test-scraper', methods=['POST'])
def api_admin_test_scraper():
    """Quick-test a single platform with a keyword. Returns count + sample."""
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    data = request.json or {}
    platform = data.get('platform', '')
    keyword  = data.get('keyword', 'indonesia').strip()

    from scraper import SCRAPERS
    scraper_cls = SCRAPERS.get(platform)
    if not scraper_cls:
        return jsonify({'ok': False, 'error': f'Unknown platform: {platform}'}), 400

    log_msgs = []
    def cb(msg): log_msgs.append(msg)

    try:
        scraper = scraper_cls(gui_callback=cb)
        results = scraper.scrape(keyword, '', max_results=5)
        return jsonify({
            'ok': True,
            'platform': platform,
            'keyword': keyword,
            'count': len(results),
            'log': log_msgs,
            'sample': results[:3],
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'log': log_msgs}), 500


if __name__ == "__main__":
    # Local dev runs over http, so the Secure cookie flag would drop the session.
    app.config['SESSION_COOKIE_SECURE'] = False
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print("\n  AlyxLabs Scraper running at http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=debug)
