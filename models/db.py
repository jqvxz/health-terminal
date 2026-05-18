"""
HealthTerminal V1 — Database Models
SQLite schema and helper functions for all data persistence.
"""

import sqlite3
import os
from contextlib import contextmanager
from config import Config


def get_db_path():
    """Return the path to the SQLite database."""
    return Config.DATABASE_PATH


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with all required tables."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY,
                strava_id TEXT UNIQUE,
                name TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                sport_type TEXT DEFAULT '',
                start_date TEXT NOT NULL,
                start_date_local TEXT NOT NULL,
                elapsed_time INTEGER DEFAULT 0,
                moving_time INTEGER DEFAULT 0,
                distance REAL DEFAULT 0,
                average_speed REAL DEFAULT 0,
                max_speed REAL DEFAULT 0,
                average_heartrate REAL DEFAULT 0,
                max_heartrate REAL DEFAULT 0,
                total_elevation_gain REAL DEFAULT 0,
                calories REAL DEFAULT 0,
                suffer_score INTEGER DEFAULT 0,
                average_cadence REAL DEFAULT 0,
                average_watts REAL DEFAULT 0,
                description TEXT DEFAULT '',
                source TEXT DEFAULT 'strava',
                is_hevy INTEGER DEFAULT 0,
                gear_id TEXT DEFAULT '',
                weather TEXT DEFAULT '',
                map_polyline TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lifting_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL,
                exercise_name TEXT NOT NULL,
                muscle_group TEXT DEFAULT '',
                secondary_muscles TEXT DEFAULT '',
                set_number INTEGER DEFAULT 1,
                reps INTEGER DEFAULT 0,
                weight REAL DEFAULT 0,
                weight_unit TEXT DEFAULT 'kg',
                is_warmup INTEGER DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                goal_type TEXT NOT NULL,
                activity_type TEXT DEFAULT '',
                metric TEXT NOT NULL,
                target_value REAL NOT NULL,
                current_value REAL DEFAULT 0,
                unit TEXT DEFAULT '',
                deadline TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usage_date TEXT NOT NULL,
                request_count INTEGER DEFAULT 0,
                UNIQUE(usage_date)
            );

            CREATE TABLE IF NOT EXISTS ai_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT UNIQUE NOT NULL,
                prompt_summary TEXT DEFAULT '',
                response TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                last_sync TEXT NOT NULL,
                activities_synced INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_message TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                action_url TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Default settings
            INSERT OR IGNORE INTO settings (key, value) VALUES ('body_weight', '75');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('weight_unit', 'kg');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('distance_unit', 'km');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'dark');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('enabled_tabs', 'dashboard,running,lifting,progress,recommendations,calendar,export,settings');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('strava_connected', '0');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('strava_access_token', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('strava_refresh_token', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('strava_token_expires', '0');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('strava_athlete_id', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('openrouter_api_key', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('last_sync', '');
        """)


def get_setting(key, default=""):
    """Get a setting value by key."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    """Set a setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, str(value)),
        )


def get_all_settings():
    """Get all settings as a dictionary."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}


def get_activities(activity_type=None, limit=50, offset=0, start_date=None, end_date=None):
    """Get activities with optional filters."""
    query = "SELECT * FROM activities WHERE 1=1"
    params = []

    if activity_type:
        if activity_type == "running":
            query += " AND activity_type IN ('Run', 'VirtualRun', 'TrailRun')"
        elif activity_type == "lifting":
            query += " AND is_hevy = 1"
        else:
            query += " AND activity_type = ?"
            params.append(activity_type)

    if start_date:
        query += " AND start_date_local >= ?"
        params.append(start_date)

    if end_date:
        query += " AND start_date_local <= ?"
        params.append(end_date)

    query += " ORDER BY start_date_local DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_activity_by_id(activity_id):
    """Get a single activity by its database ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
        return dict(row) if row else None


def get_lifting_details(activity_id):
    """Get all lifting sets for an activity."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM lifting_sessions WHERE activity_id = ? ORDER BY exercise_name, set_number",
            (activity_id,),
        ).fetchall()
        
        details = [dict(row) for row in rows]
        
        # Add user body weight to bodyweight exercises
        bw_row = conn.execute("SELECT value FROM settings WHERE key = 'body_weight'").fetchone()
        try:
            bw = float(bw_row["value"]) if bw_row and bw_row["value"] else 0.0
        except ValueError:
            bw = 0.0
            
        if bw > 0:
            for d in details:
                name_lower = d["exercise_name"].lower()
                if "dip" in name_lower or "pull-up" in name_lower or "chin-up" in name_lower or "push-up" in name_lower or "muscle-up" in name_lower:
                    d["weight"] = (d["weight"] or 0) + bw
                    
        return details


def get_distinct_exercises():
    """Get distinct exercise names from lifting sessions."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT exercise_name FROM lifting_sessions ORDER BY exercise_name"
        ).fetchall()
        return [row["exercise_name"] for row in rows]


def get_goals(status=None):
    """Get all goals, optionally filtered by status, and calculate dynamic progress."""
    query = "SELECT * FROM goals"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        goals = [dict(row) for row in rows]

        for g in goals:
            t = g['goal_type']
            cat = g['activity_type']

            try:
                if cat == 'running':
                    if t == 'distance':
                        val = conn.execute("SELECT MAX(distance) FROM activities WHERE activity_type='Run'").fetchone()[0]
                        g['current_value'] = round(val / 1000, 2) if val else 0
                    elif t == 'speed':
                        val = conn.execute("SELECT MAX(max_speed) FROM activities WHERE activity_type='Run'").fetchone()[0]
                        g['current_value'] = round(val * 3.6, 2) if val else 0
                    elif t == 'duration':
                        val = conn.execute("SELECT MAX(moving_time) FROM activities WHERE activity_type='Run'").fetchone()[0]
                        g['current_value'] = round(val / 60, 1) if val else 0
                    elif str(t).startswith('pace:'):
                        dist = float(t.split(':')[1])
                        # Calculate pace (min/km). Lower is better.
                        val = conn.execute("SELECT MIN(moving_time * 1.0 / (distance/1000) / 60) FROM activities WHERE activity_type='Run' AND distance >= ?", (dist * 1000,)).fetchone()[0]
                        g['current_value'] = round(val, 2) if val else 0

                elif cat == 'lifting':
                    if str(t).startswith('pr:'):
                        ex = t.split(':', 1)[1]
                        val = conn.execute("SELECT MAX(weight) FROM lifting_sessions WHERE exercise_name = ?", (ex,)).fetchone()[0]
                        g['current_value'] = val if val else 0
                    elif t in ['weekly', 'daily', 'monthly']:
                        if t == 'daily':
                            date_mod = "date('now', 'localtime')"
                            q = f"SELECT SUM(weight * reps) FROM lifting_sessions WHERE is_warmup = 0 AND date(created_at) = {date_mod}"
                        elif t == 'weekly':
                            date_mod = "date('now', 'localtime', 'weekday 1', '-7 days')" # Monday of current week
                            q = f"SELECT SUM(weight * reps) FROM lifting_sessions WHERE is_warmup = 0 AND date(created_at) >= {date_mod}"
                        else:
                            date_mod = "date('now', 'localtime', 'start of month')"
                            q = f"SELECT SUM(weight * reps) FROM lifting_sessions WHERE is_warmup = 0 AND date(created_at) >= {date_mod}"
                        
                        val = conn.execute(q).fetchone()[0]
                        g['current_value'] = val if val else 0
            except Exception as e:
                print(f"Error calculating goal {g['id']} progress: {e}")
                pass

        return goals


def get_ai_usage_today():
    """Get the AI request count for today."""
    from datetime import date
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT request_count FROM ai_usage WHERE usage_date = ?", (today,)
        ).fetchone()
        return row["request_count"] if row else 0


