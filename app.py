from flask import Flask, render_template, request, jsonify, send_file, url_for
from threading import Thread, Lock
import uuid
import io
import time
import pandas as pd
import json
import os

# Import EnhancedPetScraper dari scraper.py (file yang Anda upload)
from scraper import EnhancedPetScraper

app = Flask(__name__, static_folder='static', template_folder='templates')

# Simple in-memory job store (not persistent). Use DB in production.
jobs = {}   # job_id -> {status, message, results(list of dict), started_at, finished_at}
jobs_lock = Lock()

def create_job_record():
    job_id = str(uuid.uuid4())
    rec = {
        'status': 'queued',
        'message': 'Job queued',
        'results': [],
        'started_at': None,
        'finished_at': None
    }
    with jobs_lock:
        jobs[job_id] = rec
    return job_id

def run_scraper_job(job_id, keywords, location, platforms):
    """Background thread target: run EnhancedPetScraper and store results"""
    with jobs_lock:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['message'] = 'Starting scraper...'
        jobs[job_id]['started_at'] = time.time()
    try:
        def gui_update(msg):
            # update message in job record (safe)
            with jobs_lock:
                jobs[job_id]['message'] = msg

        scraper = EnhancedPetScraper(gui_callback=gui_update)
        selected_platforms = platforms  # list of platform names coming from client
        results = scraper.scrape_keywords(keywords, location, selected_platforms)

        with jobs_lock:
            jobs[job_id]['results'] = results
            jobs[job_id]['status'] = 'finished'
            jobs[job_id]['message'] = f'Finished: {len(results)} results'
            jobs[job_id]['finished_at'] = time.time()
    except Exception as e:
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['message'] = f'Error: {str(e)}'
            jobs[job_id]['finished_at'] = time.time()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    payload = request.json or {}
    keywords_text = payload.get('keywords','').strip()
    location = payload.get('location','').strip()
    platforms = payload.get('platforms', [])  # e.g. ["Google News", "News Sites"]

    if not keywords_text or not location or not platforms:
        return jsonify({'ok': False, 'error': 'keywords, location, and at least one platform required'}), 400

    keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
    if not keywords:
        return jsonify({'ok': False, 'error': 'No valid keywords parsed'}), 400

    job_id = create_job_record()
    # start thread
    t = Thread(target=run_scraper_job, args=(job_id, keywords, location, platforms))
    t.daemon = True
    t.start()

    return jsonify({'ok': True, 'job_id': job_id})

@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({'ok': False, 'error': 'job_id not found'}), 404
        # return small summary
        return jsonify({
            'ok': True,
            'status': rec['status'],
            'message': rec['message'],
            'count': len(rec.get('results', []))
        })

@app.route('/results/<job_id>')
def results(job_id):
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({'ok': False, 'error': 'job_id not found'}), 404
        return jsonify({'ok': True, 'results': rec['results']})

@app.route('/download/<job_id>/<fmt>')
def download(job_id, fmt):
    """fmt = csv | json | xlsx"""
    with jobs_lock:
        rec = jobs.get(job_id)
        if not rec:
            return "job not found", 404
        data = rec.get('results', [])

    df = pd.DataFrame(data)
    if df.empty:
        return "No data to download", 400

    if fmt == 'csv':
        bio = io.StringIO()
        df.to_csv(bio, index=False, encoding='utf-8-sig')
        bio.seek(0)
        return send_file(io.BytesIO(bio.getvalue().encode('utf-8-sig')),
                         mimetype='text/csv',
                         as_attachment=True,
                         download_name=f'scrape_{job_id}.csv')
    elif fmt == 'json':
        bio = io.BytesIO()
        bio.write(json.dumps({'data': data}, ensure_ascii=False, indent=2).encode('utf-8'))
        bio.seek(0)
        return send_file(bio, mimetype='application/json', as_attachment=True,
                         download_name=f'scrape_{job_id}.json')
    elif fmt == 'xlsx':
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='results')
        bio.seek(0)
        return send_file(bio, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=f'scrape_{job_id}.xlsx')
    else:
        return "Unsupported format", 400

if __name__ == "__main__":
    from pyngrok import ngrok
    public_url = ngrok.connect(5000)
    print(" * Ngrok tunnel URL:", public_url)
    app.run(host="0.0.0.0", port=5000)
