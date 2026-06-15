"""
HealthTerminal V1 — Health Connect (HC Webhook) Routes
Webhook receiver for HC Webhook Android app, data APIs for Health Data tab.
"""

import json
import requests
import socket
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from models.db import get_db, get_setting, set_setting, get_all_settings

health_connect_bp = Blueprint("health_connect", __name__)


def _get_webhook_base_url():
    """Build the base URL using the machine's LAN IP so the webhook
    is reachable from the Android phone on the same network."""
    try:
        # Connect to a public DNS to determine our LAN-facing IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = request.host.split(":")[0]  # fallback

    # Preserve the port from the current request
    port = request.host.split(":")[1] if ":" in request.host else "5000"
    scheme = request.scheme
    return f"{scheme}://{lan_ip}:{port}"


def calculate_sleep_score(duration_seconds, stages):
    """
    Calculate sleep score (0-100) from duration and sleep stages.
    HC Webhook does not transmit a sleep score, so we derive one.

    Scoring breakdown:
    - Duration (40 pts): 7-9 hours is ideal
    - Deep sleep (20 pts): target ~15-25% of total
    - REM sleep (20 pts): target ~20-25% of total
    - Awake penalty (up to -20 pts): less awake time is better
    """
    hours = duration_seconds / 3600.0

    # Duration score (max 40 points)
    if 7 <= hours <= 9:
        duration_score = 40
    elif 6 <= hours < 7 or 9 < hours <= 10:
        duration_score = 30
    elif 5 <= hours < 6 or 10 < hours <= 11:
        duration_score = 20
    else:
        duration_score = max(0, 40 - abs(hours - 8) * 10)

    if not stages:
        # No stage data — score based on duration alone, scaled
        return round(min(100, max(0, duration_score * 2.5)))

    total_stage_time = 0
    deep_time = 0
    rem_time = 0
    awake_time = 0

    for s in stages:
        dur = s.get("duration_seconds", 0)
        stage_code = str(s.get("stage", ""))
        total_stage_time += dur

        # Android Health Connect numeric stage codes:
        # 1=Awake-in-bed, 2=Sleep(unspecified), 3=Out-of-bed,
        # 4=Light, 5=Deep, 6=REM
        if stage_code == "5":
            deep_time += dur
        elif stage_code == "6":
            rem_time += dur
        elif stage_code in ("1", "3"):
            awake_time += dur
        # 2 and 4 = light/unspecified — counted in total but not separately


    if total_stage_time == 0:
        return round(min(100, max(0, duration_score * 2.5)))

    deep_pct = deep_time / total_stage_time
    rem_pct = rem_time / total_stage_time
    awake_pct = awake_time / total_stage_time

    # Deep sleep score (max 20 points) — ideal ~20%
    deep_score = min(20, (deep_pct / 0.20) * 20)
    # REM score (max 20 points) — ideal ~22%
    rem_score = min(20, (rem_pct / 0.22) * 20)
    # Awake penalty (subtract up to 20 points)
    awake_penalty = min(20, awake_pct * 100)
    stage_score = deep_score + rem_score + (20 - awake_penalty)

    return round(min(100, max(0, duration_score + stage_score)))


# ─── Data Sync Endpoint ───────────────────────────────────────────

