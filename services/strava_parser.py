"""
HealthTerminal V1 — Strava Parser Service
Identifies Hevy-logged activities and parses workout data from descriptions.
"""

import re
from services.muscle_map import get_muscle_info


HEVY_KEYWORDS = ["hevy", "weight training", "weighttraining", "workout log"]


def is_hevy_activity(activity):
    """Check if a Strava activity was logged via Hevy."""
    name = (activity.get("name", "") or "").lower()
    desc = (activity.get("description", "") or "").lower()
    ext_id = (activity.get("external_id", "") or "").lower()
    sport = (activity.get("sport_type", "") or "").lower()

    for kw in HEVY_KEYWORDS:
        if kw in name or kw in desc or kw in ext_id:
            return True

    if sport in ("weighttraining", "weight_training"):
        return True
    if activity.get("type", "") in ("WeightTraining", "Workout"):
        return True

    return False


def parse_hevy_description(description):
    """
    Parse a Hevy workout description into structured exercise data.
    Hevy typically formats descriptions like:
      Exercise Name
      Set 1: 10 reps × 60 kg
      Set 2: 8 reps × 65 kg
      ...
    Or variations like:
      Exercise Name: 3x10 @ 60kg
    """
    if not description:
        return []

    exercises = []
    lines = description.strip().split("\n")
    current_exercise = None
    set_number = 0

    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue

        # Skip quoted notes — Hevy wraps user notes in double quotes
        if line.startswith('"') or line.startswith('\u201c'):
            continue

        # Skip lines that are only special characters, emoji, or very short junk
        clean_check = re.sub(r'[^\w\s]', '', line).strip()
        if len(clean_check) < 2 and not re.search(r'\d', line):
            continue

        # Check if line is a set entry (contains reps/weight pattern)
        set_data = _parse_set_line(line)
        if set_data and current_exercise:
            set_number += 1
            muscle_info = get_muscle_info(current_exercise)
            exercises.append({
                "exercise_name": current_exercise,
                "muscle_group": muscle_info["primary"],
                "secondary_muscles": ", ".join(muscle_info["secondary"]),
                "set_number": set_number,
                "reps": set_data["reps"],
                "weight": set_data["weight"],
                "weight_unit": set_data.get("unit", "kg"),
                "is_warmup": set_data.get("is_warmup", False),
            })
        # Check for compact format: "Bench Press: 3x10 @ 60kg"
        elif _is_compact_format(line):
            parsed = _parse_compact_line(line)
            for p in parsed:
                muscle_info = get_muscle_info(p["exercise_name"])
                exercises.append({
                    **p,
                    "muscle_group": muscle_info["primary"],
                    "secondary_muscles": ", ".join(muscle_info["secondary"]),
                })
        else:
            # Treat as exercise name
            clean = re.sub(r"^[-•*]\s*", "", line).strip()
            clean = re.sub(r":$", "", clean).strip()
            # Must not start with a digit, not be in quotes, and be reasonable length
            if (clean and not clean[0].isdigit()
                    and not clean.startswith('"') and not clean.startswith('\u201c')
                    and not clean.endswith('"') and not clean.endswith('\u201d')
                    and len(clean) > 1):
                current_exercise = clean
                set_number = 0

    return exercises


def _parse_set_line(line):
    """Parse a single set line like 'Set 1: 10 reps × 60 kg' or '10 x 60kg'."""
    line_lower = line.lower()
    is_warmup = "warm" in line_lower

    # Pattern: "Set N: X reps × Y kg/lbs"
    m = re.search(r"(\d+)\s*(?:reps?)?\s*[×x@]\s*([\d.]+)\s*(kg|lbs?|lb)?", line, re.I)
    if m:
        return {
            "reps": int(m.group(1)),
            "weight": float(m.group(2)),
            "unit": (m.group(3) or "kg").replace("lbs", "kg").replace("lb", "kg"),
            "is_warmup": is_warmup,
        }

    # Pattern: "Y kg × X reps" (reversed)
    m = re.search(r"([\d.]+)\s*(kg|lbs?|lb)?\s*[×x@]\s*(\d+)\s*(?:reps?)?", line, re.I)
    if m:
        return {
            "reps": int(m.group(3)),
            "weight": float(m.group(1)),
            "unit": (m.group(2) or "kg"),
            "is_warmup": is_warmup,
        }

    # Pattern: just "X reps" (bodyweight)
    m = re.search(r"(\d+)\s*reps?", line, re.I)
    if m:
        return {"reps": int(m.group(1)), "weight": 0, "unit": "kg", "is_warmup": is_warmup}

    return None


def _is_compact_format(line):
    """Check if line is compact format like 'Bench Press: 3x10 @ 60kg'."""
    return bool(re.search(r":\s*\d+\s*[×x]\s*\d+\s*[@×x]\s*[\d.]+", line, re.I))


def _parse_compact_line(line):
    """Parse compact format: 'Exercise: SETSxREPS @ WEIGHTkg'."""
    m = re.match(r"(.+?):\s*(\d+)\s*[×x]\s*(\d+)\s*[@×x]\s*([\d.]+)\s*(kg|lbs?)?", line, re.I)
    if not m:
        return []

    name = m.group(1).strip()
    sets = int(m.group(2))
    reps = int(m.group(3))
    weight = float(m.group(4))
    unit = (m.group(5) or "kg")

    return [
        {
            "exercise_name": name,
            "set_number": i + 1,
            "reps": reps,
            "weight": weight,
            "weight_unit": unit,
            "is_warmup": False,
        }
        for i in range(sets)
    ]
