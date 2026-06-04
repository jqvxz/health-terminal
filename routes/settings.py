"""
HealthTerminal V1 — Settings Routes
User preferences, tab management, and data management.
"""

from flask import Blueprint, request, jsonify
from models.db import (
    get_all_settings, get_setting, set_setting, get_db,
    get_notifications, mark_notification_read, get_sync_history
)
import requests as http_requests

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/api/settings", methods=["GET"])
def get_settings():
    """Get all user settings."""
    settings = get_all_settings()
    # Never expose tokens to frontend
    safe = {k: v for k, v in settings.items()
            if k not in ("strava_access_token", "strava_refresh_token", "strava_token_expires")}
    return jsonify(safe)


@settings_bp.route("/api/settings", methods=["PUT"])
def update_settings():
    """Update one or more settings."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    allowed = [
        "body_weight", "weight_unit", "distance_unit", "theme",
        "enabled_tabs", "openrouter_api_key", "apininjas_api_key",
        "user_height", "user_age", "user_sex",
    ]

    updated = []
    for key, value in data.items():
        if key in allowed:
            set_setting(key, value)
            updated.append(key)

    # Calculate BMI in backend
    bmi_exceeded = False
    try:
        weight_str = get_setting("body_weight")
        weight_unit = get_setting("weight_unit", "kg")
        height_str = get_setting("user_height")

        if weight_str and height_str:
            weight = float(weight_str)
            height_cm = float(height_str)
            if height_cm > 0:
                height_m = height_cm / 100.0
                if weight_unit == "lbs":
                    weight_kg = weight * 0.45359237
                else:
                    weight_kg = weight
                bmi = weight_kg / (height_m * height_m)
                if bmi > 25.0:
                    bmi_exceeded = True
    except Exception:
        pass

    return jsonify({
        "message": f"Updated {len(updated)} settings",
        "updated": updated,
        "bmi_exceeded": bmi_exceeded
    })


@settings_bp.route("/api/settings/<key>", methods=["GET"])
def get_single_setting(key):
    """Get a single setting value."""
    value = get_setting(key, "")
    return jsonify({"key": key, "value": value})


@settings_bp.route("/api/settings/validate-key", methods=["POST"])
def validate_api_key():
    """Test the OpenRouter API key."""
    data = request.json
    key = data.get("key", "")
    if not key:
        return jsonify({"valid": False, "error": "No key provided"})

    try:
        resp = http_requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            info = resp.json()
            return jsonify({
                "valid": True,
                "label": info.get("data", {}).get("label", ""),
                "usage": info.get("data", {}).get("usage", 0),
                "limit": info.get("data", {}).get("limit", None),
            })
        else:
            return jsonify({"valid": False, "error": f"HTTP {resp.status_code}"})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@settings_bp.route("/api/settings/clear-cache", methods=["POST"])
def clear_cache():
    """Clear AI recommendation cache."""
    with get_db() as conn:
        conn.execute("DELETE FROM ai_cache")
    return jsonify({"message": "AI cache cleared"})


@settings_bp.route("/api/settings/clear-data", methods=["POST"])
def clear_data():
    """Clear all activity data (keeps settings)."""
    with get_db() as conn:
        conn.execute("DELETE FROM lifting_sessions")
        conn.execute("DELETE FROM activities")
        conn.execute("DELETE FROM sync_log")
        conn.execute("DELETE FROM ai_cache")
        conn.execute("DELETE FROM ai_usage")
    set_setting("last_sync", "")
    return jsonify({"message": "All activity data cleared"})


@settings_bp.route("/api/settings/sync-history")
def sync_history():
    """Get sync history."""
    history = get_sync_history(20)
    return jsonify(history)


@settings_bp.route("/api/notifications")
def get_notifs():
    """Get notifications."""
    unread = request.args.get("unread", "false") == "true"
    notifs = get_notifications(unread_only=unread)
    return jsonify(notifs)


@settings_bp.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def mark_read(notif_id):
    """Mark a notification as read."""
    mark_notification_read(notif_id)
    return jsonify({"message": "Marked as read"})


@settings_bp.route("/api/notifications/read-all", methods=["POST"])
def mark_all_read():
    """Mark all notifications as read."""
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read = 1")
    return jsonify({"message": "All marked as read"})
