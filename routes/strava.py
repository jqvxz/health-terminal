"""
HealthTerminal V1 — Strava Routes
OAuth authentication and activity sync with Strava API via stravalib.
"""

import re
from flask import Blueprint, redirect, request, session, jsonify, url_for
from stravalib.client import Client
from config import Config
from models.db import (
    get_db, get_setting, set_setting, get_activities,
    get_activity_by_id, get_lifting_details
)
from services.strava_parser import is_hevy_activity, parse_hevy_description
from services.muscle_map import get_muscle_info
from services.nutrition import (
    estimate_calories_running, estimate_calories_lifting,
    estimate_calories_general, get_macro_recommendations
)
import time

strava_bp = Blueprint("strava", __name__)


def _get_client():
    """Create a stravalib Client with current access token."""
    client = Client()
    token = get_setting("strava_access_token")
    if token:
        expires = int(get_setting("strava_token_expires", "0"))
        if time.time() > expires:
            token = _refresh_token(client)
        client.access_token = token
    return client


def _refresh_token(client):
    """Refresh the Strava access token."""
    refresh = get_setting("strava_refresh_token")
    if not refresh:
        return None
    try:
        resp = client.refresh_access_token(
            client_id=Config.STRAVA_CLIENT_ID,
            client_secret=Config.STRAVA_CLIENT_SECRET,
            refresh_token=refresh,
        )
        set_setting("strava_access_token", resp["access_token"])
        set_setting("strava_refresh_token", resp["refresh_token"])
        set_setting("strava_token_expires", str(resp["expires_at"]))
        return resp["access_token"]
    except Exception as e:
        print(f"Token refresh failed: {e}")
        return None


@strava_bp.route("/auth/strava")
def auth_strava():
    """Initiate Strava OAuth2 flow."""
    client = Client()
    auth_url = client.authorization_url(
        client_id=Config.STRAVA_CLIENT_ID,
        redirect_uri=Config.STRAVA_REDIRECT_URI,
        scope=["read_all", "activity:read_all", "profile:read_all"],
    )
    return redirect(auth_url)


@strava_bp.route("/auth/strava/callback")
def strava_callback():
    """Handle Strava OAuth2 callback."""
    code = request.args.get("code")
    if not code:
        return redirect("/?error=no_code")

    try:
        client = Client()
        resp = client.exchange_code_for_token(
            client_id=Config.STRAVA_CLIENT_ID,
            client_secret=Config.STRAVA_CLIENT_SECRET,
            code=code,
        )
        set_setting("strava_access_token", resp["access_token"])
        set_setting("strava_refresh_token", resp["refresh_token"])
        set_setting("strava_token_expires", str(resp["expires_at"]))
        set_setting("strava_connected", "1")

        # Get athlete info
        client.access_token = resp["access_token"]
        athlete = client.get_athlete()
        set_setting("strava_athlete_id", str(athlete.id))
        set_setting("strava_athlete_name", f"{athlete.firstname} {athlete.lastname}")

        return redirect("/?success=connected")
    except Exception as e:
        print(f"OAuth error: {e}")
        return redirect(f"/?error=oauth_failed")


@strava_bp.route("/auth/strava/disconnect")
def disconnect_strava():
    """Disconnect Strava account."""
    set_setting("strava_connected", "0")
    set_setting("strava_access_token", "")
    set_setting("strava_refresh_token", "")
    set_setting("strava_token_expires", "0")
    return redirect("/?success=disconnected")


