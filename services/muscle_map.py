"""
HealthTerminal V1 — Muscle Map Service
Maps exercises to primary and secondary muscle groups.
"""

MUSCLE_GROUPS = [
    "Chest", "Back", "Shoulders", "Biceps", "Triceps",
    "Quadriceps", "Hamstrings", "Glutes", "Calves",
    "Core", "Forearms", "Traps", "Lats", "Abductors", "Adductors"
]

EXERCISE_MAP = {
    # === Chest ===
    "bench press": {"primary": "Chest", "secondary": ["Triceps", "Shoulders"]},
    "incline bench press": {"primary": "Chest", "secondary": ["Shoulders", "Triceps"]},
    "decline bench press": {"primary": "Chest", "secondary": ["Triceps"]},
    "dumbbell bench press": {"primary": "Chest", "secondary": ["Triceps", "Shoulders"]},
    "bench press (dumbbell)": {"primary": "Chest", "secondary": ["Triceps", "Shoulders"]},
    "incline dumbbell press": {"primary": "Chest", "secondary": ["Shoulders", "Triceps"]},
    "dumbbell fly": {"primary": "Chest", "secondary": ["Shoulders"]},
    "incline dumbbell fly": {"primary": "Chest", "secondary": ["Shoulders"]},
    "cable fly": {"primary": "Chest", "secondary": ["Shoulders"]},
    "cable crossover": {"primary": "Chest", "secondary": ["Shoulders"]},
    "chest press machine": {"primary": "Chest", "secondary": ["Triceps"]},
    "chest press": {"primary": "Chest", "secondary": ["Triceps"]},
    "push up": {"primary": "Chest", "secondary": ["Triceps", "Shoulders", "Core"]},
    "push-up": {"primary": "Chest", "secondary": ["Triceps", "Shoulders", "Core"]},
    "dips": {"primary": "Chest", "secondary": ["Triceps", "Shoulders"]},
    "chest dip": {"primary": "Chest", "secondary": ["Triceps", "Shoulders"]},
    "pec deck": {"primary": "Chest", "secondary": []},
    "butterfly": {"primary": "Chest", "secondary": []},
    "butterfly (pec deck)": {"primary": "Chest", "secondary": []},
    "pec fly": {"primary": "Chest", "secondary": []},
    "machine fly": {"primary": "Chest", "secondary": []},

    # === Back ===
    "deadlift": {"primary": "Back", "secondary": ["Hamstrings", "Glutes", "Core", "Traps"]},
    "barbell row": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "bent over row": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "pendlay row": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "dumbbell row": {"primary": "Back", "secondary": ["Biceps"]},
    "one arm dumbbell row": {"primary": "Back", "secondary": ["Biceps"]},
    "seated cable row": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "seated cable row - bar grip": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "cable row": {"primary": "Back", "secondary": ["Biceps", "Traps"]},
    "t bar row": {"primary": "Back", "secondary": ["Biceps", "Traps", "Lats"]},
    "t-bar row": {"primary": "Back", "secondary": ["Biceps", "Traps", "Lats"]},
    "face pull": {"primary": "Back", "secondary": ["Shoulders", "Traps"]},
    "cable pullover": {"primary": "Lats", "secondary": ["Chest"]},
    "straight arm pulldown": {"primary": "Lats", "secondary": ["Core"]},
    "back extension": {"primary": "Back", "secondary": ["Glutes", "Hamstrings"]},
    "hyperextension": {"primary": "Back", "secondary": ["Glutes"]},
    "meadows row": {"primary": "Back", "secondary": ["Biceps"]},
    "chest supported row": {"primary": "Back", "secondary": ["Biceps"]},
    "machine row": {"primary": "Back", "secondary": ["Biceps"]},

    # === Lats ===
    "lat pulldown": {"primary": "Lats", "secondary": ["Biceps"]},
    "lat pulldown (cable)": {"primary": "Lats", "secondary": ["Biceps"]},
    "wide grip lat pulldown": {"primary": "Lats", "secondary": ["Biceps"]},
    "close grip lat pulldown": {"primary": "Lats", "secondary": ["Biceps"]},
    "pull up": {"primary": "Lats", "secondary": ["Biceps", "Core"]},
    "pull-up": {"primary": "Lats", "secondary": ["Biceps", "Core"]},
    "chin up": {"primary": "Lats", "secondary": ["Biceps"]},
    "chin-up": {"primary": "Lats", "secondary": ["Biceps"]},

    # === Shoulders ===
    "overhead press": {"primary": "Shoulders", "secondary": ["Triceps", "Core"]},
    "overhead press (smith machine)": {"primary": "Shoulders", "secondary": ["Triceps"]},
    "shoulder press": {"primary": "Shoulders", "secondary": ["Triceps"]},
    "shoulder press (machine plates)": {"primary": "Shoulders", "secondary": ["Triceps"]},
    "military press": {"primary": "Shoulders", "secondary": ["Triceps", "Core"]},
    "dumbbell shoulder press": {"primary": "Shoulders", "secondary": ["Triceps"]},
    "lateral raise": {"primary": "Shoulders", "secondary": []},
    "single arm lateral raise": {"primary": "Shoulders", "secondary": []},
    "single arm lateral raise (cable)": {"primary": "Shoulders", "secondary": []},
    "cable lateral raise": {"primary": "Shoulders", "secondary": []},
    "dumbbell lateral raise": {"primary": "Shoulders", "secondary": []},
    "front raise": {"primary": "Shoulders", "secondary": []},
    "rear delt fly": {"primary": "Shoulders", "secondary": ["Back"]},
    "reverse fly": {"primary": "Shoulders", "secondary": ["Back"]},
    "reverse pec deck": {"primary": "Shoulders", "secondary": ["Back"]},
    "arnold press": {"primary": "Shoulders", "secondary": ["Triceps"]},
    "upright row": {"primary": "Shoulders", "secondary": ["Traps"]},

    # === Traps ===
    "shrug": {"primary": "Traps", "secondary": ["Shoulders"]},
    "barbell shrug": {"primary": "Traps", "secondary": []},
    "dumbbell shrug": {"primary": "Traps", "secondary": []},

    # === Biceps ===
    "bicep curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "barbell curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "dumbbell curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "hammer curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "preacher curl": {"primary": "Biceps", "secondary": []},
    "preacher curl (machine)": {"primary": "Biceps", "secondary": []},
    "single arm preacher curl": {"primary": "Biceps", "secondary": []},
    "single arm preacher curl (bench 60°)": {"primary": "Biceps", "secondary": []},
    "concentration curl": {"primary": "Biceps", "secondary": []},
    "cable curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "incline curl": {"primary": "Biceps", "secondary": []},
    "incline dumbbell curl": {"primary": "Biceps", "secondary": []},
    "seated incline curl": {"primary": "Biceps", "secondary": []},
    "seated incline curl (dumbbell)": {"primary": "Biceps", "secondary": []},
    "ez bar curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "spider curl": {"primary": "Biceps", "secondary": []},
    "bayesian curl": {"primary": "Biceps", "secondary": []},
    "reverse curl": {"primary": "Biceps", "secondary": ["Forearms"]},
    "drag curl": {"primary": "Biceps", "secondary": []},

    # === Triceps ===
    "tricep pushdown": {"primary": "Triceps", "secondary": []},
    "triceps rope pushdown": {"primary": "Triceps", "secondary": []},
    "tricep rope pushdown": {"primary": "Triceps", "secondary": []},
    "rope pushdown": {"primary": "Triceps", "secondary": []},
    "cable pushdown": {"primary": "Triceps", "secondary": []},
    "tricep extension": {"primary": "Triceps", "secondary": []},
    "overhead tricep extension": {"primary": "Triceps", "secondary": []},
    "skull crusher": {"primary": "Triceps", "secondary": []},
    "close grip bench press": {"primary": "Triceps", "secondary": ["Chest"]},
    "tricep dip": {"primary": "Triceps", "secondary": ["Chest", "Shoulders"]},
    "tricep kickback": {"primary": "Triceps", "secondary": []},
    "diamond push up": {"primary": "Triceps", "secondary": ["Chest"]},
    "jm press": {"primary": "Triceps", "secondary": []},

    # === Forearms ===
    "wrist curl": {"primary": "Forearms", "secondary": []},
    "reverse wrist curl": {"primary": "Forearms", "secondary": []},
    "farmer's walk": {"primary": "Forearms", "secondary": ["Traps", "Core"]},

    # === Quadriceps ===
    "squat": {"primary": "Quadriceps", "secondary": ["Glutes", "Hamstrings", "Core"]},
    "back squat": {"primary": "Quadriceps", "secondary": ["Glutes", "Hamstrings", "Core"]},
    "front squat": {"primary": "Quadriceps", "secondary": ["Core", "Glutes"]},
    "leg press": {"primary": "Quadriceps", "secondary": ["Glutes", "Hamstrings"]},
    "leg extension": {"primary": "Quadriceps", "secondary": []},
    "hack squat": {"primary": "Quadriceps", "secondary": ["Glutes"]},
    "goblet squat": {"primary": "Quadriceps", "secondary": ["Core", "Glutes"]},
    "sissy squat": {"primary": "Quadriceps", "secondary": []},
    "lunge": {"primary": "Quadriceps", "secondary": ["Glutes", "Hamstrings"]},
    "walking lunge": {"primary": "Quadriceps", "secondary": ["Glutes"]},
    "bulgarian split squat": {"primary": "Quadriceps", "secondary": ["Glutes"]},
    "step up": {"primary": "Quadriceps", "secondary": ["Glutes"]},

    # === Hamstrings ===
    "leg curl": {"primary": "Hamstrings", "secondary": []},
    "seated leg curl": {"primary": "Hamstrings", "secondary": []},
    "lying leg curl": {"primary": "Hamstrings", "secondary": []},
    "romanian deadlift": {"primary": "Hamstrings", "secondary": ["Glutes", "Back"]},
    "stiff leg deadlift": {"primary": "Hamstrings", "secondary": ["Glutes", "Back"]},
    "good morning": {"primary": "Hamstrings", "secondary": ["Back", "Glutes"]},
    "nordic curl": {"primary": "Hamstrings", "secondary": []},

    # === Glutes, Abductors & Adductors ===
    "hip thrust": {"primary": "Glutes", "secondary": ["Hamstrings"]},
    "glute bridge": {"primary": "Glutes", "secondary": ["Hamstrings"]},
    "cable kickback": {"primary": "Glutes", "secondary": []},
    "hip abduction": {"primary": "Abductors", "secondary": ["Glutes"]},
    "hip adduction": {"primary": "Adductors", "secondary": []},

    # === Calves ===
    "calf raise": {"primary": "Calves", "secondary": []},
    "seated calf raise": {"primary": "Calves", "secondary": []},
    "standing calf raise": {"primary": "Calves", "secondary": []},

    # === Core ===
    "plank": {"primary": "Core", "secondary": ["Shoulders"]},
    "crunch": {"primary": "Core", "secondary": []},
    "crunch (machine)": {"primary": "Core", "secondary": []},
    "machine crunch": {"primary": "Core", "secondary": []},
    "cable crunch": {"primary": "Core", "secondary": []},
    "sit up": {"primary": "Core", "secondary": []},
    "russian twist": {"primary": "Core", "secondary": []},
    "leg raise": {"primary": "Core", "secondary": []},
    "hanging leg raise": {"primary": "Core", "secondary": ["Forearms"]},
    "ab wheel rollout": {"primary": "Core", "secondary": ["Shoulders"]},
    "wood chop": {"primary": "Core", "secondary": ["Shoulders"]},
    "dead bug": {"primary": "Core", "secondary": []},
    "mountain climber": {"primary": "Core", "secondary": ["Shoulders"]},
    "pallof press": {"primary": "Core", "secondary": []},
}