def increment_ai_usage():
    """Increment the AI usage counter for today."""
    from datetime import date
    today = date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO ai_usage (usage_date, request_count) VALUES (?, 1) "
            "ON CONFLICT(usage_date) DO UPDATE SET request_count = request_count + 1",
            (today,),
        )


def get_weekly_stats(weeks_back=0):
    """Get aggregated stats for a specific week."""
    from datetime import datetime, timedelta
    now = datetime.now()
    week_start = now - timedelta(days=now.weekday() + (weeks_back * 7))
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    with get_db() as conn:
        stats = {}

        # Running stats
        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(distance), 0) as total_distance,
               COALESCE(SUM(moving_time), 0) as total_time, COALESCE(SUM(calories), 0) as total_calories,
               COALESCE(AVG(average_heartrate), 0) as avg_hr
               FROM activities
               WHERE activity_type IN ('Run', 'VirtualRun', 'TrailRun')
               AND start_date_local >= ? AND start_date_local < ?""",
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchone()
        stats["running"] = dict(row) if row else {}

        # Lifting stats
        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(moving_time), 0) as total_time,
               COALESCE(SUM(calories), 0) as total_calories
               FROM activities
               WHERE is_hevy = 1
               AND start_date_local >= ? AND start_date_local < ?""",
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchone()
        stats["lifting"] = dict(row) if row else {}

        # Total volume lifted
        row = conn.execute(
            """SELECT COALESCE(SUM(ls.weight * ls.reps), 0) as total_volume
               FROM lifting_sessions ls
               JOIN activities a ON ls.activity_id = a.id
               WHERE a.start_date_local >= ? AND a.start_date_local < ?
               AND ls.is_warmup = 0""",
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchone()
        stats["total_volume"] = row["total_volume"] if row else 0

        stats["week_start"] = week_start.strftime("%Y-%m-%d")
        stats["week_end"] = week_end.strftime("%Y-%m-%d")

        return stats


def get_monthly_stats(months_back=0):
    """Get aggregated stats for a specific month."""
    from datetime import datetime
    import calendar as cal_mod
    now = datetime.now()
    # Calculate target month
    year = now.year
    month = now.month - months_back
    while month <= 0:
        month += 12
        year -= 1

    month_start = datetime(year, month, 1)
    days_in_month = cal_mod.monthrange(year, month)[1]
    month_end = datetime(year, month, days_in_month, 23, 59, 59)

    with get_db() as conn:
        stats = {}

        # Running stats
        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(distance), 0) as total_distance,
               COALESCE(SUM(moving_time), 0) as total_time, COALESCE(SUM(calories), 0) as total_calories,
               COALESCE(AVG(CASE WHEN average_heartrate > 0 THEN average_heartrate END), 0) as avg_hr,
               COALESCE(MAX(distance), 0) as longest_run
               FROM activities
               WHERE activity_type IN ('Run', 'VirtualRun', 'TrailRun')
               AND start_date_local >= ? AND start_date_local < ?""",
            (month_start.isoformat(), month_end.isoformat()),
        ).fetchone()
        stats["running"] = dict(row) if row else {}

        # Lifting stats
        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(moving_time), 0) as total_time,
               COALESCE(SUM(calories), 0) as total_calories
               FROM activities
               WHERE is_hevy = 1
               AND start_date_local >= ? AND start_date_local < ?""",
            (month_start.isoformat(), month_end.isoformat()),
        ).fetchone()
        stats["lifting"] = dict(row) if row else {}

        # Total volume lifted
        row = conn.execute(
            """SELECT COALESCE(SUM(ls.weight * ls.reps), 0) as total_volume
               FROM lifting_sessions ls
               JOIN activities a ON ls.activity_id = a.id
               WHERE a.start_date_local >= ? AND a.start_date_local < ?
               AND ls.is_warmup = 0""",
            (month_start.isoformat(), month_end.isoformat()),
        ).fetchone()
        stats["total_volume"] = row["total_volume"] if row else 0

        # All activities count
        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(calories), 0) as total_calories
               FROM activities WHERE start_date_local >= ? AND start_date_local < ?""",
            (month_start.isoformat(), month_end.isoformat()),
        ).fetchone()
        stats["total_activities"] = row["count"] if row else 0
        stats["total_calories"] = row["total_calories"] if row else 0

        stats["month_start"] = month_start.strftime("%Y-%m-%d")
        stats["month_end"] = month_end.strftime("%Y-%m-%d")
        stats["month_name"] = month_start.strftime("%B %Y")

        return stats


def get_overview_stats():
    """Get all-time overview statistics."""
    with get_db() as conn:
        stats = {}

        row = conn.execute("SELECT COUNT(*) as total FROM activities").fetchone()
        stats["total_activities"] = row["total"] if row else 0

        row = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(distance), 0) as total_distance,
               COALESCE(SUM(calories), 0) as total_calories,
               COALESCE(MAX(distance), 0) as longest_run,
               COALESCE(MIN(CASE WHEN distance > 0 AND moving_time > 0
                   THEN moving_time * 1.0 / distance END), 0) as best_pace
               FROM activities WHERE activity_type IN ('Run', 'VirtualRun', 'TrailRun')"""
        ).fetchone()
        stats["running"] = dict(row) if row else {}

        row = conn.execute(
            "SELECT COUNT(*) as count FROM activities WHERE is_hevy = 1"
        ).fetchone()
        stats["lifting_count"] = row["count"] if row else 0

        row = conn.execute(
            """SELECT COALESCE(SUM(ls.weight * ls.reps), 0) as total_volume,
               COALESCE(MAX(ls.weight), 0) as max_weight
               FROM lifting_sessions ls WHERE ls.is_warmup = 0"""
        ).fetchone()
        stats["total_volume"] = row["total_volume"] if row else 0
        stats["max_weight"] = row["max_weight"] if row else 0

        # Top exercises by volume
        rows = conn.execute(
            """SELECT exercise_name, SUM(weight * reps) as volume, MAX(weight) as max_weight,
               COUNT(*) as total_sets
               FROM lifting_sessions WHERE is_warmup = 0
               GROUP BY exercise_name ORDER BY volume DESC LIMIT 10"""
        ).fetchall()
        stats["top_exercises"] = [dict(r) for r in rows]

        # Personal bests
        rows = conn.execute(
            """SELECT exercise_name, MAX(weight) as max_weight, muscle_group
               FROM lifting_sessions WHERE is_warmup = 0 AND weight > 0
               GROUP BY exercise_name ORDER BY max_weight DESC LIMIT 10"""
        ).fetchall()
        stats["personal_bests"] = [dict(r) for r in rows]

        return stats


