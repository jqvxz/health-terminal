"""
HealthTerminal V1 — Goals Routes
CRUD operations for user-defined fitness goals.
"""

from flask import Blueprint, request, jsonify
from models.db import get_db, get_goals, get_distinct_exercises

goals_bp = Blueprint("goals", __name__)


@goals_bp.route("/api/goals", methods=["GET"])
def list_goals():
    """List all goals, optionally filtered by status."""
    status = request.args.get("status")
    goals = get_goals(status)
    return jsonify(goals)


@goals_bp.route("/api/goals", methods=["POST"])
def create_goal():
    """Create a new goal."""
    data = request.json
    if not data or not data.get("title") or not data.get("target_value"):
        return jsonify({"error": "Title and target value required"}), 400

    with get_db() as conn:
        conn.execute(
            """INSERT INTO goals (title, goal_type, activity_type, metric, target_value, unit, deadline)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data["title"],
                data.get("goal_type", "custom"),
                data.get("activity_type", ""),
                data.get("metric", "custom"),
                float(data["target_value"]),
                data.get("unit", ""),
                data.get("deadline", ""),
            ),
        )
    return jsonify({"message": "Goal created"}), 201


@goals_bp.route("/api/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    """Update a goal's progress or details."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    sets = []
    params = []
    for field in ["title", "current_value", "target_value", "status", "deadline", "unit"]:
        if field in data:
            sets.append(f"{field} = ?")
            params.append(data[field])

    if not sets:
        return jsonify({"error": "No valid fields to update"}), 400

    sets.append("updated_at = datetime('now')")
    params.append(goal_id)

    with get_db() as conn:
        conn.execute(f"UPDATE goals SET {', '.join(sets)} WHERE id = ?", params)
    return jsonify({"message": "Goal updated"})


@goals_bp.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    """Delete a goal."""
    with get_db() as conn:
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return jsonify({"message": "Goal deleted"})


@goals_bp.route("/api/exercises", methods=["GET"])
def list_exercises():
    """List distinct exercise names from logged lifting data."""
    exercises = get_distinct_exercises()
    return jsonify(exercises)
