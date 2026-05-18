"""
HealthTerminal V1 — AI Routes
OpenRouter API integration for AI-powered recommendations.
"""

from flask import Blueprint, request, jsonify
import requests
import hashlib
import json
from config import Config
from models.db import (
    get_db, get_setting, get_activities, get_goals,
    get_ai_usage_today, increment_ai_usage,
    get_weekly_stats, get_muscle_group_stats
)

ai_bp = Blueprint("ai", __name__)


def _build_context():
    """Build a data context string for the AI from recent activity data."""
    parts = []

    # User profile
    weight = get_setting("body_weight")
    height = get_setting("user_height")
    age = get_setting("user_age")
    sex = get_setting("user_sex")
    weight_unit = get_setting("weight_unit") or "kg"
    profile_parts = []
    if weight:
        profile_parts.append(f"Weight: {weight}{weight_unit}")
    if height:
        profile_parts.append(f"Height: {height}cm")
    if age:
        profile_parts.append(f"Age: {age}")
    if sex:
        profile_parts.append(f"Sex: {sex}")
    if profile_parts:
        parts.append("## User Profile:")
        parts.append(", ".join(profile_parts))

    # Recent activities
    recent = get_activities(limit=20)
    if recent:
        parts.append("## Recent Activities (last 20):")
        for a in recent:
            duration_min = round(a["moving_time"] / 60, 1) if a["moving_time"] else 0
            dist_km = round(a["distance"] / 1000, 2) if a["distance"] else 0
            line = f"- {a['start_date_local'][:10]} | {a['name']} | {a['activity_type']}"
            if dist_km > 0:
                line += f" | {dist_km}km"
            line += f" | {duration_min}min"
            if a["average_heartrate"]:
                line += f" | HR:{a['average_heartrate']}bpm"
            if a["calories"]:
                line += f" | {a['calories']}kcal"
            parts.append(line)

    # Weekly stats
    stats = get_weekly_stats(0)
    if stats:
        parts.append("\n## This Week Stats:")
        r = stats.get("running", {})
        l = stats.get("lifting", {})
        if r.get("count", 0) > 0:
            parts.append(f"- Running: {r['count']} sessions, {round(r['total_distance']/1000, 1)}km total")
        if l.get("count", 0) > 0:
            parts.append(f"- Lifting: {l['count']} sessions")
        if stats.get("total_volume", 0) > 0:
            parts.append(f"- Total volume lifted: {round(stats['total_volume'])}kg")

    # Muscle groups
    muscles = get_muscle_group_stats(7)
    if muscles:
        parts.append("\n## Muscle Groups Trained (7 days):")
        for m in muscles:
            parts.append(f"- {m['muscle_group']}: {m['session_count']} sessions, {round(m['total_volume'])}kg volume")

    # Goals
    goals = get_goals("active")
    if goals:
        parts.append("\n## Active Goals:")
        for g in goals:
            pct = round((g["current_value"] / g["target_value"]) * 100, 1) if g["target_value"] > 0 else 0
            parts.append(f"- {g['title']}: {g['current_value']}/{g['target_value']} {g['unit']} ({pct}%)")

    return "\n".join(parts) if parts else "No activity data available yet."


@ai_bp.route("/api/ai/analyze", methods=["POST"])
def analyze():
    """Trigger AI analysis — button-activated only."""
    api_key = get_setting("openrouter_api_key") or Config.OPENROUTER_API_KEY
    if not api_key:
        return jsonify({"error": "OpenRouter API key not configured. Add it in Settings."}), 400

    # Check daily limit
    usage = get_ai_usage_today()
    if usage >= Config.OPENROUTER_DAILY_LIMIT:
        return jsonify({"error": f"Daily limit reached ({Config.OPENROUTER_DAILY_LIMIT} requests). Try again tomorrow."}), 429

    # Build prompt
    user_msg = request.json.get("prompt", "")
    context = _build_context()
    full_prompt = f"{context}\n\n---\nUser question: {user_msg}" if user_msg else f"{context}\n\n---\nPlease analyze my recent training data and provide personalized recommendations for optimizing my performance. Include suggestions for training adjustments, recovery, and nutrition."

    # Check cache
    prompt_hash = hashlib.md5(full_prompt.encode()).hexdigest()
    with get_db() as conn:
        cached = conn.execute(
            "SELECT response FROM ai_cache WHERE prompt_hash = ?", (prompt_hash,)
        ).fetchone()
        if cached:
            return jsonify({"response": cached["response"], "cached": True, "usage": usage})

    # Call OpenRouter
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": Config.BASE_URL,
            "X-Title": "HealthTerminal",
            "Content-Type": "application/json",
        }
        payload = {
            "model": Config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": Config.AI_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            "max_tokens": 2000,
        }

        resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code != 200:
            return jsonify({"error": f"API error: {resp.status_code}"}), resp.status_code

        data = resp.json()
        ai_response = data["choices"][0]["message"]["content"]

        # Cache response
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai_cache (prompt_hash, prompt_summary, response) VALUES (?, ?, ?)",
                (prompt_hash, (user_msg or "auto-analysis")[:100], ai_response),
            )

        # Track usage
        increment_ai_usage()

        return jsonify({"response": ai_response, "cached": False, "usage": usage + 1})

    except requests.exceptions.Timeout:
        return jsonify({"error": "AI request timed out. Please try again."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/api/ai/usage")
def ai_usage():
    """Get current AI usage stats."""
    usage = get_ai_usage_today()
    return jsonify({
        "used": usage,
        "limit": Config.OPENROUTER_DAILY_LIMIT,
        "remaining": max(0, Config.OPENROUTER_DAILY_LIMIT - usage),
    })


@ai_bp.route("/api/ai/history")
def ai_history():
    """Get cached AI recommendations."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT prompt_summary, response, created_at FROM ai_cache ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