# Keyword-based fallback: maps keywords to muscle groups
# Order matters — more specific keywords should come first
KEYWORD_RULES = [
    # Biceps keywords (must be before chest to prevent "incline curl" → Chest)
    (["curl"], "Biceps"),
    (["bicep"], "Biceps"),

    # Triceps keywords
    (["pushdown"], "Triceps"),
    (["tricep"], "Triceps"),
    (["skull crush"], "Triceps"),

    # Back / Lats keywords
    (["row"], "Back"),
    (["pulldown"], "Lats"),
    (["pull down"], "Lats"),
    (["pull up", "pullup", "chin up", "chinup"], "Lats"),
    (["lat "], "Lats"),
    (["deadlift"], "Back"),

    # Chest keywords
    (["bench press"], "Chest"),
    (["chest"], "Chest"),
    (["pec ", "peck"], "Chest"),
    (["butterfly"], "Chest"),
    (["fly"], "Chest"),
    (["push up", "pushup"], "Chest"),

    # Shoulder keywords
    (["lateral raise"], "Shoulders"),
    (["shoulder"], "Shoulders"),
    (["overhead press"], "Shoulders"),
    (["military"], "Shoulders"),
    (["delt"], "Shoulders"),
    (["arnold"], "Shoulders"),

    # Traps
    (["shrug"], "Traps"),
    (["face pull"], "Back"),

    # Legs
    (["squat"], "Quadriceps"),
    (["leg press"], "Quadriceps"),
    (["leg ext"], "Quadriceps"),
    (["lunge"], "Quadriceps"),
    (["split squat"], "Quadriceps"),
    (["step up"], "Quadriceps"),
    (["leg curl"], "Hamstrings"),
    (["romanian"], "Hamstrings"),
    (["rdl"], "Hamstrings"),
    (["hip thrust"], "Glutes"),
    (["glute"], "Glutes"),
    (["abductor", "abduction"], "Abductors"),
    (["adductor", "adduction"], "Adductors"),
    (["calf", "calve"], "Calves"),

    # Core
    (["crunch"], "Core"),
    (["plank"], "Core"),
    (["sit up", "situp"], "Core"),
    (["ab "], "Core"),
]


def get_muscle_info(exercise_name):
    """Look up muscle groups for an exercise name. Uses exact match, then keyword rules."""
    name = exercise_name.lower().strip()

    # 1. Direct match
    if name in EXERCISE_MAP:
        return EXERCISE_MAP[name]

    # 2. Exact key contained in name or name contained in key
    #    Sort by key length descending so longer (more specific) matches win
    sorted_keys = sorted(EXERCISE_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in name or name in key:
            return EXERCISE_MAP[key]

    # 3. Keyword-based fallback (order-sensitive)
    for keywords, muscle in KEYWORD_RULES:
        for kw in keywords:
            if kw in name:
                return {"primary": muscle, "secondary": []}

    return {"primary": "Other", "secondary": []}


def get_primary_muscle(exercise_name):
    """Get just the primary muscle group for an exercise."""
    return get_muscle_info(exercise_name)["primary"]


def get_all_muscles_worked(exercise_name):
    """Get all muscles (primary + secondary) worked by an exercise."""
    info = get_muscle_info(exercise_name)
    return [info["primary"]] + info["secondary"]