def get_muscle_group_stats(days=7):
    """Get muscle group training frequency for the last N days."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """SELECT ls.muscle_group, COUNT(DISTINCT a.id) as session_count,
               SUM(ls.reps * ls.weight) as total_volume
               FROM lifting_sessions ls
               JOIN activities a ON ls.activity_id = a.id
               WHERE a.start_date_local >= ? AND ls.muscle_group != '' AND ls.is_warmup = 0
               GROUP BY ls.muscle_group
               ORDER BY total_volume DESC""",
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_exercise_progression(exercise_name, limit=20):
    """Get weight progression for a specific exercise over time."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.start_date_local, MAX(ls.weight) as max_weight,
               SUM(ls.weight * ls.reps) as session_volume,
               MAX(ls.reps) as max_reps
               FROM lifting_sessions ls
               JOIN activities a ON ls.activity_id = a.id
               WHERE LOWER(ls.exercise_name) = LOWER(?) AND ls.is_warmup = 0
               GROUP BY a.id
               ORDER BY a.start_date_local DESC LIMIT ?""",
            (exercise_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_notifications(unread_only=False, limit=20):
    """Get notifications."""
    query = "SELECT * FROM notifications"
    if unread_only:
        query += " WHERE is_read = 0"
    query += " ORDER BY created_at DESC LIMIT ?"
    with get_db() as conn:
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]


def add_notification(title, message, notif_type="info", action_url=""):
    """Add a new notification."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (title, message, type, action_url) VALUES (?, ?, ?, ?)",
            (title, message, notif_type, action_url),
        )


def mark_notification_read(notif_id):
    """Mark a notification as read."""
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))


def get_sync_history(limit=10):
    """Get sync log history."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
