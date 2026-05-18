"""
HealthTerminal V1 — Export Routes
CSV and JSON data export with filters, lifting detail export, and share image.
"""

from flask import Blueprint, request, jsonify, Response
import csv
import io
import json
from models.db import get_activities, get_lifting_details, get_weekly_stats, get_overview_stats

export_bp = Blueprint("export", __name__)


@export_bp.route("/api/export/json")
def export_json():
    """Export activities as JSON."""
    activities = _get_filtered_activities()
    # Add lifting details for hevy activities
    for a in activities:
        if a.get("is_hevy"):
            a["lifting_details"] = get_lifting_details(a["id"])

    response = Response(
        json.dumps(activities, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=healthterminal_export.json"},
    )
    return response


@export_bp.route("/api/export/csv")
def export_csv():
    """Export activities as CSV."""
    activities = _get_filtered_activities()
    include_lifting = request.args.get("include_lifting", "false") == "true"

    output = io.StringIO()
    writer = csv.writer(output)

    if include_lifting:
        # Detailed export with lifting data
        writer.writerow([
            "Date", "Name", "Type", "Distance (m)", "Duration (min)",
            "Avg Speed (m/s)", "Avg HR", "Max HR", "Elevation (m)",
            "Calories", "Source", "Exercise", "Set", "Reps",
            "Weight", "Weight Unit", "Warmup", "Muscle Group"
        ])

        for a in activities:
            base_row = [
                a.get("start_date_local", "")[:10],
                a.get("name", ""),
                a.get("activity_type", ""),
                round(a.get("distance", 0), 1),
                round(a.get("moving_time", 0) / 60, 1),
                round(a.get("average_speed", 0), 2),
                a.get("average_heartrate", 0),
                a.get("max_heartrate", 0),
                round(a.get("total_elevation_gain", 0), 1),
                round(a.get("calories", 0), 1),
                a.get("source", ""),
            ]

            if a.get("is_hevy"):
                details = get_lifting_details(a["id"])
                if details:
                    for d in details:
                        writer.writerow(base_row + [
                            d.get("exercise_name", ""),
                            d.get("set_number", ""),
                            d.get("reps", ""),
                            d.get("weight", ""),
                            d.get("weight_unit", "kg"),
                            "Yes" if d.get("is_warmup") else "No",
                            d.get("muscle_group", ""),
                        ])
                else:
                    writer.writerow(base_row + ["", "", "", "", "", "", ""])
            else:
                writer.writerow(base_row + ["", "", "", "", "", "", ""])
    else:
        # Standard export
        writer.writerow([
            "Date", "Name", "Type", "Distance (m)", "Duration (min)",
            "Avg Speed (m/s)", "Avg HR", "Max HR", "Elevation (m)",
            "Calories", "Source"
        ])

        for a in activities:
            writer.writerow([
                a.get("start_date_local", "")[:10],
                a.get("name", ""),
                a.get("activity_type", ""),
                round(a.get("distance", 0), 1),
                round(a.get("moving_time", 0) / 60, 1),
                round(a.get("average_speed", 0), 2),
                a.get("average_heartrate", 0),
                a.get("max_heartrate", 0),
                round(a.get("total_elevation_gain", 0), 1),
                round(a.get("calories", 0), 1),
                a.get("source", ""),
            ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=healthterminal_export.csv"},
    )
    return response


@export_bp.route("/api/export/summary")
def export_summary():
    """Get export summary stats before downloading."""
    activities = _get_filtered_activities()
    if not activities:
        return jsonify({"count": 0, "date_range": "", "types": {}})

    types = {}
    for a in activities:
        t = "Lifting" if a.get("is_hevy") else (a.get("activity_type") or "Other")
        types[t] = types.get(t, 0) + 1

    dates = [a.get("start_date_local", "")[:10] for a in activities if a.get("start_date_local")]
    date_range = f"{min(dates)} to {max(dates)}" if dates else ""

    total_distance = sum(a.get("distance", 0) for a in activities) / 1000
    total_calories = sum(a.get("calories", 0) for a in activities)
    total_time = sum(a.get("moving_time", 0) for a in activities) / 3600

    return jsonify({
        "count": len(activities),
        "date_range": date_range,
        "types": types,
        "total_distance_km": round(total_distance, 1),
        "total_calories": round(total_calories),
        "total_hours": round(total_time, 1),
    })


@export_bp.route("/api/export/share-data")
def share_data():
    """Get data for generating a share image on the frontend (Canvas API)."""
    overview = get_overview_stats()
    weekly = get_weekly_stats(0)

    return jsonify({
        "total_activities": overview.get("total_activities", 0),
        "total_distance_km": round((overview.get("running", {}).get("total_distance", 0)) / 1000, 1),
        "total_volume_kg": round(overview.get("total_volume", 0)),
        "lifting_sessions": overview.get("lifting_count", 0),
        "running_count": overview.get("running", {}).get("count", 0),
        "max_weight_kg": round(overview.get("max_weight", 0), 1),
        "top_exercises": overview.get("top_exercises", [])[:5],
        "personal_bests": overview.get("personal_bests", [])[:5],
        "week": {
            "running_km": round((weekly.get("running", {}).get("total_distance", 0)) / 1000, 1),
            "sessions": (weekly.get("running", {}).get("count", 0)) + (weekly.get("lifting", {}).get("count", 0)),
            "volume": round(weekly.get("total_volume", 0)),
        },
    })


def _get_filtered_activities():
    """Get activities with query parameter filters."""
    activity_type = request.args.get("type")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = int(request.args.get("limit", 1000))
    return get_activities(activity_type, limit, 0, start_date, end_date)
