import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template
from tester.runner import execute_test_suite

app = Flask(__name__)

# --- GESTION SQLITE INTÉGRÉE ---
DB_FILE = Path(__file__).resolve().parent / "runs.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            api_name TEXT NOT NULL,
            passed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            error_rate REAL NOT NULL,
            latency_avg REAL NOT NULL,
            latency_p95 REAL NOT NULL,
            raw_details TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_run(run: dict):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    s = run["summary"]
    c.execute(
        """
        INSERT INTO runs (timestamp, api_name, passed, failed, error_rate, latency_avg, latency_p95, raw_details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            run["timestamp"],
            run["api"],
            s["passed"],
            s["failed"],
            s["error_rate"],
            s["latency_ms_avg"],
            s["latency_ms_p95"],
            json.dumps(run["tests"]),
        ),
    )
    conn.commit()
    conn.close()


def list_runs(limit: int = 10):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "api_name": r["api_name"],
            "passed": r["passed"],
            "failed": r["failed"],
            "error_rate": round(r["error_rate"] * 100, 1),
            "latency_avg": round(r["latency_avg"], 2),
            "latency_p95": round(r["latency_p95"], 2),
            "tests": json.loads(r["raw_details"]),
        }
        for r in rows
    ]


# Initialisation de la table au démarrage
init_db()


# --- ROUTES FLASK ---
@app.get("/")
@app.get("/dashboard")
def dashboard():
    runs = list_runs(limit=10)
    last_run = runs[0] if runs else None
    return render_template("dashboard.html", runs=runs, last_run=last_run)


@app.get("/run")
def trigger_run():
    data = execute_test_suite()
    save_run(data)
    return jsonify(data)


@app.get("/health")
def health():
    runs = list_runs(limit=1)
    if not runs:
        return jsonify({"status": "OK", "details": "Aucun run enregistré"}), 200
    last = runs[0]
    return (
        jsonify({
            "status": "HEALTHY" if last["failed"] == 0 else "DEGRADED",
            "last_run": last["timestamp"],
            "error_rate": f"{last['error_rate']}%",
            "latency_avg_ms": last["latency_avg"],
        }),
        200,
    )
