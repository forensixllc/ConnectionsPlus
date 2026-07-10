from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import os

app = Flask(__name__, static_folder='static')
DB_PATH = '/content/connections.db'  # adjust if needed

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- API: list of hubs (unique pulte_subdomain) ---
@app.route('/api/hubs')
def hubs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT pulte_subdomain FROM connections WHERE pulte_subdomain IS NOT NULL ORDER BY pulte_subdomain')
    rows = cur.fetchall()
    conn.close()
    return jsonify([r['pulte_subdomain'] for r in rows])

# --- API: list of risk categories (unique tags) ---
@app.route('/api/categories')
def categories():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT fraud_risk_tags FROM connections WHERE fraud_risk_tags IS NOT NULL')
    rows = cur.fetchall()
    tags = set()
    for r in rows:
        for t in r['fraud_risk_tags'].split(', '):
            tags.add(t)
    conn.close()
    return jsonify(sorted(tags))

# --- API: search ---
@app.route('/api/search')
def search():
    hub = request.args.get('hub')
    category = request.args.get('category')
    domain = request.args.get('domain')

    conn = get_db_connection()
    cur = conn.cursor()

    # Build query
    query = "SELECT ip, pulte_subdomain, overlap_subdomain, fraud_risk_tags, cname_evidence, cname_shared FROM connections WHERE 1=1"
    params = []

    if hub:
        query += " AND pulte_subdomain = ?"
        params.append(hub)
    if category:
        query += " AND fraud_risk_tags LIKE ?"
        params.append(f'%{category}%')
    if domain:
        query += " AND overlap_subdomain LIKE ?"
        params.append(f'%{domain}%')

    # Limit results for performance
    query += " LIMIT 1000"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            'ip': r['ip'],
            'pulte_subdomain': r['pulte_subdomain'],
            'overlap_subdomain': r['overlap_subdomain'],
            'fraud_risk_tags': r['fraud_risk_tags'],
            'cname_evidence': r['cname_evidence'],
            'cname_shared': r['cname_shared']
        })
    return jsonify(results)

# Serve static HTML (optional)
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)