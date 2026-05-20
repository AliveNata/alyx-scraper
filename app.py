from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from threading import Thread, Lock
import uuid
import io
import time
import json
import os
import hashlib

import pandas as pd

from scraper import UnifiedScraper, SCRAPERS
from image_scraper_module import ImageScraper
from database import log_audit, get_audit_logs, get_usage_stats, get_top_keywords, get_top_platforms, get_summary_stats

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'alivyx-secret-key-change-in-prod')

ADMIN_KEY = os.environ.get('ADMIN_KEY', 'alivyx2024admin')
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


def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()


def create_job_record():
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


@app.route('/alyx-control-panel/login', methods=['POST'])
def admin_login_post():
    pw = request.form.get('password', '')
    # Check config override first, then fallback to default
    cfg = load_config()
    correct_pw = cfg.get('admin_password', 'Alyvx@password!')
    if pw == correct_pw:
        session['admin_auth'] = True
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html', error='Password salah. Coba lagi.')


@app.route('/alyx-control-panel/dashboard')
def admin_dashboard():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html', admin_key=ADMIN_KEY)


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

    # Save new password & clear token
    cfg['admin_password'] = new_pw
    cfg.pop('reset_token', None)
    save_config(cfg)
    return render_template('reset_password.html', token='', valid=False, success=True)


@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    """Send reset email. Called from admin_login.html JS."""
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


@app.route('/api/results/<job_id>')
def api_results(job_id):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        return jsonify({'ok': True, 'results': rec['results']})


@app.route('/api/download/<job_id>/<fmt>')
def api_download(job_id, fmt):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return "Job not found", 404
        data = rec.get('results', [])

    if not data:
        return "No data", 400

    df = pd.DataFrame(data)

    if fmt == 'csv':
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        buf.seek(0)
        return send_file(
            io.BytesIO(buf.getvalue().encode('utf-8-sig')),
            mimetype='text/csv', as_attachment=True,
            download_name=f'alivyx_{job_id[:8]}.csv'
        )
    elif fmt == 'json':
        buf = io.BytesIO()
        buf.write(json.dumps({'data': data}, ensure_ascii=False, indent=2).encode('utf-8'))
        buf.seek(0)
        return send_file(buf, mimetype='application/json', as_attachment=True,
                         download_name=f'alivyx_{job_id[:8]}.json')
    elif fmt == 'xlsx':
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='results')
        buf.seek(0)
        return send_file(buf,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=f'alivyx_{job_id[:8]}.xlsx')
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
    keywords = os.path.splitext(file.filename)[0].replace('-', ' ').replace('_', ' ')
    images = scraper.search_images(keywords, max_images=20)

    log_audit(session_id=str(uuid.uuid4()), action='image_upload',
              keyword=file.filename, platform='Image Scraper', results_count=len(images),
              duration_seconds=round(time.time() - start, 2), ip_address=ip, user_agent=ua)

    return jsonify({
        'ok': True,
        'uploaded': {'data': b64, 'content_type': content_type, 'filename': file.filename},
        'related_images': images
    })


# ─── Admin API ────────────────────────────────────────────────────────
@app.route('/api/admin/logs')
def api_admin_logs():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403

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
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403

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
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    return jsonify({'ok': True, 'config': load_config()})


@app.route('/api/admin/settings', methods=['POST'])
def api_admin_settings_post():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    data = request.json or {}
    cfg = load_config()
    if 'twitter' in data:
        tw = data['twitter']
        cfg['twitter'] = {
            'use_twikit': bool(tw.get('use_twikit', False)),
            'nitter_instances': [
                s.strip() for s in tw.get('nitter_instances', []) if s.strip()
            ]
        }
    if 'email' in data:
        em = data['email']
        cfg['email'] = {
            'gmail_user':        em.get('gmail_user', '').strip(),
            'gmail_app_password': em.get('gmail_app_password', '').strip(),
            'reset_recipient':   em.get('reset_recipient', 'alivenata@gmail.com').strip(),
        }
    save_config(cfg)
    return jsonify({'ok': True})


