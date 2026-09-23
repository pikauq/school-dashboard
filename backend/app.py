import os
import json
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, g
from flask_cors import CORS

try:
    import anthropic
except ImportError:
    anthropic = None

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "data.db")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

app = Flask(__name__)
CORS(app)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,      -- 'school' or 'hobby'
            course TEXT,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_type TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def get_client():
    if anthropic is None:
        raise RuntimeError("anthropic package not installed — run pip install -r requirements.txt")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def call_claude_json(system_prompt, user_text):
    client = get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


def week_bounds(d=None):
    d = d or datetime.utcnow()
    start = d - timedelta(days=d.weekday())  # Monday
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


# ---------- Tasks ----------

@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    category = request.args.get("category")
    db = get_db()
    q = "SELECT * FROM tasks WHERE status = 'pending'"
    params = []
    if category:
        q += " AND category = ?"
        params.append(category)
    q += " ORDER BY created_at DESC"
    rows = db.execute(q, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/tasks/manual", methods=["POST"])
def add_task_manual():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (category, course, description, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (data["category"], data.get("course"), data["description"], datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/agent/add", methods=["POST"])
def agent_add():
    """Natural-language task entry, e.g. 'I have this homework and review for csc258'."""
    text = request.get_json(force=True).get("text", "")
    system = (
        "You extract to-do items from a student's message. Return ONLY a JSON array, "
        "no prose, no markdown fences. Each item: "
        '{"category": "school"|"hobby", "course": string|null, "description": string}. '
        "Split multiple tasks into separate items. If a course code (e.g. csc258) is "
        "mentioned, use it as course and category 'school'. If nothing suggests school, "
        "use category 'hobby' and course null."
    )
    try:
        items = call_claude_json(system, text)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    db = get_db()
    created = []
    now = datetime.utcnow().isoformat()
    for item in items:
        cur = db.execute(
            "INSERT INTO tasks (category, course, description, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (item.get("category", "hobby"), item.get("course"), item["description"], now),
        )
        created.append(cur.lastrowid)
    db.commit()
    return jsonify({"created_ids": created, "items": items}), 201


@app.route("/api/tasks/<int:task_id>/complete", methods=["POST"])
def complete_task(task_id):
    db = get_db()
    db.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), task_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/tasks/this-week", methods=["GET"])
def this_week():
    start, end = week_bounds()
    db = get_db()
    pending = db.execute("SELECT * FROM tasks WHERE status = 'pending'").fetchall()
    done = db.execute(
        "SELECT * FROM tasks WHERE status = 'done' AND completed_at >= ? AND completed_at < ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return jsonify({
        "pending": [dict(r) for r in pending],
        "completed_this_week": [dict(r) for r in done],
    })


# ---------- Stats ----------

@app.route("/api/stats", methods=["GET"])
def stats():
    db = get_db()
    lifetime = db.execute("SELECT COUNT(*) c FROM tasks WHERE status = 'done'").fetchone()["c"]
    rows = db.execute(
        "SELECT strftime('%Y-%W', completed_at) wk, COUNT(*) c FROM tasks "
        "WHERE status = 'done' GROUP BY wk ORDER BY wk DESC LIMIT 52"
    ).fetchall()
    weekly = [{"week": r["wk"], "completed": r["c"]} for r in rows][::-1]
    return jsonify({"lifetime_completed": lifetime, "weekly": weekly})


@app.route("/api/agent/weekly-summary", methods=["POST"])
def weekly_summary():
    start, end = week_bounds()
    db = get_db()
    done = db.execute(
        "SELECT description, category, course FROM tasks WHERE status='done' AND completed_at >= ? AND completed_at < ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    pending = db.execute("SELECT description, category, course FROM tasks WHERE status='pending'").fetchall()

    payload = {
        "completed_this_week": [dict(r) for r in done],
        "still_pending": [dict(r) for r in pending],
    }
    system = (
        "You are a supportive but honest weekly review assistant for a student. Given JSON of "
        "completed and pending tasks, write a short summary (plain text, 3 short sections: "
        "'Went well', 'Could improve', 'Suggestions for next week'). No JSON in the output."
    )
    try:
        client = get_client()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"summary": text})


# ---------- Calendar / syllabus ----------

@app.route("/api/calendar", methods=["GET"])
def calendar():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM calendar_events WHERE event_date >= ? ORDER BY event_date ASC",
        (datetime.utcnow().date().isoformat(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/agent/syllabus", methods=["POST"])
def agent_syllabus():
    data = request.get_json(force=True)
    course = data.get("course", "")
    text = data.get("text", "")
    system = (
        "Extract important dated events from this course syllabus text. Return ONLY a JSON "
        'array, each item: {"title": string, "event_date": "YYYY-MM-DD", "event_type": '
        '"exam"|"assignment"|"other"}. Skip anything without a clear date. Assume the current '
        f"year is {datetime.utcnow().year} if no year is given."
    )
    try:
        items = call_claude_json(system, text)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    db = get_db()
    created = []
    for item in items:
        cur = db.execute(
            "INSERT INTO calendar_events (course, title, event_date, event_type) VALUES (?, ?, ?, ?)",
            (course, item["title"], item["event_date"], item.get("event_type", "other")),
        )
        created.append(cur.lastrowid)
    db.commit()
    return jsonify({"created_ids": created, "items": items}), 201


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
else:
    init_db()
