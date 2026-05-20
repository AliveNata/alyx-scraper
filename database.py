import sqlite3
import os
import json
from datetime import datetime, timedelta
from threading import Lock

DB_PATH = os.path.join(os.path.dirname(__file__), 'alivyx.db')
db_lock = Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        username TEXT DEFAULT 'anonymous',
        action TEXT NOT NULL,
        keyword TEXT,
        platform TEXT,
        location TEXT,
        results_count INTEGER DEFAULT 0,
        duration_seconds REAL DEFAULT 0,
        ip_address TEXT,
        user_agent TEXT,
        geo_location TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
    CREATE INDEX IF NOT EXISTS idx_audit_ip ON audit_logs(ip_address);
    """)
    conn.commit()
    conn.close()


def log_audit(session_id, action, keyword=None, platform=None, location=None,
              results_count=0, duration_seconds=0, ip_address=None,
              user_agent=None, geo_location=None, username='anonymous'):
    with db_lock:
        conn = get_db()
        conn.execute("""
            INSERT INTO audit_logs
            (session_id, username, action, keyword, platform, location,
             results_count, duration_seconds, ip_address, user_agent, geo_location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, username, action, keyword, platform, location,
              results_count, duration_seconds, ip_address, user_agent, geo_location))
        conn.commit()
        conn.close()


def get_audit_logs(limit=200, offset=0, action_filter=None, date_from=None, date_to=None):
    conn = get_db()
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []

    if action_filter:
        query += " AND action = ?"
        params.append(action_filter)
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_usage_stats(period='daily', days=90):
    conn = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    if period == 'daily':
        group_fmt = '%Y-%m-%d'
    elif period == 'weekly':
        group_fmt = '%Y-%W'
    elif period == 'monthly':
        group_fmt = '%Y-%m'
    elif period == 'quarterly':
        group_fmt = '%Y-%m'
    else:
        group_fmt = '%Y-%m-%d'

    rows = conn.execute(f"""
        SELECT strftime('{group_fmt}', created_at) as period,
               COUNT(*) as total_requests,
               COUNT(DISTINCT ip_address) as unique_users,
               SUM(results_count) as total_results,
               AVG(duration_seconds) as avg_duration
        FROM audit_logs
        WHERE created_at >= ? AND action = 'scrape'
        GROUP BY strftime('{group_fmt}', created_at)
        ORDER BY period
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_keywords(limit=20, days=30):
    conn = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = conn.execute("""
        SELECT keyword, COUNT(*) as count, SUM(results_count) as total_results
        FROM audit_logs
        WHERE created_at >= ? AND action = 'scrape' AND keyword IS NOT NULL
        GROUP BY keyword ORDER BY count DESC LIMIT ?
    """, (cutoff, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_platforms(days=30):
    conn = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = conn.execute("""
        SELECT platform, COUNT(*) as count, SUM(results_count) as total_results
        FROM audit_logs
        WHERE created_at >= ? AND action = 'scrape' AND platform IS NOT NULL
        GROUP BY platform ORDER BY count DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_summary_stats():
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*) as total_scrapes,
            COUNT(DISTINCT ip_address) as unique_users,
            SUM(results_count) as total_results,
            AVG(duration_seconds) as avg_duration,
            COUNT(DISTINCT keyword) as unique_keywords
        FROM audit_logs WHERE action = 'scrape'
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


init_db()