@app.route('/api/admin/test-email', methods=['POST'])
def api_admin_test_email():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
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


@app.route('/api/admin/platform-status')
def api_admin_platform_status():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403

    cfg = load_config()

    # Instagram
    ig = cfg.get('instagram', {})
    ig_user = ig.get('username', '')
    ig_session = ig.get('session_file', '')
    ig_ready = bool(ig_user and ig_session and os.path.exists(ig_session))

    # Facebook package check
    try:
        import facebook_scraper  # noqa
        fb_pkg = True
    except ImportError:
        fb_pkg = False

    # Twitter / twikit
    tw_cfg = cfg.get('twitter', {})
    use_twikit = tw_cfg.get('use_twikit', False)
    tw_user = tw_cfg.get('username', '')
    cookies_path = os.path.join(os.path.dirname(__file__), 'twitter_cookies.json')
    tw_ready = use_twikit and os.path.exists(cookies_path)

    return jsonify({
        'ok': True,
        'status': {
            'instagram':      ig_ready,
            'instagram_user': ig_user if ig_ready else '',
            'facebook_pkg':   fb_pkg,
            'twitter':        tw_ready,
            'twitter_user':   tw_user if tw_ready else '',
        }
    })


@app.route('/api/admin/pip-install', methods=['POST'])
def api_admin_pip_install():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    import subprocess, sys
    pkg = (request.json or {}).get('package', '').strip()
    if not pkg or any(c in pkg for c in [';', '&', '|', '`', '$']):
        return jsonify({'ok': False, 'error': 'Invalid package name'}), 400
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', pkg],
            capture_output=True, text=True, timeout=120
        )
        success = result.returncode == 0
        return jsonify({
            'ok': success,
            'stdout': result.stdout[-3000:],
            'stderr': result.stderr[-1000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'Timeout (120s)'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/admin/login-instagram', methods=['POST'])
def api_admin_login_instagram():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    data = request.json or {}
    username   = data.get('username', '').strip()
    session_id = data.get('session_id', '').strip()   # preferred: cookie-based
    password   = data.get('password', '').strip()     # fallback: password login

    if not username:
        return jsonify({'ok': False, 'error': 'Username wajib diisi'}), 400

    try:
        import instaloader
        session_file = os.path.join(os.path.dirname(__file__), f'ig_session_{username}')
        L = instaloader.Instaloader()

        if session_id:
            # ── Method 1: Session ID cookie (most reliable, no bot detection) ──
            import requests as req_lib
            # Build a minimal session using the sessionid cookie
            L.context._session.cookies.set('sessionid', session_id,
                                            domain='.instagram.com', path='/')
            # Verify the session is valid by fetching own profile
            test_resp = L.context._session.get(
                'https://www.instagram.com/api/v1/accounts/current_user/?edit=true',
                headers={
                    'User-Agent': 'Instagram 155.0.0.37.107',
                    'X-CSRFToken': L.context._session.cookies.get('csrftoken', ''),
                }
            )
            if test_resp.status_code == 200:
                user_data = test_resp.json().get('user', {})
                verified_user = user_data.get('username', username)
                L.context.username = verified_user
                L.save_session_to_file(filename=session_file)
                cfg = load_config()
                cfg['instagram'] = {'username': verified_user, 'session_file': session_file}
                save_config(cfg)
                return jsonify({'ok': True, 'message': f'Session aktif sebagai @{verified_user}',
                                'method': 'session_id'})
            else:
                return jsonify({'ok': False,
                                'error': f'Session ID tidak valid (HTTP {test_resp.status_code}). '
                                         'Pastikan session ID masih aktif dan disalin dengan benar.'})

        elif password:
            # ── Method 2: Username + Password (may be blocked by Instagram) ──
            L.login(username, password)
            L.save_session_to_file(filename=session_file)
            cfg = load_config()
            cfg['instagram'] = {'username': username, 'session_file': session_file}
            save_config(cfg)
            return jsonify({'ok': True, 'message': f'Login berhasil sebagai @{username}',
                            'method': 'password'})
        else:
            return jsonify({'ok': False, 'error': 'Isi Session ID atau Password'}), 400

    except Exception as e:
        err = str(e)
        if 'checkpoint' in err.lower() or '2fa' in err.lower() or 'challenge' in err.lower():
            return jsonify({'ok': False,
                            'error': 'Akun butuh verifikasi 2FA/Checkpoint. '
                                     'Gunakan metode Session ID sebagai gantinya.',
                            'checkpoint': True})
        if 'bad credentials' in err.lower() or 'wrong password' in err.lower():
            return jsonify({'ok': False, 'error': 'Username atau password salah.'})
        return jsonify({'ok': False, 'error': err[:200]})


@app.route('/api/admin/instagram-status', methods=['GET'])
def api_admin_instagram_status():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    cfg = load_config()
    ig = cfg.get('instagram', {})
    username = ig.get('username', '')
    session_file = ig.get('session_file', '')
    logged_in = bool(username and session_file and os.path.exists(session_file))
    return jsonify({'ok': True, 'logged_in': logged_in, 'username': username})


@app.route('/api/admin/logout-instagram', methods=['POST'])
def api_admin_logout_instagram():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    cfg = load_config()
    ig = cfg.get('instagram', {})
    session_file = ig.get('session_file', '')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
        except Exception:
            pass
    cfg.pop('instagram', None)
    save_config(cfg)
    return jsonify({'ok': True})


@app.route('/api/admin/twitter-status', methods=['GET'])
def api_admin_twitter_status():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    cfg = load_config()
    tw = cfg.get('twitter', {})
    cookies_path = os.path.join(os.path.dirname(__file__), 'twitter_cookies.json')
    logged_in = tw.get('use_twikit', False) and os.path.exists(cookies_path)
    username = tw.get('username', '') if logged_in else ''
    return jsonify({'ok': True, 'logged_in': logged_in, 'username': username})


@app.route('/api/admin/login-twitter', methods=['POST'])
def api_admin_login_twitter():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    data       = request.json or {}
    method     = data.get('method', 'password')   # 'cookie' or 'password'
    username   = data.get('username', '').strip()

    if not username:
        return jsonify({'ok': False, 'error': 'Username wajib diisi'}), 400

    cookies_path = os.path.join(os.path.dirname(__file__), 'twitter_cookies.json')

    # ── Method 1: Auth Token + ct0 (cookie-based, most reliable) ──
    if method == 'cookie':
        auth_token = data.get('auth_token', '').strip()
        ct0        = data.get('ct0', '').strip()
        if not auth_token or not ct0:
            return jsonify({'ok': False, 'error': 'auth_token dan ct0 wajib diisi'}), 400
        try:
            import asyncio
            from twikit import Client

            # Write cookies directly in twikit's expected format (simple dict)
            # twikit's save_cookies/load_cookies uses {"name": "value"} JSON
            cookie_dict = {
                'auth_token': auth_token,
                'ct0':        ct0,
            }
            with open(cookies_path, 'w') as f:
                json.dump(cookie_dict, f)

            async def _do_cookie_login():
                client = Client('en-US')
                client.load_cookies(cookies_path)
                # Verify session by fetching own profile
                try:
                    me = await client.user()
                    verified = getattr(me, 'screen_name', None) or getattr(me, 'name', username)
                except Exception:
                    verified = username
                # Re-save after loading (may add more cookies from server)
                client.save_cookies(cookies_path)
                return verified

            loop = asyncio.new_event_loop()
            try:
                verified_user = loop.run_until_complete(_do_cookie_login())
            finally:
                loop.close()

            cfg = load_config()
            if 'twitter' not in cfg:
                cfg['twitter'] = {}
            cfg['twitter']['use_twikit'] = True
            cfg['twitter']['username'] = verified_user
            save_config(cfg)
            return jsonify({
                'ok': True,
                'message': f'Token valid! Session aktif sebagai @{verified_user}.',
                'username': verified_user,
            })

        except ImportError:
            return jsonify({'ok': False, 'error': 'twikit belum terinstall. Pip install twikit dulu.'})
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Token tidak valid atau expired: {str(e)[:200]}'})

    # ── Method 2: Username + Password (may fail if X changes flow) ──
    else:
        email    = data.get('email', '').strip()
        password = data.get('password', '').strip()
        if not password:
            return jsonify({'ok': False, 'error': 'Password wajib diisi'}), 400
        try:
            import asyncio
            from twikit import Client

            async def _do_pw_login():
                client = Client('en-US')
                kwargs = {'auth_info_1': username, 'password': password}
                if email and email != username:
                    kwargs['auth_info_2'] = email
                await client.login(**kwargs)
                client.save_cookies(cookies_path)
                try:
                    me = await client.user()
                    return me.screen_name if hasattr(me, 'screen_name') else username
                except Exception:
                    return username

            loop = asyncio.new_event_loop()
            try:
                verified_user = loop.run_until_complete(_do_pw_login())
            finally:
                loop.close()

            cfg = load_config()
            if 'twitter' not in cfg:
                cfg['twitter'] = {}
            cfg['twitter']['use_twikit'] = True
            cfg['twitter']['username'] = verified_user
            save_config(cfg)
            return jsonify({
                'ok': True,
                'message': f'Login berhasil sebagai @{verified_user}.',
                'username': verified_user,
            })

        except ImportError:
            return jsonify({'ok': False, 'error': 'twikit belum terinstall. Jalankan: pip install twikit'})
        except Exception as e:
            err = str(e)
            if 'key_byte' in err.lower() or 'indices' in err.lower():
                return jsonify({'ok': False,
                    'error': 'Twitter mengubah flow login (KEY_BYTE error). Gunakan metode Auth Token sebagai gantinya.'})
            if 'incorrect' in err.lower() or 'wrong' in err.lower() or 'bad' in err.lower():
                return jsonify({'ok': False, 'error': 'Username atau password salah.'})
            if '2fa' in err.lower() or 'verification' in err.lower():
                return jsonify({'ok': False, 'error': 'Akun butuh verifikasi 2FA. Gunakan metode Auth Token.'})
            if 'suspend' in err.lower() or 'locked' in err.lower():
                return jsonify({'ok': False, 'error': 'Akun di-suspend atau dikunci oleh X.'})
            return jsonify({'ok': False, 'error': err[:250]})


@app.route('/api/admin/logout-twitter', methods=['POST'])
def api_admin_logout_twitter():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    cookies_path = os.path.join(os.path.dirname(__file__), 'twitter_cookies.json')
    if os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
        except Exception:
            pass
    cfg = load_config()
    if 'twitter' in cfg:
        cfg['twitter']['use_twikit'] = False
        cfg['twitter'].pop('username', None)
        save_config(cfg)
    return jsonify({'ok': True})


@app.route('/api/admin/test-nitter', methods=['POST'])
def api_admin_test_nitter():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403
    data = request.json or {}
    instances = [s.strip() for s in data.get('instances', []) if s.strip()]
    results = []
    for inst in instances:
        try:
            r = __import__('requests').get(inst, timeout=6, allow_redirects=True)
            results.append({'instance': inst, 'ok': r.status_code < 400})
        except Exception:
            results.append({'instance': inst, 'ok': False})
    return jsonify({'ok': True, 'results': results})


@app.route('/api/admin/test-scraper', methods=['POST'])
def api_admin_test_scraper():
    """Quick-test a single platform with a keyword. Returns count + sample."""
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return jsonify({'ok': False}), 403

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
    print("\n  Alyx Scraper running at http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
