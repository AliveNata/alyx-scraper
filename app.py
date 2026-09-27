from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from threading import Thread, Lock
from functools import wraps
from datetime import datetime, timezone, timedelta
from collections import Counter
import uuid
import io
import time
import json
import os

from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

from scraper import UnifiedScraper, SCRAPERS
from image_scraper_module import ImageScraper
from database import log_audit, get_audit_logs, get_usage_stats, get_top_keywords, get_top_platforms, get_summary_stats

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'alivyx-secret-key-change-in-prod')
app.permanent_session_lifetime = timedelta(hours=8)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,   # served over HTTPS in prod; disabled for local dev in __main__
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

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return _DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

jobs = {}
jobs_lock = Lock()

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
    return request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()


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
        'platforms': []
    }
    with jobs_lock:
        jobs[job_id] = rec
    return job_id


def run_scraper_job(job_id, keywords, locations, platforms, ip, ua):
    with jobs_lock:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['message'] = 'Starting scraper...'
        jobs[job_id]['started_at'] = time.time()

    try:
        def cb(msg):
            with jobs_lock:
                jobs[job_id]['message'] = msg

        scraper = UnifiedScraper(gui_callback=cb)
        results = scraper.scrape_keywords(keywords, locations, platforms)

        with jobs_lock:
            jobs[job_id]['results'] = results
            jobs[job_id]['status'] = 'finished'
            jobs[job_id]['message'] = f'Finished: {len(results)} results'
            jobs[job_id]['finished_at'] = time.time()

        duration = jobs[job_id]['finished_at'] - jobs[job_id]['started_at']
        location_str = ', '.join(loc for loc in locations if loc)
        for kw in keywords:
            log_audit(
                session_id=job_id, action='scrape',
                keyword=kw, platform=','.join(platforms),
                location=location_str, results_count=len(results),
                duration_seconds=round(duration, 2),
                ip_address=ip, user_agent=ua
            )
    except Exception as e:
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['message'] = f'Error: {str(e)}'
            jobs[job_id]['finished_at'] = time.time()


# ─── Pages ───────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html', platforms=list(SCRAPERS.keys()))


@app.route('/docs')
def docs():
    return render_template('docs.html')