@strava_bp.route("/api/sync")
def sync_activities():
    """Fetch new activities from Strava and store in database."""
    if get_setting("strava_connected") != "1":
        return jsonify({"error": "Strava not connected"}), 401

    client = _get_client()
    if not client.access_token:
        return jsonify({"error": "Invalid token"}), 401

    try:
        # Fetch summary activities first
        activities = client.get_activities(limit=200)
        synced = 0
        errors = 0

        try:
            athlete = client.get_athlete()
            athlete_weight = float(getattr(athlete, 'weight', 75.0) or 75.0)
        except Exception:
            athlete_weight = 75.0

        with get_db() as conn:
            for act in activities:
                strava_id = str(act.id)
                existing = conn.execute(
                    "SELECT id FROM activities WHERE strava_id = ?", (strava_id,)
                ).fetchone()
                if existing:
                    continue

                # Fetch detailed activity for description, splits, etc.
                try:
                    detailed = client.get_activity(act.id)
                except Exception as e:
                    print(f"Failed to fetch detail for {act.id}: {e}")
                    detailed = None
                    errors += 1

                # Use detailed activity as primary source (has all fields),
                # fall back to summary for basic fields
                src = detailed if detailed else act
                description = getattr(src, 'description', '') or ''

                # stravalib enums str() to "root='Run'" — extract clean value
                def _clean_type(val):
                    s = str(val) if val else ''
                    m = re.search(r"root='(\w+)'", s)
                    return m.group(1) if m else s

                act_type = _clean_type(getattr(act, 'type', ''))
                sport_type = _clean_type(getattr(act, 'sport_type', ''))

                # Build activity dict for hevy check
                act_dict = {
                    "name": getattr(act, 'name', '') or '',
                    "description": description,
                    "type": act_type,
                    "sport_type": sport_type,
                    "external_id": str(getattr(act, 'external_id', '') or ''),
                }
                hevy = is_hevy_activity(act_dict)

                # Safe numeric extraction — getattr with 0 default
                def _float(obj, attr):
                    v = getattr(obj, attr, None)
                    try:
                        return float(v) if v else 0.0
                    except (TypeError, ValueError):
                        return 0.0

                # Safe duration extraction — handles stravalib Duration type
                def _secs(obj, attr):
                    dur = getattr(obj, attr, None)
                    if not dur:
                        return 0
                    if hasattr(dur, 'total_seconds'):
                        return int(dur.total_seconds())
                    if hasattr(dur, 'seconds'):
                        return int(dur.seconds)
                    try:
                        return int(dur)
                    except (TypeError, ValueError):
                        return 0

                # Safe date extraction
                def _iso(obj, attr):
                    v = getattr(obj, attr, None)
                    return v.isoformat() if v else ''

                # Calorie estimation for lifting if missing from Strava
                calories = _float(src, 'calories')
                moving_time_secs = _secs(act, 'moving_time')
                if calories == 0 and (hevy or act_type in ('WeightTraining', 'Workout')):
                    # Calories = MET * m * (t / 60)  (where t is minutes)
                    # Using typical vigorous lifting MET = 6.0
                    met_value = 6.0
                    t_minutes = moving_time_secs / 60.0
                    if t_minutes == 0:
                        t_minutes = 10.0 # Estimate 10min if no moving time provided
                    calories = met_value * athlete_weight * (t_minutes / 60.0)

                conn.execute(
                    """INSERT INTO activities (
                        strava_id, name, activity_type, sport_type,
                        start_date, start_date_local, elapsed_time, moving_time,
                        distance, average_speed, max_speed,
                        average_heartrate, max_heartrate, total_elevation_gain,
                        calories, suffer_score, average_cadence, average_watts,
                        description, source, is_hevy, map_polyline
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        strava_id,
                        getattr(act, 'name', '') or '',
                        act_type,
                        sport_type,
                        _iso(act, 'start_date'),
                        _iso(act, 'start_date_local'),
                        _secs(act, 'elapsed_time'),
                        moving_time_secs,
                        _float(act, 'distance'),
                        _float(act, 'average_speed'),
                        _float(act, 'max_speed'),
                        _float(src, 'average_heartrate'),
                        _float(src, 'max_heartrate'),
                        _float(act, 'total_elevation_gain'),
                        calories,
                        _float(src, 'suffer_score'),
                        _float(src, 'average_cadence'),
                        _float(src, 'average_watts'),
                        description,
                        "hevy" if hevy else "strava",
                        1 if hevy else 0,
                        # Extract polyline from map object
                        getattr(getattr(src, 'map', None), 'summary_polyline', '') or '',
                    ),
                )

                # Parse lifting data if Hevy activity
                if hevy and description:
                    activity_id = conn.execute(
                        "SELECT id FROM activities WHERE strava_id = ?", (strava_id,)
                    ).fetchone()["id"]
                    sets = parse_hevy_description(description)
                    for s in sets:
                        conn.execute(
                            """INSERT INTO lifting_sessions (
                                activity_id, exercise_name, muscle_group,
                                secondary_muscles, set_number, reps, weight,
                                weight_unit, is_warmup
                            ) VALUES (?,?,?,?,?,?,?,?,?)""",
                            (
                                activity_id, s["exercise_name"],
                                s["muscle_group"], s.get("secondary_muscles", ""),
                                s["set_number"], s["reps"], s["weight"],
                                s.get("weight_unit", "kg"),
                                1 if s.get("is_warmup") else 0,
                            ),
                        )
                synced += 1

        # Log sync and update last sync time
        from datetime import datetime
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO sync_log (sync_type, last_sync, activities_synced) VALUES (?, ?, ?)",
                ("strava", now, synced),
            )
        set_setting("last_sync", now)

        msg = f"Synced {synced} new activities"
        if errors:
            msg += f" ({errors} detail fetches failed)"
        return jsonify({"synced": synced, "errors": errors, "message": msg})
    except Exception as e:
        print(f"Sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@strava_bp.route("/api/activities")
def api_activities():
    """Get activities with optional filters."""
    activity_type = request.args.get("type")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    activities = get_activities(activity_type, limit, offset, start_date, end_date)
    
    # Attach lifting details for volume calculations in the UI
    if activity_type == "lifting":
        for a in activities:
            if a.get("is_hevy"):
                a["lifting_details"] = get_lifting_details(a["id"])

    return jsonify(activities)


@strava_bp.route("/api/activities/<int:activity_id>")
def api_activity_detail(activity_id):
    """Get a single activity with lifting details if applicable."""
    activity = get_activity_by_id(activity_id)
    if not activity:
        return jsonify({"error": "Not found"}), 404

    if activity["is_hevy"]:
        activity["lifting_details"] = get_lifting_details(activity_id)

    return jsonify(activity)


@strava_bp.route("/api/activities/<int:activity_id>/streams")
def api_activity_streams(activity_id):
    """Fetch activity streams (HR, speed, altitude, distance) from Strava."""
    activity = get_activity_by_id(activity_id)
    if not activity:
        return jsonify({"error": "Not found"}), 404

    strava_id = activity.get("strava_id")
    if not strava_id:
        return jsonify({"error": "No Strava ID"}), 404

    client = _get_client()
    if not client:
        return jsonify({"error": "Strava not connected"}), 401

    try:
        stream_types = ["heartrate", "velocity_smooth", "altitude", "distance"]
        streams = client.get_activity_streams(
            int(strava_id),
            types=stream_types,
            resolution="medium",
        )

        result = {}
        for key in stream_types:
            if key in streams:
                result[key] = streams[key].data
            else:
                result[key] = []

        return jsonify(result)
    except Exception as e:
        print(f"Streams fetch error for {strava_id}: {e}")
        return jsonify({"error": str(e)}), 500

@strava_bp.route("/api/activities/<int:activity_id>/hr-fallback")
def api_activity_hr_fallback(activity_id):
    """
    Fetch watch heart rate data for the timeframe of a Strava activity.
    Used as a fallback when Strava did not record average_heartrate.
    Returns avg, min, max BPM from health_heart_rate table within the
    activity's [start_date, start_date + elapsed_time] window.
    """
    activity = get_activity_by_id(activity_id)
    if not activity:
        return jsonify({"error": "Not found"}), 404

    # Only return fallback if Strava HR is missing or zero
    if activity.get("average_heartrate") and activity["average_heartrate"] > 0:
        return jsonify({"fallback": False, "reason": "Strava HR already present"})

    start_date = activity.get("start_date") or activity.get("start_date_local")
    elapsed = activity.get("elapsed_time") or activity.get("moving_time") or 0

    if not start_date:
        return jsonify({"fallback": False, "reason": "No start date"})

    try:
        from datetime import datetime, timedelta
        # Parse the ISO start date — handle both with and without timezone suffix
        start_str = start_date.replace("Z", "+00:00") if start_date.endswith("Z") else start_date
        try:
            start_dt = datetime.fromisoformat(start_str)
        except ValueError:
            # Fallback: strip timezone and parse naively
            start_dt = datetime.fromisoformat(start_date[:19])

        end_dt = start_dt + timedelta(seconds=elapsed)
        # Store as ISO strings for SQLite comparison
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        with get_db() as conn:
            row = conn.execute(
                """SELECT ROUND(AVG(bpm)) as avg_bpm,
                          MIN(bpm) as min_bpm,
                          MAX(bpm) as max_bpm,
                          COUNT(*) as sample_count
                   FROM health_heart_rate
                   WHERE time >= ? AND time <= ?""",
                (start_iso, end_iso),
            ).fetchone()

            if row and row["sample_count"] > 0:
                series_rows = conn.execute(
                    "SELECT bpm FROM health_heart_rate WHERE time >= ? AND time <= ? ORDER BY time",
                    (start_iso, end_iso)
                ).fetchall()
                series_data = [r["bpm"] for r in series_rows]

                return jsonify({
                    "fallback": True,
                    "avg_bpm": int(row["avg_bpm"]),
                    "min_bpm": int(row["min_bpm"]),
                    "max_bpm": int(row["max_bpm"]),
                    "sample_count": row["sample_count"],
                    "window_start": start_iso,
                    "window_end": end_iso,
                    "series": series_data
                })
            else:
                return jsonify({"fallback": False, "reason": "No watch HR data in activity timeframe"})

    except Exception as e:
        print(f"HR fallback error for activity {activity_id}: {e}")
        return jsonify({"fallback": False, "reason": str(e)}), 500


@strava_bp.route("/api/stats/weekly")
def api_weekly_stats():
    """Get weekly stats, optionally for a past week."""
    from models.db import get_weekly_stats
    weeks_back = int(request.args.get("weeks_back", 0))
    stats = get_weekly_stats(weeks_back)
    return jsonify(stats)


@strava_bp.route("/api/stats/monthly")
def api_monthly_stats():
    """Get monthly stats."""
    from models.db import get_monthly_stats
    months_back = int(request.args.get("months_back", 0))
    stats = get_monthly_stats(months_back)
    return jsonify(stats)


@strava_bp.route("/api/stats/muscles")
def api_muscle_stats():
    """Get muscle group training frequency."""
    from models.db import get_muscle_group_stats
    days = int(request.args.get("days", 7))
    stats = get_muscle_group_stats(days)
    return jsonify(stats)


@strava_bp.route("/api/stats/overview")
def api_overview_stats():
    """Get all-time overview stats."""
    from models.db import get_overview_stats
    stats = get_overview_stats()
    return jsonify(stats)


@strava_bp.route("/api/nutrition/<int:activity_id>")
def api_nutrition(activity_id):
    """Get nutrition recommendations for a specific activity."""
    activity = get_activity_by_id(activity_id)
    if not activity:
        return jsonify({"error": "Not found"}), 404

    body_weight = float(get_setting("body_weight", "75"))
    weight_unit = get_setting("weight_unit") or "kg"
    if weight_unit == "lbs":
        body_weight_kg = body_weight * 0.45359237
    else:
        body_weight_kg = body_weight

    activity_type = activity["activity_type"]
    duration = activity["moving_time"] or 0

    if activity["is_hevy"]:
        calories = estimate_calories_lifting(duration, body_weight_kg)
    elif activity_type in ("Run", "VirtualRun", "TrailRun"):
        calories = estimate_calories_running(
            activity["distance"] or 0, duration, body_weight_kg,
            activity["average_heartrate"]
        )
    else:
        calories = estimate_calories_general(activity_type, duration, body_weight_kg)

    # If Strava provided calories, prefer those
    if activity["calories"] and activity["calories"] > 0:
        calories = activity["calories"]

    macros = get_macro_recommendations(calories, activity_type, body_weight_kg)
    return jsonify(macros)


@strava_bp.route("/api/nutrition/daily")
def api_daily_nutrition():
    """Get daily nutrition summary based on today's activities."""
    from datetime import date
    today = date.today().isoformat()

    activities = get_activities(start_date=today, limit=100)
    body_weight = float(get_setting("body_weight", "75"))
    weight_unit = get_setting("weight_unit") or "kg"
    if weight_unit == "lbs":
        body_weight_kg = body_weight * 0.45359237
    else:
        body_weight_kg = body_weight

    total_calories = 0

    for a in activities:
        if a["calories"] and a["calories"] > 0:
            total_calories += a["calories"]
        elif a["is_hevy"]:
            total_calories += estimate_calories_lifting(a["moving_time"] or 0, body_weight_kg)
        elif a["activity_type"] in ("Run", "VirtualRun", "TrailRun"):
            total_calories += estimate_calories_running(
                a["distance"] or 0, a["moving_time"] or 0, body_weight_kg
            )
        else:
            total_calories += estimate_calories_general(
                a["activity_type"], a["moving_time"] or 0, body_weight_kg
            )

    # Determine dominant activity type
    dominant = "general"
    if any(a["is_hevy"] for a in activities):
        dominant = "WeightTraining"
    elif any(a["activity_type"] in ("Run", "VirtualRun", "TrailRun") for a in activities):
        dominant = "Run"

    macros = get_macro_recommendations(total_calories, dominant, body_weight_kg)
    macros["activity_count"] = len(activities)
    return jsonify(macros)


@strava_bp.route("/api/sync/status")
def sync_status():
    """Get last sync info."""
    last_sync = get_setting("last_sync", "")
    connected = get_setting("strava_connected", "0")
    with get_db() as conn:
        row = conn.execute(
            "SELECT activities_synced, created_at FROM sync_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return jsonify({
        "connected": connected == "1",
        "last_sync": last_sync,
        "last_synced_count": row["activities_synced"] if row else 0,
    })
