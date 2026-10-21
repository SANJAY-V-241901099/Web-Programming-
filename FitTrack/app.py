import csv
import io
import os
import re
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "fittrack.db"

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

VIDEO_PREFIXES = ("https://www.youtube.com/", "https://youtu.be/", "/static/videos/")


# ---------- database ----------
def connect_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


SEED_EXERCISES = [
    ("Barbell Squat", "Legs", "Quadriceps, Glutes", 6.0, "Bar on upper back, feet shoulder-width.\nBrace core, sit hips back and down.\nLower until thighs are parallel.\nDrive through heels to stand.", "Keep knees in line with toes."),
    ("Push-Up", "Chest", "Chest, Triceps", 7.0, "Hands slightly wider than shoulders.\nBody in a straight line.\nLower chest to just above the floor.\nPush back up.", "Do not let hips sag."),
    ("Deadlift", "Back", "Hamstrings, Back", 6.5, "Bar over mid-foot, hands just outside legs.\nFlat back, chest up.\nPush the floor away and stand tall.\nLower the bar with control.", "Keep the bar close to your legs."),
    ("Bench Press", "Chest", "Chest, Triceps", 5.0, "Lie flat, eyes under the bar.\nLower the bar to mid-chest.\nPress up until arms are straight.", "Keep feet planted and shoulder blades pinched."),
    ("Pull-Up", "Back", "Lats, Biceps", 8.0, "Hang with palms facing away.\nPull chest toward the bar.\nLower slowly to a full hang.", "Avoid swinging."),
    ("Plank", "Core", "Abs, Core", 4.0, "Forearms on the floor, elbows under shoulders.\nBody in a straight line.\nHold the position.", "Squeeze glutes and abs."),
    ("Lunges", "Legs", "Quadriceps, Glutes", 5.5, "Step forward with one leg.\nLower back knee toward the floor.\nPush back to the start and switch legs.", "Keep your torso upright."),
    ("Shoulder Press", "Shoulders", "Deltoids, Triceps", 5.0, "Hold weights at shoulder height.\nPress overhead until arms are straight.\nLower with control.", "Do not arch your lower back."),
    ("Bicep Curl", "Arms", "Biceps", 4.0, "Stand tall, weights at your sides.\nCurl up, keeping elbows still.\nLower slowly.", "Do not swing your body."),
    ("Burpees", "Cardio", "Full body", 10.0, "Squat and place hands on the floor.\nJump feet back into a plank.\nDo a push-up, jump feet in, then jump up.", "Move at a steady pace."),
    ("Running", "Cardio", "Legs, Heart", 9.0, "Warm up with a brisk walk.\nRun at a pace you can talk at.\nCool down and stretch.", "Wear proper shoes."),
    ("Jump Rope", "Cardio", "Calves, Heart", 11.0, "Elbows close to your body.\nTurn the rope with your wrists.\nJump low, land softly.", "Stay on the balls of your feet."),
    ("Bent-Over Row", "Back", "Lats, Rhomboids", 5.5, "Hinge at hips with a flat back.\nPull the weight toward your belly.\nLower with control.", "Keep your neck neutral."),
    ("Mountain Climbers", "Core", "Abs, Shoulders", 9.0, "Start in a high plank.\nDrive knees toward your chest alternately.\nKeep hips low.", "Keep hands under shoulders."),
    ("Crunches", "Core", "Abs", 4.0, "Lie on your back, knees bent.\nCurl shoulders off the floor.\nLower slowly.", "Do not pull on your neck."),
]
SEED_PLANS = [
    ("Beginner Full Body", "Three easy days for people new to training.", [
        (1, "Barbell Squat", 3, 10), (1, "Push-Up", 3, 10), (1, "Plank", 3, 30),
        (2, "Lunges", 3, 12), (2, "Shoulder Press", 3, 10), (2, "Bicep Curl", 3, 12),
        (3, "Deadlift", 3, 8), (3, "Bent-Over Row", 3, 10), (3, "Crunches", 3, 15)]),
    ("Fat Loss Circuit", "High-energy cardio and core work.", [
        (1, "Burpees", 4, 12), (1, "Mountain Climbers", 4, 30), (1, "Jump Rope", 4, 60),
        (2, "Running", 1, 30), (2, "Plank", 3, 45), (2, "Crunches", 3, 20)]),
]