@app.route('/alyx-control-panel')
def admin_login():
    if session.get('admin_auth'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html', error=None)


def _password_ok(pw, cfg):
    """Verify pw against stored admin_password.
    Supports werkzeug hashes; auto-upgrades a legacy plaintext value to a hash
    on first successful login."""
    stored = cfg.get('admin_password', '')
    if not stored:
        return False
    if stored.startswith(('pbkdf2:', 'scrypt:')):
        return check_password_hash(stored, pw)
    # Legacy plaintext -> verify, then upgrade to a hash
    if pw == stored:
        cfg['admin_password'] = generate_password_hash(pw)
        save_config(cfg)
        return True
    return False


@app.route('/alyx-control-panel/login', methods=['POST'])
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


@app.route('/alyx-control-panel/dashboard')
def admin_dashboard():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html')


@app.route('/alyx-control-panel/reset-password')
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


@app.route('/alyx-control-panel/reset-password', methods=['POST'])
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
        return jsonify({'ok': False, 'error': 'Email belum dikonfigurasi di Admin → Settings → Email Config'}), 400

    # Generate token
    token = str(uuid.uuid4())
    cfg['reset_token'] = {'token': token, 'issued_at': time.time()}
    save_config(cfg)

    # Build reset URL (detect host from request)
    host = request.host_url.rstrip('/')
    reset_url = f"{host}/alyx-control-panel/reset-password?token={token}"

    try:
        import yagmail
        yag = yagmail.SMTP(sender, app_pw)
        subject = 'Reset Password — Alyx Admin'
        body = f"""
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px">
    <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
      display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.1rem;font-weight:700">A</div>
    <span style="font-weight:800;font-size:1.1rem;color:#6366f1">Alyx Admin</span>
  </div>

  <h2 style="font-size:1.3rem;font-weight:700;color:#0f172a;margin:0 0 8px">Reset Password</h2>
  <p style="color:#64748b;font-size:.92rem;line-height:1.6;margin:0 0 24px">
    Kami menerima permintaan reset password untuk akun Alyx Admin.<br>
    Klik tombol di bawah untuk membuat password baru.
  </p>

  <a href="{reset_url}" style="display:inline-block;padding:13px 28px;
    background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;text-decoration:none;
    border-radius:10px;font-weight:600;font-size:.95rem;
    box-shadow:0 4px 16px rgba(99,102,241,.35)">
    🔑 Reset Password Sekarang
  </a>

  <p style="color:#94a3b8;font-size:.78rem;margin-top:24px;line-height:1.6">
    Link ini berlaku selama <strong>1 jam</strong>.<br>
    Jika Anda tidak meminta reset password, abaikan email ini.<br><br>
    <a href="{reset_url}" style="color:#6366f1;word-break:break-all">{reset_url}</a>
  </p>

  <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
  <p style="color:#cbd5e1;font-size:.75rem;margin:0">
    © 2024-2026 Alyx Scraper. Jangan balas email ini.
  </p>
</div>
"""
        yag.send(to=recipient, subject=subject, contents=body)
        return jsonify({'ok': True, 'recipient': recipient})
    except Exception as e:
        # Clean up token if send fails
        cfg2 = load_config()
        cfg2.pop('reset_token', None)
        save_config(cfg2)
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/alyx-control-panel/logout')
def admin_logout():
    session.pop('admin_auth', None)
    return redirect(url_for('admin_login'))


# ─── Scraper API ─────────────────────────────────────────────────────
@app.route('/api/start', methods=['POST'])
def api_start():
    payload = request.json or {}
    keywords_text = payload.get('keywords', '').strip()
    location_raw  = payload.get('location', '').strip()
    platforms = payload.get('platforms', [])

    if not keywords_text or not platforms:
        return jsonify({'ok': False, 'error': 'Keywords and at least one platform required'}), 400

    keywords  = [k.strip() for k in keywords_text.split(',') if k.strip()]
    if not keywords:
        return jsonify({'ok': False, 'error': 'No valid keywords'}), 400

    # Multi-location: "Jakarta, Depok" → ['Jakarta', 'Depok']
    # Empty location → [''] (general, no location filter)
    locations = [l.strip() for l in location_raw.split(',') if l.strip()] if location_raw else ['']

    job_id = create_job_record()
    with jobs_lock:
        jobs[job_id]['keywords']  = keywords
        jobs[job_id]['locations'] = locations
        jobs[job_id]['location']  = location_raw
        jobs[job_id]['platforms'] = platforms

    ip = get_client_ip()
    ua = request.headers.get('User-Agent', '')

    t = Thread(target=run_scraper_job, args=(job_id, keywords, locations, platforms, ip, ua))
    t.daemon = True
    t.start()

    return jsonify({'ok': True, 'job_id': job_id})


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
            'count': len(rec.get('results', []))
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
        'tool': 'Alyx Scraper',
        'keywords': rec.get('keywords', []),
        'location': rec.get('location', ''),
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
    return "Unsupported format", 400


# ─── Image Scraper API ───────────────────────────────────────────────
@app.route('/api/images/scrape-url', methods=['POST'])
def api_images_scrape_url():
    payload = request.json or {}
    url = payload.get('url', '').strip()
    if not url:
        return jsonify({'ok': False, 'error': 'URL required'}), 400

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

    scraper = ImageScraper()
    images = scraper.find_related_images(image_url=image_url)
    return jsonify({'ok': True, 'images': images})


@app.route('/api/images/upload', methods=['POST'])
def api_images_upload():
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
    cfg = load_config()
    vision_key = (cfg.get('google_vision_key') or os.environ.get('GOOGLE_VISION_API_KEY', '')).strip()

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


# ─── Admin API ────────────────────────────────────────────────────────
@app.route('/api/admin/logs')
def api_admin_logs():
    if not session.get('admin_auth'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))
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
            'gmail_user':        em.get('gmail_user', '').strip(),
            'gmail_app_password': em.get('gmail_app_password', '').strip(),
            'reset_recipient':   em.get('reset_recipient', 'alivenata@gmail.com').strip(),
        }
    if 'google_vision_key' in data:
        cfg['google_vision_key'] = (data.get('google_vision_key') or '').strip()
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
        return jsonify({'ok': False, 'error': 'Email config belum diisi'}), 400
    try:
        import yagmail
        yag = yagmail.SMTP(sender, app_pw)
        yag.send(
            to=recipient,
            subject='Test Email — Alyx Admin',
            contents=f'<p>✅ Konfigurasi email Alyx berhasil! Pengirim: <strong>{sender}</strong></p>'
        )
        return jsonify({'ok': True, 'recipient': recipient})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


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
    # Local dev runs over http, so the Secure cookie flag would drop the session
    app.config['SESSION_COOKIE_SECURE'] = False
    print("\n  Alyx Scraper running at http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