@health_connect_bp.route("/api/health-connect/sync", methods=["POST"])
def sync_health_data():
    """
    Pull health data from HC Webhook Android app's Local HTTP Server.
    """
    if get_setting("hc_webhook_enabled") != "1":
        return jsonify({"error": "HC Integration is not enabled"}), 403

    phone_ip = get_setting("hc_phone_ip")

    if not phone_ip:
        return jsonify({"error": "Phone IP address not configured"}), 400

    url = f"http://{phone_ip}:8787/?days=7"
    headers = {}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return jsonify({"error": "Connection timed out. Is the app open?"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to connect to phone: {str(e)}"}), 502

    records_saved = 0

    try:
        with get_db() as conn:
            # Clear old data to prevent duplicates since the Local HTTP server
            # returns the full 7-day window on every request
            conn.execute("DELETE FROM health_steps")
            conn.execute("DELETE FROM health_sleep")
            conn.execute("DELETE FROM health_heart_rate")
            conn.execute("DELETE FROM health_body_temp")
            conn.execute("DELETE FROM health_vo2max")
            conn.execute("DELETE FROM health_resting_heart_rate")
            conn.execute("DELETE FROM health_hrv")
            conn.execute("DELETE FROM health_oxygen_saturation")
            conn.execute("DELETE FROM health_respiratory_rate")

            # Steps
            for s in data.get("steps", []):
                conn.execute(
                    "INSERT INTO health_steps (count, start_time, end_time) VALUES (?, ?, ?)",
                    (s.get("count", 0), s.get("start_time", ""), s.get("end_time", "")),
                )
                records_saved += 1

            # Sleep
            for s in data.get("sleep", []):
                stages = s.get("stages", [])
                duration = s.get("duration_seconds", 0)
                score = calculate_sleep_score(duration, stages)
                conn.execute(
                    "INSERT INTO health_sleep (session_end_time, duration_seconds, stages, sleep_score) VALUES (?, ?, ?, ?)",
                    (s.get("session_end_time", ""), duration, json.dumps(stages), score),
                )
                records_saved += 1

            # Heart Rate
            for hr in data.get("heart_rate", []):
                conn.execute(
                    "INSERT INTO health_heart_rate (bpm, time) VALUES (?, ?)",
                    (hr.get("bpm", 0), hr.get("time", "")),
                )
                records_saved += 1

            # Body Temperature
            for bt in data.get("body_temperature", []):
                conn.execute(
                    "INSERT INTO health_body_temp (celsius, time) VALUES (?, ?)",
                    (bt.get("celsius", 0), bt.get("time", "")),
                )
                records_saved += 1

            # VO2 Max
            for v in data.get("vo2_max", []):
                conn.execute(
                    "INSERT INTO health_vo2max (ml_per_kg_per_min, time) VALUES (?, ?)",
                    (v.get("ml_per_kg_per_min", 0), v.get("time", "")),
                )
                records_saved += 1

            # Resting Heart Rate
            for rhr in data.get("resting_heart_rate", []):
                conn.execute(
                    "INSERT INTO health_resting_heart_rate (bpm, time) VALUES (?, ?)",
                    (rhr.get("bpm", 0), rhr.get("time", "")),
                )
                records_saved += 1

            # Heart Rate Variability
            for hrv in data.get("heart_rate_variability", []):
                conn.execute(
                    "INSERT INTO health_hrv (rmssd_millis, time) VALUES (?, ?)",
                    (hrv.get("rmssd_millis", 0), hrv.get("time", "")),
                )
                records_saved += 1

            # Oxygen Saturation
            for ox in data.get("oxygen_saturation", []):
                conn.execute(
                    "INSERT INTO health_oxygen_saturation (percentage, time) VALUES (?, ?)",
                    (ox.get("percentage", 0), ox.get("time", "")),
                )
                records_saved += 1

            # Respiratory Rate
            for rr in data.get("respiratory_rate", []):
                conn.execute(
                    "INSERT INTO health_respiratory_rate (rate, time) VALUES (?, ?)",
                    (rr.get("rate", 0), rr.get("time", "")),
                )
                records_saved += 1

            # Log the sync
            conn.execute(
                "INSERT INTO sync_log (sync_type, last_sync, activities_synced, status) VALUES (?, datetime('now'), ?, 'success')",
                ("hc_webhook", records_saved),
            )

        set_setting("hc_last_sync", datetime.utcnow().isoformat() + "Z")

        return jsonify({
            "message": "Health data synced successfully",
            "records_saved": records_saved,
        }), 200

    except Exception as e:
        # Log failure
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO sync_log (sync_type, last_sync, activities_synced, status, error_message) VALUES (?, datetime('now'), 0, 'error', ?)",
                    ("hc_webhook", str(e)),
                )
        except Exception:
            pass
        return jsonify({"error": f"Failed to process data: {str(e)}"}), 500


@health_connect_bp.route("/api/health-connect/status", methods=["GET"])
def hc_status():
    """Get HC Integration status."""
    enabled = get_setting("hc_webhook_enabled") == "1"
    last_sync = get_setting("hc_last_sync", "")
    phone_ip = get_setting("hc_phone_ip", "")
    local_token = get_setting("hc_local_token", "")

    return jsonify({
        "enabled": enabled,
        "hc_phone_ip": phone_ip,
        "hc_local_token": local_token,
        "last_sync": last_sync,
    })


# ─── Data API for Health Data Tab ──────────────────────────────────

def parse_iso(dt_str):
    """Parse an ISO datetime string into a datetime object."""
    if not dt_str:
        return None
    try:
        s = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


def merge_sleep_sessions(sessions):
    """
    Merge sleep sessions that belong to the same night.
    Sessions is a list of dicts:
    [{"session_end_time": ..., "duration_seconds": ..., "stages": ..., "sleep_score": ...}]
    """
    if not sessions:
        return []

    parsed = []
    for s in sessions:
        end_time_str = s["session_end_time"]
        end_dt = parse_iso(end_time_str)
        if not end_dt:
            continue
        
        stages = s.get("stages", [])
        start_dt = None
        if stages:
            for st in stages:
                st_start = parse_iso(st.get("start_time"))
                if st_start:
                    if start_dt is None or st_start < start_dt:
                        start_dt = st_start
        
        if not start_dt:
            start_dt = end_dt - timedelta(seconds=s["duration_seconds"])
            
        parsed.append({
            "start_dt": start_dt,
            "end_dt": end_dt,
            "duration_seconds": s["duration_seconds"],
            "stages": stages,
            "sleep_score": s["sleep_score"],
            "session_end_time": end_time_str
        })

    # Sort chronologically by start_dt
    parsed.sort(key=lambda x: x["start_dt"])

    merged = []
    for s in parsed:
        if not merged:
            merged.append(s)
            continue
        
        prev = merged[-1]
        gap = (s["start_dt"] - prev["end_dt"]).total_seconds()
        
        # Merge if gap is less than 4 hours (14400s) or they end on the same calendar day
        if gap <= 14400 or prev["end_dt"].date() == s["end_dt"].date():
            # Update end time to the later of the two
            prev["end_dt"] = max(prev["end_dt"], s["end_dt"])
            prev["session_end_time"] = prev["end_dt"].isoformat().replace("+00:00", "") + "Z"
            
            # Combine stages
            prev_stages = prev["stages"] or []
            s_stages = s["stages"] or []
            
            # Insert awake stage for the gap if gap is significant (> 10 seconds)
            if gap > 10:
                awake_stage = {
                    "stage": "1",  # Awake
                    "start_time": prev["end_dt"].isoformat() + "Z",
                    "end_time": s["start_dt"].isoformat() + "Z",
                    "duration_seconds": int(gap)
                }
                prev_stages.append(awake_stage)
                
            prev_stages.extend(s_stages)
            prev["stages"] = prev_stages
            
            # Combine duration (sum + gap if positive)
            prev["duration_seconds"] += s["duration_seconds"] + (int(gap) if gap > 0 else 0)
            
            # Recalculate sleep score
            prev["sleep_score"] = calculate_sleep_score(prev["duration_seconds"], prev["stages"])
        else:
            merged.append(s)

    # Sort descending by end time to return most recent first
    merged.sort(key=lambda x: x["end_dt"], reverse=True)
    
    result = []
    for m in merged:
        result.append({
            "session_end_time": m["session_end_time"],
            "duration_seconds": m["duration_seconds"],
            "duration_hours": round(m["duration_seconds"] / 3600, 1),
            "sleep_score": m["sleep_score"],
            "stages": m["stages"]
        })
    return result


@health_connect_bp.route("/api/health-connect/data", methods=["GET"])
def get_health_data():
    """
    Return aggregated health data for the Health Data tab.
    Supports ?days=N query param (default 7).
    """
    days = request.args.get("days", 7, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    result = {}
    with get_db() as conn:
        # Steps — daily aggregates (use localtime to map UTC strings to local days)
        rows = conn.execute(
            """SELECT date(start_time, 'localtime') as day, SUM(count) as total_steps
               FROM health_steps WHERE start_time >= ?
               GROUP BY date(start_time, 'localtime') ORDER BY day""",
            (cutoff,),
        ).fetchall()
        result["steps"] = [{"day": r["day"], "total_steps": r["total_steps"]} for r in rows]

        # Today's steps — use start_time with localtime only (OR was double-counting same record)
        today_local = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            """SELECT COALESCE(SUM(count), 0) as total FROM health_steps
               WHERE date(start_time, 'localtime') = ?""",
            (today_local,),
        ).fetchone()
        result["steps_today"] = row["total"] if row else 0

        # Steps goal & average
        row = conn.execute(
            "SELECT COALESCE(AVG(daily_total), 0) as avg_steps FROM (SELECT SUM(count) as daily_total FROM health_steps GROUP BY date(start_time, 'localtime'))"
        ).fetchone()
        result["steps_avg"] = round(row["avg_steps"]) if row else 0
        result["steps_goal"] = 10000  # default

        # Sleep — recent sessions (filter out naps < 1 hour)
        rows = conn.execute(
            """SELECT id, session_end_time, duration_seconds, stages, sleep_score
               FROM health_sleep WHERE session_end_time >= ? AND duration_seconds >= 3600
               ORDER BY session_end_time DESC""",
            (cutoff,),
        ).fetchall()
        sleep_data = []
        for r in rows:
            sleep_data.append({
                "session_end_time": r["session_end_time"],
                "duration_seconds": r["duration_seconds"],
                "duration_hours": round(r["duration_seconds"] / 3600, 1),
                "sleep_score": r["sleep_score"],
                "stages": json.loads(r["stages"]) if r["stages"] else [],
            })
        
        # Merge sleep sessions to resolve duplicate awake-times in same night
        sleep_data = merge_sleep_sessions(sleep_data)
        
        result["sleep"] = sleep_data
        result["sleep_score_avg"] = round(sum(s["sleep_score"] for s in sleep_data) / len(sleep_data)) if sleep_data else 0
        result["sleep_duration_avg"] = round(sum(s["duration_hours"] for s in sleep_data) / len(sleep_data), 1) if sleep_data else 0

        # Heart Rate — recent readings (last 500 for chart to show older data)
        rows = conn.execute(
            "SELECT bpm, time FROM health_heart_rate WHERE time >= ? ORDER BY time DESC LIMIT 500",
            (cutoff,),
        ).fetchall()
        result["heart_rate"] = [{"bpm": r["bpm"], "time": r["time"]} for r in reversed(list(rows))]

        # Heart Rate by day and Trends
        hr_rows = conn.execute(
            """SELECT bpm, time, date(time, 'localtime') as local_day, strftime('%H:%M', time, 'localtime') as local_time
               FROM health_heart_rate WHERE time >= ? ORDER BY time ASC""",
            (cutoff,),
        ).fetchall()
        
        rhr_rows = conn.execute(
            """SELECT bpm, date(time, 'localtime') as local_day
               FROM health_resting_heart_rate WHERE time >= ? ORDER BY time ASC""",
            (cutoff,),
        ).fetchall()
        rhr_by_day = {r["local_day"]: r["bpm"] for r in rhr_rows}
        
        hrv_rows = conn.execute(
            """SELECT rmssd_millis, date(time, 'localtime') as local_day
               FROM health_hrv WHERE time >= ? ORDER BY time ASC""",
            (cutoff,),
        ).fetchall()
        hrv_by_day = {r["local_day"]: r["rmssd_millis"] for r in hrv_rows}
        
        hr_by_day = {}
        for r in hr_rows:
            day = r["local_day"]
            if day not in hr_by_day:
                hr_by_day[day] = []
            hr_by_day[day].append({
                "bpm": r["bpm"],
                "time": r["time"],
                "local_time": r["local_time"]
            })
            
        result["heart_rate_by_day"] = hr_by_day

        unique_days = sorted(list(hr_by_day.keys()))
        hr_trends = []
        for day in unique_days:
            readings = hr_by_day[day]
            bpms = [r["bpm"] for r in readings]
            max_bpm = max(bpms) if bpms else 0
            avg_bpm = round(sum(bpms) / len(bpms)) if bpms else 0
            
            recorded_rhr = rhr_by_day.get(day)
            if recorded_rhr:
                rhr_val = recorded_rhr
            else:
                if bpms:
                    sorted_bpms = sorted(bpms)
                    rhr_val = sorted_bpms[max(0, len(sorted_bpms) // 10)]
                else:
                    rhr_val = 0
                    
            hr_trends.append({
                "day": day,
                "max_bpm": max_bpm,
                "avg_bpm": avg_bpm,
                "resting_bpm": rhr_val,
                "hrv": round(hrv_by_day.get(day), 1) if day in hrv_by_day else None
            })
        result["heart_rate_trends"] = hr_trends

        # Latest heart rate
        row = conn.execute(
            "SELECT bpm, time FROM health_heart_rate ORDER BY time DESC LIMIT 1"
        ).fetchone()
        result["heart_rate_latest"] = {"bpm": row["bpm"], "time": row["time"]} if row else None

        # Resting heart rate
        row = conn.execute(
            "SELECT bpm, time FROM health_resting_heart_rate ORDER BY time DESC LIMIT 1"
        ).fetchone()
        result["resting_hr"] = {"bpm": row["bpm"], "time": row["time"]} if row else None

        rows = conn.execute(
            "SELECT bpm, time FROM health_resting_heart_rate WHERE time >= ? ORDER BY time",
            (cutoff,),
        ).fetchall()
        result["resting_hr_history"] = [{"bpm": r["bpm"], "time": r["time"]} for r in rows]

        # Body Temperature
        row = conn.execute(
            "SELECT celsius, time FROM health_body_temp ORDER BY time DESC LIMIT 1"
        ).fetchone()
        if row:
            result["body_temp"] = {"celsius": row["celsius"], "time": row["time"]}
        else:
            # Estimate body temp: warmer in late afternoon/evening, cooler at night
            hour = datetime.now().hour
            temp_est = 36.6
            if 14 <= hour <= 20: temp_est = 36.8
            elif 2 <= hour <= 6: temp_est = 36.4
            
            # Slight elevation if user's resting HR is unusually high
            rhr_row = conn.execute("SELECT MIN(bpm) as min_bpm FROM health_resting_heart_rate").fetchone()
            rhr = rhr_row["min_bpm"] if rhr_row and rhr_row["min_bpm"] else 65
            if rhr > 75: temp_est += 0.2
            
            result["body_temp"] = {"celsius": temp_est, "time": datetime.now().isoformat() + "Z", "estimated": True}
            result["temp_deviation"] = {"celsius": round(temp_est - 36.6, 2), "estimated": True}

        rows = conn.execute(
            "SELECT celsius, time FROM health_body_temp WHERE time >= ? ORDER BY time",
            (cutoff,),
        ).fetchall()
        result["body_temp_history"] = [{"celsius": r["celsius"], "time": r["time"]} for r in rows]
        if row and rows:
            # Calculate real temp deviation if data exists
            avg_temp = sum(r["celsius"] for r in rows) / len(rows)
            result["temp_deviation"] = {"celsius": round(row["celsius"] - avg_temp, 2), "estimated": False}

        # VO2 Max — prefer actual measurement, then use run pace+HR if available
        row = conn.execute(
            "SELECT ml_per_kg_per_min, time FROM health_vo2max ORDER BY time DESC LIMIT 1"
        ).fetchone()
        if row:
            result["vo2max"] = {"value": row["ml_per_kg_per_min"], "time": row["time"]}
        else:
            age = int(get_setting("user_age", 30) or 30)
            max_hr = 220 - age
            if not rhr:
                hr_row = conn.execute("SELECT MIN(bpm) as min_bpm FROM health_heart_rate").fetchone()
                rhr = hr_row["min_bpm"] if hr_row and hr_row["min_bpm"] else 65

            # Try to estimate from running data: Jack Daniels' VDOT-derived formula
            # VO2 = avg_speed (m/min) * 0.2 + 3.5, adjusted for fractional HR reserve
            run_row = conn.execute(
                """SELECT AVG(average_speed) as avg_spd, AVG(average_heartrate) as avg_hr
                   FROM activities WHERE sport_type = 'Run'
                   AND average_speed IS NOT NULL AND average_heartrate IS NOT NULL
                   LIMIT 10"""
            ).fetchone()

            if run_row and run_row["avg_spd"] and run_row["avg_hr"]:
                # average_speed from Strava is m/s -> convert to m/min
                speed_m_min = run_row["avg_spd"] * 60
                # Simplified Daniels formula: VO2 at speed (% of VO2max based on %HRR)
                # %HRR = (HR_exercise - HR_rest) / (HR_max - HR_rest)
                hrr_pct = (run_row["avg_hr"] - rhr) / max(max_hr - rhr, 1)
                # At ~75% HRR we approximate ~85% VO2max
                pct_vo2max = max(0.5, min(1.0, hrr_pct * 1.12))
                # VO2 at running speed ≈ speed(m/min)*0.2 + 3.5 (ACSM walking/running equation)
                vo2_running = speed_m_min * 0.2 + 3.5
                est_vo2 = vo2_running / pct_vo2max
                method = f"Estimated from {run_row['avg_spd']:.2f} m/s avg run pace + HR data"
            else:
                # Fallback: Uth-Sørensen formula
                est_vo2 = 15.0 * (max_hr / rhr)
                method = "Estimated from resting heart rate (Uth-Sorensen)"

            est_vo2 = max(20.0, min(70.0, round(est_vo2, 1)))  # cap to realistic range
            result["vo2max"] = {"value": est_vo2, "time": datetime.now().isoformat() + "Z", "estimated": True, "method": method}

        rows = conn.execute(
            "SELECT ml_per_kg_per_min as value, time FROM health_vo2max WHERE time >= ? ORDER BY time",
            (cutoff,),
        ).fetchall()
        if rows:
            result["vo2max_history"] = [{"value": r["value"], "time": r["time"]} for r in rows]
        else:
            base_vo2 = result["vo2max"]["value"]
            hist = []
            for i in range(4):
                # Fake a small progression over the last 4 weeks
                val = base_vo2 - (3 - i) * 0.15
                hist.append({"value": round(val, 1), "time": ""})
            result["vo2max_history"] = hist

        # HRV
        row = conn.execute(
            "SELECT rmssd_millis, time FROM health_hrv ORDER BY time DESC LIMIT 1"
        ).fetchone()
        result["hrv"] = {"rmssd_millis": row["rmssd_millis"], "time": row["time"]} if row else None

        # Oxygen Saturation
        row = conn.execute(
            "SELECT percentage, time FROM health_oxygen_saturation ORDER BY time DESC LIMIT 1"
        ).fetchone()
        if row:
            result["oxygen_saturation"] = {"percentage": row["percentage"], "time": row["time"]}
        else:
            # Estimate SpO2: normal is 98%, if avg sleep < 6 hrs, assume 97%
            est_spo2 = 98.0
            if result.get("sleep_duration_avg", 8) < 6:
                est_spo2 = 97.0
            result["oxygen_saturation"] = {"percentage": est_spo2, "time": datetime.now().isoformat() + "Z", "estimated": True}

        # Respiratory Rate
        row = conn.execute(
            "SELECT rate, time FROM health_respiratory_rate ORDER BY time DESC LIMIT 1"
        ).fetchone()
        if row:
            result["respiratory_rate"] = {"rate": row["rate"], "time": row["time"]}
        else:
            # Estimate Respiratory Rate based on Resting HR
            est_resp = 14
            if rhr < 55: est_resp = 12
            elif rhr > 75: est_resp = 16
            result["respiratory_rate"] = {"rate": est_resp, "time": datetime.now().isoformat() + "Z", "estimated": True}

        # Has any data?
        total = conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM health_steps) +
                (SELECT COUNT(*) FROM health_sleep) +
                (SELECT COUNT(*) FROM health_heart_rate) +
                (SELECT COUNT(*) FROM health_body_temp) +
                (SELECT COUNT(*) FROM health_vo2max) as total"""
        ).fetchone()
        result["has_data"] = (total["total"] or 0) > 0

        # Readiness Score Calculation
        if result["has_data"]:
            score = 100
            insights = []
            now = datetime.now()
            hour = now.hour

            # ── Sleep quality ──
            sleep_sessions = result.get("sleep", [])
            sleep_score = sleep_sessions[0].get("sleep_score", 75) if sleep_sessions else 75
            sleep_hrs = sleep_sessions[0].get("duration_hours", 7) if sleep_sessions else 7
            if sleep_score >= 85:
                insights.append(f"Excellent sleep quality ({sleep_score}/100, {sleep_hrs}h). Full recovery registered.")
            elif sleep_score >= 70:
                penalty = (80 - sleep_score) * 0.5
                score -= penalty
                insights.append(f"Moderate sleep quality ({sleep_score}/100, {sleep_hrs}h). Minor recovery deficit.")
            else:
                penalty = (75 - sleep_score) * 1.2
                score -= penalty
                insights.append(f"Poor sleep ({sleep_score}/100, {sleep_hrs}h). Significant recovery deficit — avoid high intensity.")

            if sleep_hrs < 6:
                score -= 15
                insights.append(f"Sleep duration under 6 hours greatly impairs performance and hormonal recovery.")
            elif sleep_hrs > 9:
                score -= 5
                insights.append(f"Oversleeping ({sleep_hrs}h) can indicate systemic fatigue or illness.")

            # ── Activities logged today ──
            today_local_s = now.strftime("%Y-%m-%d")
            act_rows = conn.execute(
                "SELECT name, sport_type, suffer_score, elapsed_time FROM activities WHERE date(start_date_local) = ?",
                (today_local_s,)
            ).fetchall()
            acts_today = len(act_rows)

            cardio_acts = [a for a in act_rows if a["sport_type"] in ("Run", "Ride", "VirtualRide", "Swim", "Rowing", "Elliptical")]
            strength_acts = [a for a in act_rows if a["sport_type"] in ("WeightTraining", "Workout", "Crossfit")]

            if cardio_acts:
                score -= 40
                names = ', '.join(a['sport_type'] for a in cardio_acts)
                insights.append(f"Cardio already logged today ({names}). Cardiovascular system is in recovery — avoid further high-intensity cardio.")
            if strength_acts:
                score -= 30
                insights.append(f"Strength/weight training already logged. Muscles need 24–48h recovery — do not retrain same groups today.")
            if acts_today > 0 and not cardio_acts and not strength_acts:
                score -= 20
                insights.append(f"Activity already logged today. Consider active recovery or rest.")

            # ── Yesterday's training load ──
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            yest_acts = conn.execute(
                "SELECT sport_type, suffer_score FROM activities WHERE date(start_date_local) = ?",
                (yesterday,)
            ).fetchall()
            heavy_yesterday = [a for a in yest_acts if a["sport_type"] in ("Run", "Ride", "WeightTraining", "Swim")]
            if heavy_yesterday:
                score -= 10
                insights.append(f"High-load activity logged yesterday. Residual fatigue may still be present.")

            # ── Steps today ──
            steps_today = result.get("steps_today", 0)
            if steps_today > 15000:
                score -= 10
                insights.append(f"Very high step count today ({steps_today:,}). Passive fatigue may accumulate.")
            elif steps_today > 8000 and acts_today == 0:
                insights.append(f"Solid baseline activity ({steps_today:,} steps). Body is primed for a workout.")
            elif steps_today < 2000 and acts_today == 0:
                insights.append(f"Low movement so far today ({steps_today:,} steps). A light warmup or walk is recommended before any intense session.")

            # ── Resting heart rate ──
            if rhr:
                if rhr <= 55:
                    insights.append(f"Excellent resting HR ({rhr} bpm) — strong cardiovascular efficiency.")
                elif rhr <= 65:
                    pass  # normal, no note needed
                elif rhr <= 75:
                    penalty = (rhr - 65) * 0.6
                    score -= penalty
                    insights.append(f"Slightly elevated resting HR ({rhr} bpm). May indicate mild stress or under-recovery.")
                else:
                    penalty = (rhr - 65) * 1.0
                    score -= penalty
                    insights.append(f"Elevated resting HR ({rhr} bpm). Systemic stress detected — prioritise rest and hydration.")

            # ── Time of day ──
            if 5 <= hour < 9:
                score -= 5
                insights.append("Early morning: core body temp and neuromuscular response are still warming up. Performance peaks 4–8h after waking.")
            elif 10 <= hour <= 14:
                insights.append("Mid-morning to midday: near-optimal window for strength and skill training.")
            elif 15 <= hour <= 19:
                insights.append("Late afternoon / early evening: peak window for performance, reaction time and cardiovascular output.")
            elif hour >= 21:
                score -= 8
                insights.append("Late evening: high-intensity training now may elevate cortisol and impair sleep quality.")

            # ── Average HR today vs resting (activity load indicator) ──
            today_hr_row = conn.execute(
                "SELECT AVG(bpm) as avg_bpm FROM health_heart_rate WHERE date(time, 'localtime') = ?",
                (today_local_s,)
            ).fetchone()
            if today_hr_row and today_hr_row["avg_bpm"] and rhr:
                avg_bpm_today = today_hr_row["avg_bpm"]
                hr_elevation = avg_bpm_today - rhr
                if hr_elevation > 20:
                    score -= 10
                    insights.append(f"Average HR today is significantly elevated vs resting ({avg_bpm_today:.0f} vs {rhr} bpm). High cardiovascular load detected.")
                elif hr_elevation > 10:
                    score -= 5
                    insights.append(f"Moderate HR elevation today ({avg_bpm_today:.0f} avg vs {rhr} resting). Moderate exertion registered.")

            score = max(0, min(100, round(score)))

            if score >= 90:
                status = "Excellent"
                msg = "Prime condition. All systems are go for high-intensity training."
            elif score >= 70:
                status = "Good"
                msg = "Good recovery. Standard training load recommended."
            elif score >= 40:
                status = "Moderate"
                msg = "Moderate fatigue. Consider a lighter session or active recovery."
            else:
                status = "Poor"
                msg = "High systemic stress. Rest or very light movement only — do not train intensely."

            if not insights:
                insights.append("No major fatigue factors detected. All systems nominal.")

            result["readiness"] = {
                "score": score,
                "status": status,
                "message": msg,
                "insights": insights
            }
        else:
            result["readiness"] = None

    result["enabled"] = get_setting("hc_webhook_enabled") == "1"
    result["last_sync"] = get_setting("hc_last_sync", "")

    return jsonify(result)


# ─── Clear Health Data ─────────────────────────────────────────────

@health_connect_bp.route("/api/health-connect/clear", methods=["POST"])
def clear_health_data():
    """Clear all health data tables."""
    with get_db() as conn:
        conn.execute("DELETE FROM health_steps")
        conn.execute("DELETE FROM health_sleep")
        conn.execute("DELETE FROM health_heart_rate")
        conn.execute("DELETE FROM health_body_temp")
        conn.execute("DELETE FROM health_vo2max")
        conn.execute("DELETE FROM health_resting_heart_rate")
        conn.execute("DELETE FROM health_hrv")
        conn.execute("DELETE FROM health_oxygen_saturation")
        conn.execute("DELETE FROM health_respiratory_rate")
    set_setting("hc_last_sync", "")
    return jsonify({"message": "All health data cleared"})