def setup_database():
    with connect_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
                height_cm REAL, created_at TEXT NOT NULL,
                plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL);
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL, muscle TEXT NOT NULL DEFAULT '',
                calories_per_min REAL NOT NULL DEFAULT 5, steps TEXT NOT NULL DEFAULT '',
                tips TEXT NOT NULL DEFAULT '', video_url TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                sets INTEGER NOT NULL DEFAULT 1, reps INTEGER NOT NULL DEFAULT 1,
                weight REAL NOT NULL DEFAULT 0, duration INTEGER NOT NULL DEFAULT 0,
                workout_date TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS plan_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                day INTEGER NOT NULL, sets INTEGER NOT NULL, reps INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                weight_kg REAL NOT NULL, body_fat REAL, waist_cm REAL, measured_on TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL, target_weight REAL, deadline TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Achieved')));
            CREATE TABLE IF NOT EXISTS trainer_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                note TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        # upgrade databases created by the first version of FitTrack
        cols = {r[1] for r in db.execute("PRAGMA table_info(users)")}
        if "plan_id" not in cols:
            db.execute("ALTER TABLE users ADD COLUMN plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL")
        if db.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO exercises (name, category, muscle, calories_per_min, steps, tips) VALUES (?,?,?,?,?,?)",
                SEED_EXERCISES)
            for name, desc, items in SEED_PLANS:
                plan_id = db.execute("INSERT INTO plans (name, description) VALUES (?,?)", (name, desc)).lastrowid
                for day, ex_name, sets, reps in items:
                    ex_id = db.execute("SELECT id FROM exercises WHERE name=?", (ex_name,)).fetchone()[0]
                    db.execute("INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps) VALUES (?,?,?,?,?)",
                               (plan_id, ex_id, day, sets, reps))
        if db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0:
            db.execute("INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                       ("Trainer Admin", "admin@fittrack.com", generate_password_hash("Admin@123"),
                        "admin", date.today().isoformat()))


# ---------- helpers ----------
def error(message, status=400):
    return jsonify({"error": message}), status


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return error("Please log in.", 401)
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return error("Please log in.", 401)
        if session.get("role") != "admin":
            return error("Trainer/admin access only.", 403)
        return view(*args, **kwargs)
    return wrapper


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


# ---------- pages ----------
@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# ---------- authentication ----------
@app.post("/api/auth/register")
def register():
    d = request.get_json(silent=True) or {}
    name, email, password = str(d.get("name", "")).strip(), str(d.get("email", "")).strip().lower(), str(d.get("password", ""))
    height = to_float(d.get("height_cm"))
    if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return error("Enter your name and a valid email.")
    if len(password) < 6:
        return error("Password must be at least 6 characters.")
    try:
        with connect_db() as db:
            uid = db.execute(
                "INSERT INTO users (name, email, password_hash, height_cm, created_at) VALUES (?,?,?,?,?)",
                (name, email, generate_password_hash(password), height, date.today().isoformat())).lastrowid
    except sqlite3.IntegrityError:
        return error("That email is already registered.", 409)
    session.update(user_id=uid, role="user")
    return jsonify({"id": uid, "name": name, "role": "user", "height_cm": height}), 201


@app.post("/api/auth/login")
def login():
    d = request.get_json(silent=True) or {}
    with connect_db() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (str(d.get("email", "")).strip().lower(),)).fetchone()
    if not user or not check_password_hash(user["password_hash"], str(d.get("password", ""))):
        return error("Wrong email or password.", 401)
    session.update(user_id=user["id"], role=user["role"])
    return jsonify({"id": user["id"], "name": user["name"], "role": user["role"], "height_cm": user["height_cm"]})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@app.get("/api/auth/me")
