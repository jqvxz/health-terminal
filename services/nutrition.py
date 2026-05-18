"""
HealthTerminal V1 — Nutrition Service
Calorie estimation and macro recommendation formulas.
"""

from config import Config


def estimate_calories_running(distance_m, duration_s, body_weight_kg, heartrate_avg=None):
    """Estimate calories burned during running using MET values adjusted for speed."""
    if duration_s <= 0:
        return 0
    hours = duration_s / 3600
    met = 9.8
    if distance_m > 0:
        speed_kmh = (distance_m / 1000) / hours
        if speed_kmh < 8:
            met = 8.0
        elif speed_kmh < 10:
            met = 9.8
        elif speed_kmh < 12:
            met = 11.0
        elif speed_kmh < 14:
            met = 12.8
        else:
            met = 14.5
    return round(met * body_weight_kg * hours, 1)


def estimate_calories_lifting(duration_s, body_weight_kg, intensity="moderate"):
    """Estimate calories burned during weight training."""
    if duration_s <= 0:
        return 0
    hours = duration_s / 3600
    multiplier = {"light": 0.7, "moderate": 1.0, "vigorous": 1.3, "intense": 1.5}
    met = 6.0 * multiplier.get(intensity, 1.0)
    return round(met * body_weight_kg * hours, 1)


def estimate_calories_general(activity_type, duration_s, body_weight_kg):
    """Estimate calories for any activity type."""
    if duration_s <= 0:
        return 0
    hours = duration_s / 3600
    activity_map = {"Ride": "cycling", "Swim": "swimming", "Hike": "hiking", "Walk": "walking", "Yoga": "yoga"}
    met_key = activity_map.get(activity_type, "default")
    met = Config.MET_VALUES.get(met_key, 5.0)
    return round(met * body_weight_kg * hours, 1)


def get_macro_recommendations(calories_burned, activity_type, body_weight_kg):
    """Generate macro nutrient recommendations based on activity and calories."""
    from models.db import get_setting
    
    if activity_type in ("Run", "VirtualRun", "TrailRun", "Ride", "Swim"):
        p, c, f = 0.25, 0.55, 0.20
    elif activity_type in ("WeightTraining", "Workout"):
        p, c, f = 0.35, 0.40, 0.25
    else:
        p, c, f = 0.30, 0.45, 0.25

    # Fetch additional settings for precise Mifflin-St Jeor BMR
    height_cm = float(get_setting("user_height", "175") or 175)
    age_yrs = float(get_setting("user_age", "25") or 25)
    sex = get_setting("user_sex", "male")

    # Mifflin-St Jeor equation
    bmr = (10.0 * body_weight_kg) + (6.25 * height_cm) - (5.0 * age_yrs)
    if sex == "female":
        bmr -= 161.0
    else:
        bmr += 5.0

    # Calculate NEAT (Non-Exercise Activity Thermogenesis)
    # Assuming baseline daily mobility of ~7000 steps (approx. 5km / 1 hour of walking at 3.5 METs)
    neat_calories = 3.5 * body_weight_kg

    total = bmr + neat_calories + calories_burned
    return {
        "total_calories": round(total),
        "calories_burned": round(calories_burned),
        "protein_g": int(round((total * p) / 4)),
        "carbs_g": int(round((total * c) / 4)),
        "fat_g": int(round((total * f) / 9)),
    }