def me():
    if "user_id" not in session:
        return error("Not logged in.", 401)
    with connect_db() as db:
        user = db.execute("SELECT id, name, role, height_cm FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user:
        session.clear()
        return error("Not logged in.", 401)
    return jsonify(dict(user))


# ---------- exercises ----------
def exercise_fields(d):
    name = str(d.get("name", "")).strip()
    category = str(d.get("category", "")).strip()
    cal = to_float(d.get("calories_per_min"), 5)
    video = str(d.get("video_url", "")).strip()
    if not name or not category:
        return None, "Enter an exercise name and category."
    if cal is None or cal <= 0:
        return None, "Calories per minute must be a positive number."
    if video and not video.startswith(VIDEO_PREFIXES):
        return None, "Video must be a YouTube link or a file in /static/videos/."
    return (name, category, str(d.get("muscle", "")).strip(), cal,
            str(d.get("steps", "")).strip(), str(d.get("tips", "")).strip(), video), None


@app.get("/api/exercises")
@login_required
def list_exercises():
    q, cat = request.args.get("q", "").strip(), request.args.get("category", "").strip()
    sql, args = "SELECT * FROM exercises WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR muscle LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if cat:
        sql += " AND category=?"
        args.append(cat)
    with connect_db() as db:
        return jsonify(rows(db.execute(sql + " ORDER BY name", args)))


@app.post("/api/exercises")
@admin_required
def create_exercise():
    fields, msg = exercise_fields(request.get_json(silent=True) or {})
    if msg:
        return error(msg)
    try:
        with connect_db() as db:
            eid = db.execute("INSERT INTO exercises (name, category, muscle, calories_per_min, steps, tips, video_url) "
                             "VALUES (?,?,?,?,?,?,?)", fields).lastrowid
            return jsonify(dict(db.execute("SELECT * FROM exercises WHERE id=?", (eid,)).fetchone())), 201
    except sqlite3.IntegrityError:
        return error("An exercise with that name already exists.", 409)


@app.put("/api/exercises/<int:eid>")
@admin_required
def update_exercise(eid):
    fields, msg = exercise_fields(request.get_json(silent=True) or {})
    if msg:
        return error(msg)
    with connect_db() as db:
        cur = db.execute("UPDATE exercises SET name=?, category=?, muscle=?, calories_per_min=?, steps=?, tips=?, "
                         "video_url=? WHERE id=?", (*fields, eid))
        if cur.rowcount == 0:
            return error("Exercise not found.", 404)
        return jsonify(dict(db.execute("SELECT * FROM exercises WHERE id=?", (eid,)).fetchone()))


@app.delete("/api/exercises/<int:eid>")
@admin_required
def delete_exercise(eid):
    with connect_db() as db:
        cur = db.execute("DELETE FROM exercises WHERE id=?", (eid,))
    return jsonify({"message": "Deleted."}) if cur.rowcount else error("Exercise not found.", 404)


# ---------- workouts ----------
WORKOUT_SQL = """SELECT w.*, e.name AS exercise_name, e.category,
                 ROUND(w.duration * e.calories_per_min) AS calories
                 FROM workouts w JOIN exercises e ON e.id = w.exercise_id WHERE w.user_id=?"""


def workout_fields(d):
    try:
        ex_id, sets, reps, duration = int(d.get("exercise_id")), int(d.get("sets", 1)), int(d.get("reps", 1)), int(d.get("duration", 0))
    except (TypeError, ValueError):
        return None, "Sets, reps, duration and exercise must be numbers."
    weight = to_float(d.get("weight", 0), 0)
    day = str(d.get("workout_date") or date.today().isoformat())
    if min(sets, reps, duration) < 0 or sets > 100 or reps > 1000 or weight < 0 or duration > 600:
        return None, "Enter realistic positive values."
    if not valid_date(day):
        return None, "Enter a valid date."
    return (ex_id, sets, reps, weight, duration, day), None


@app.get("/api/workouts")
@login_required
def list_workouts():
    sql, args = WORKOUT_SQL, [session["user_id"]]
    if request.args.get("date"):
        sql += " AND w.workout_date=?"
        args.append(request.args["date"])
    if request.args.get("exercise_id", "").isdigit():
        sql += " AND w.exercise_id=?"
        args.append(int(request.args["exercise_id"]))
    with connect_db() as db:
        return jsonify(rows(db.execute(sql + " ORDER BY w.workout_date DESC, w.id DESC LIMIT 200", args)))


@app.post("/api/workouts")
@login_required
def create_workout():
    fields, msg = workout_fields(request.get_json(silent=True) or {})
    if msg:
        return error(msg)
    with connect_db() as db:
        if not db.execute("SELECT 1 FROM exercises WHERE id=?", (fields[0],)).fetchone():
            return error("Exercise not found.", 404)
        wid = db.execute("INSERT INTO workouts (user_id, exercise_id, sets, reps, weight, duration, workout_date) "
                         "VALUES (?,?,?,?,?,?,?)", (session["user_id"], *fields)).lastrowid
        return jsonify(dict(db.execute(WORKOUT_SQL + " AND w.id=?", (session["user_id"], wid)).fetchone())), 201


@app.put("/api/workouts/<int:wid>")
@login_required
def update_workout(wid):
    fields, msg = workout_fields(request.get_json(silent=True) or {})
    if msg:
        return error(msg)
    with connect_db() as db:
        cur = db.execute("UPDATE workouts SET exercise_id=?, sets=?, reps=?, weight=?, duration=?, workout_date=? "
                         "WHERE id=? AND user_id=?", (*fields, wid, session["user_id"]))
        if cur.rowcount == 0:
            return error("Workout not found.", 404)
        return jsonify(dict(db.execute(WORKOUT_SQL + " AND w.id=?", (session["user_id"], wid)).fetchone()))


@app.delete("/api/workouts/<int:wid>")
@login_required
def delete_workout(wid):
    with connect_db() as db:
        cur = db.execute("DELETE FROM workouts WHERE id=? AND user_id=?", (wid, session["user_id"]))
    return jsonify({"message": "Deleted."}) if cur.rowcount else error("Workout not found.", 404)


@app.get("/api/workouts/export")
@login_required
def export_workouts():
    with connect_db() as db:
        data = db.execute(WORKOUT_SQL + " ORDER BY w.workout_date", (session["user_id"],)).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Exercise", "Sets", "Reps", "Weight (kg)", "Duration (min)", "Calories"])
    for r in data:
        writer.writerow([r["workout_date"], r["exercise_name"], r["sets"], r["reps"], r["weight"], r["duration"], r["calories"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=workouts.csv"})


# ---------- plans (trainer feature) ----------
@app.get("/api/plans")
@login_required
def list_plans():
    with connect_db() as db:
        plans = rows(db.execute("SELECT * FROM plans ORDER BY id"))
        for p in plans:
            p["items"] = rows(db.execute(
                "SELECT pe.day, pe.sets, pe.reps, e.id AS exercise_id, e.name, e.video_url FROM plan_exercises pe "
                "JOIN exercises e ON e.id = pe.exercise_id WHERE pe.plan_id=? ORDER BY pe.day, pe.id", (p["id"],)))
    return jsonify(plans)


@app.post("/api/plans")
@admin_required
def create_plan():
    d = request.get_json(silent=True) or {}
    name, items = str(d.get("name", "")).strip(), d.get("items") or []
    if not name or not items:
        return error("Enter a plan name and at least one exercise.")
    try:
        with connect_db() as db:
            pid = db.execute("INSERT INTO plans (name, description) VALUES (?,?)",
                             (name, str(d.get("description", "")).strip())).lastrowid
            for it in items:
                db.execute("INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps) VALUES (?,?,?,?,?)",
                           (pid, int(it["exercise_id"]), int(it["day"]), int(it["sets"]), int(it["reps"])))
    except sqlite3.IntegrityError:
        return error("Plan name already exists or an exercise is invalid.", 409)
    except (KeyError, TypeError, ValueError):
        return error("Each item needs exercise_id, day, sets and reps.")
    return jsonify({"id": pid}), 201


@app.delete("/api/plans/<int:pid>")
@admin_required
def delete_plan(pid):
    with connect_db() as db:
        cur = db.execute("DELETE FROM plans WHERE id=?", (pid,))
    return jsonify({"message": "Deleted."}) if cur.rowcount else error("Plan not found.", 404)


# ---------- measurements ----------
@app.get("/api/measurements")
@login_required
def list_measurements():
    with connect_db() as db:
        return jsonify(rows(db.execute("SELECT * FROM measurements WHERE user_id=? ORDER BY measured_on DESC, id DESC",
                                       (session["user_id"],))))


@app.post("/api/measurements")
@login_required
def add_measurement():
    d = request.get_json(silent=True) or {}
    weight, fat, waist = to_float(d.get("weight_kg")), to_float(d.get("body_fat")), to_float(d.get("waist_cm"))
    day = str(d.get("measured_on") or date.today().isoformat())
    if weight is None or not 20 <= weight <= 400:
        return error("Enter a realistic weight in kg.")
    if not valid_date(day):
        return error("Enter a valid date.")
    with connect_db() as db:
        mid = db.execute("INSERT INTO measurements (user_id, weight_kg, body_fat, waist_cm, measured_on) VALUES (?,?,?,?,?)",
                         (session["user_id"], weight, fat, waist, day)).lastrowid
        return jsonify(dict(db.execute("SELECT * FROM measurements WHERE id=?", (mid,)).fetchone())), 201


@app.delete("/api/measurements/<int:mid>")
@login_required
def delete_measurement(mid):
    with connect_db() as db:
        cur = db.execute("DELETE FROM measurements WHERE id=? AND user_id=?", (mid, session["user_id"]))
    return jsonify({"message": "Deleted."}) if cur.rowcount else error("Not found.", 404)


# ---------- goals ----------
def goals_for(db, uid):
    goals = rows(db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)))
    start = db.execute("SELECT weight_kg FROM measurements WHERE user_id=? ORDER BY measured_on, id LIMIT 1", (uid,)).fetchone()
    now = db.execute("SELECT weight_kg FROM measurements WHERE user_id=? ORDER BY measured_on DESC, id DESC LIMIT 1", (uid,)).fetchone()
    for g in goals:  # progress = how far current weight moved from first weight toward the target
        g["progress"] = None
        if start and now and g["target_weight"] is not None and start[0] != g["target_weight"]:
            g["progress"] = max(0, min(100, round((start[0] - now[0]) * 100 / (start[0] - g["target_weight"]))))
    return goals


@app.get("/api/goals")
@login_required
def list_goals():
    with connect_db() as db:
        return jsonify(goals_for(db, session["user_id"]))


@app.post("/api/goals")
@login_required
def add_goal():
    d = request.get_json(silent=True) or {}
    title, deadline = str(d.get("title", "")).strip(), str(d.get("deadline", "")).strip()
    if not title:
        return error("Enter a goal title.")
    if deadline and not valid_date(deadline):
        return error("Enter a valid deadline.")
    with connect_db() as db:
        gid = db.execute("INSERT INTO goals (user_id, title, target_weight, deadline) VALUES (?,?,?,?)",
                         (session["user_id"], title, to_float(d.get("target_weight")), deadline)).lastrowid
    return jsonify({"id": gid}), 201


@app.put("/api/goals/<int:gid>")
@login_required
def toggle_goal(gid):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("Active", "Achieved"):
        return error("Invalid status.")
    with connect_db() as db:
        cur = db.execute("UPDATE goals SET status=? WHERE id=? AND user_id=?", (status, gid, session["user_id"]))
    return jsonify({"message": "Updated."}) if cur.rowcount else error("Goal not found.", 404)


@app.delete("/api/goals/<int:gid>")
@login_required
def delete_goal(gid):
    with connect_db() as db:
        cur = db.execute("DELETE FROM goals WHERE id=? AND user_id=?", (gid, session["user_id"]))
    return jsonify({"message": "Deleted."}) if cur.rowcount else error("Goal not found.", 404)


# ---------- dashboard ----------
@app.get("/api/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with connect_db() as db:
        user = db.execute("SELECT height_cm FROM users WHERE id=?", (uid,)).fetchone()
        totals = db.execute("SELECT COUNT(*) n, COALESCE(SUM(duration*e.calories_per_min),0) cal FROM workouts w "
                            "JOIN exercises e ON e.id=w.exercise_id WHERE w.user_id=?", (uid,)).fetchone()
        weekly = rows(db.execute("SELECT strftime('%Y-W%W', workout_date) wk, COUNT(*) n FROM workouts WHERE user_id=? "
                                 "GROUP BY wk ORDER BY wk DESC LIMIT 8", (uid,)))[::-1]
        volume = rows(db.execute("SELECT workout_date d, SUM(sets*reps*weight) v FROM workouts WHERE user_id=? "
                                 "GROUP BY d ORDER BY d DESC LIMIT 10", (uid,)))[::-1]
        weights = rows(db.execute("SELECT measured_on d, weight_kg w FROM measurements WHERE user_id=? "
                                  "ORDER BY measured_on DESC, id DESC LIMIT 10", (uid,)))[::-1]
        records = rows(db.execute("SELECT e.name, MAX(w.weight) best FROM workouts w JOIN exercises e ON e.id=w.exercise_id "
                                  "WHERE w.user_id=? AND w.weight>0 GROUP BY e.id ORDER BY best DESC LIMIT 5", (uid,)))
        days = {r[0] for r in db.execute("SELECT DISTINCT workout_date FROM workouts WHERE user_id=?", (uid,))}
    streak, cursor = 0, date.today()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)  # a streak is still alive if you trained yesterday
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    bmi = None
    if weights and user["height_cm"]:
        bmi = round(weights[-1]["w"] / ((user["height_cm"] / 100) ** 2), 1)
    return jsonify({"workouts": totals["n"], "calories": round(totals["cal"]), "streak": streak, "bmi": bmi,
                    "weekly": weekly, "volume": volume, "weights": weights, "records": records})


# ---------- what a client sees from the trainer ----------
@app.get("/api/my/coach")
@login_required
def my_coach():
    with connect_db() as db:
        plan = db.execute("SELECT p.id, p.name, p.description FROM users u JOIN plans p ON p.id=u.plan_id WHERE u.id=?",
                          (session["user_id"],)).fetchone()
        notes = rows(db.execute("SELECT note, created_at FROM trainer_notes WHERE user_id=? ORDER BY id DESC LIMIT 3",
                                (session["user_id"],)))
    return jsonify({"plan": dict(plan) if plan else None, "notes": notes})


# ---------- trainer (admin) area: list of clients and their progress ----------
@app.get("/api/trainer/clients")
@admin_required
def trainer_clients():
    week_ago = (date.today() - timedelta(days=6)).isoformat()
    with connect_db() as db:
        clients = rows(db.execute("""
            SELECT u.id, u.name, u.email, u.created_at, p.name AS plan_name,
              (SELECT COUNT(*) FROM workouts w WHERE w.user_id=u.id) AS workouts,
              (SELECT MAX(workout_date) FROM workouts w WHERE w.user_id=u.id) AS last_workout,
              (SELECT COUNT(*) FROM workouts w WHERE w.user_id=u.id AND w.workout_date>=?) AS week_workouts,
              (SELECT weight_kg FROM measurements m WHERE m.user_id=u.id ORDER BY measured_on, id LIMIT 1) AS start_weight,
              (SELECT weight_kg FROM measurements m WHERE m.user_id=u.id ORDER BY measured_on DESC, id DESC LIMIT 1) AS current_weight,
              (SELECT COUNT(*) FROM goals g WHERE g.user_id=u.id AND g.status='Active') AS active_goals
            FROM users u LEFT JOIN plans p ON p.id=u.plan_id WHERE u.role='user' ORDER BY u.name""", (week_ago,)))
    active = sum(1 for c in clients if c["week_workouts"] > 0)
    return jsonify({"summary": {"clients": len(clients), "active_this_week": active,
                                "inactive": len(clients) - active, "total_workouts": sum(c["workouts"] for c in clients)},
                    "clients": clients})


def get_client(db, cid):
    return db.execute("SELECT id, name, email, height_cm, plan_id, created_at FROM users "
                      "WHERE id=? AND role='user'", (cid,)).fetchone()


@app.get("/api/trainer/clients/<int:cid>")
@admin_required
def trainer_client_detail(cid):
    with connect_db() as db:
        user = get_client(db, cid)
        if not user:
            return error("Client not found.", 404)
        data = dict(user)
        data["workouts"] = rows(db.execute(WORKOUT_SQL + " ORDER BY w.workout_date DESC, w.id DESC LIMIT 15", (cid,)))
        data["weekly"] = rows(db.execute("SELECT strftime('%Y-W%W', workout_date) wk, COUNT(*) n FROM workouts WHERE user_id=? "
                                         "GROUP BY wk ORDER BY wk DESC LIMIT 8", (cid,)))[::-1]
        data["measurements"] = rows(db.execute("SELECT * FROM measurements WHERE user_id=? ORDER BY measured_on, id", (cid,)))
        data["goals"] = goals_for(db, cid)
        data["notes"] = rows(db.execute("SELECT id, note, created_at FROM trainer_notes WHERE user_id=? ORDER BY id DESC LIMIT 10", (cid,)))
    return jsonify(data)


@app.post("/api/trainer/clients/<int:cid>/notes")
@admin_required
def trainer_add_note(cid):
    note = str((request.get_json(silent=True) or {}).get("note", "")).strip()
    if not note or len(note) > 500:
        return error("Write a note of up to 500 characters.")
    with connect_db() as db:
        if not get_client(db, cid):
            return error("Client not found.", 404)
        db.execute("INSERT INTO trainer_notes (user_id, note, created_at) VALUES (?,?,?)", (cid, note, date.today().isoformat()))
    return jsonify({"message": "Note sent."}), 201


@app.put("/api/trainer/clients/<int:cid>/plan")
@admin_required
def trainer_assign_plan(cid):
    plan_id = (request.get_json(silent=True) or {}).get("plan_id")
    with connect_db() as db:
        if not get_client(db, cid):
            return error("Client not found.", 404)
        if plan_id and not db.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone():
            return error("Plan not found.", 404)
        db.execute("UPDATE users SET plan_id=? WHERE id=?", (plan_id or None, cid))
    return jsonify({"message": "Plan assigned."})


def apply_video_links():
    """Read video_links.txt ('Exercise name | YouTube URL') and fill exercises that have no video yet."""
    path = BASE_DIR / "video_links.txt"
    if not path.exists():
        return
    with connect_db() as db:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#") or "|" not in line:
                continue
            name, url = (part.strip() for part in line.split("|", 1))
            if url.startswith(VIDEO_PREFIXES):
                db.execute("UPDATE exercises SET video_url=? WHERE name=? AND video_url=''", (url, name))


setup_database()
apply_video_links()

if __name__ == "__main__":
    app.run(debug=True)
