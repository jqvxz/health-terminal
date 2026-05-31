"""
HealthTerminal V1 — Nutrition Routes
Handles zero-cost API retrieval, aggressive caching, daily rate limiters,
and Nemotron AI performance scans.
"""

import json
import requests
import hashlib
from flask import Blueprint, request, jsonify
from config import Config
from models.db import (
    get_db, get_setting, get_nutrition_cache, set_nutrition_cache,
    get_nutrition_api_usage_today, increment_nutrition_api_usage,
    get_custom_foods, add_custom_food, delete_custom_food,
    get_recipes, add_recipe, delete_recipe, get_recipe_by_id,
    get_custom_food_by_id
)

nutrition_bp = Blueprint("nutrition", __name__)


def safe_float(val, default=0.0):
    """Safely convert a value to float."""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


@nutrition_bp.route("/api/nutrition/targets", methods=["GET"])
def get_dynamic_targets():
    """Calculate daily calorie and protein targets based on BMR + moderate daily activity + 5000 steps minimum + activities logged today."""
    try:
        from datetime import datetime
        from services.nutrition import get_macro_recommendations
        
        weight_val = get_setting("body_weight")
        weight_unit = get_setting("weight_unit") or "kg"

        try:
            weight = float(weight_val) if weight_val else 75.0
        except ValueError:
            weight = 75.0

        if weight_unit == "lbs":
            weight_kg = weight * 0.45359237
        else:
            weight_kg = weight

        # Today's activities
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        today_activity_calories = 0.0
        has_hevy = False
        has_run = False
        
        with get_db() as conn:
            rows = conn.execute(
                "SELECT calories, is_hevy, activity_type, moving_time, distance FROM activities WHERE substr(start_date_local, 1, 10) = ?",
                (today_str,)
            ).fetchall()
            for r in rows:
                c = r["calories"]
                is_hevy_act = r["is_hevy"]
                act_type = r["activity_type"]
                dur = r["moving_time"] or 0
                dist = r["distance"] or 0.0

                if c and c > 0:
                    today_activity_calories += float(c)
                elif is_hevy_act:
                    from services.nutrition import estimate_calories_lifting
                    today_activity_calories += estimate_calories_lifting(dur, weight_kg)
                elif act_type in ("Run", "VirtualRun", "TrailRun"):
                    from services.nutrition import estimate_calories_running
                    today_activity_calories += estimate_calories_running(dist, dur, weight_kg)
                else:
                    from services.nutrition import estimate_calories_general
                    today_activity_calories += estimate_calories_general(act_type, dur, weight_kg)

                if r["is_hevy"]:
                    has_hevy = True
                if r["activity_type"] in ("Run", "VirtualRun", "TrailRun"):
                    has_run = True

        # Determine dominant activity type
        dominant = "general"
        if has_hevy:
            dominant = "WeightTraining"
        elif has_run:
            dominant = "Run"

        macros = get_macro_recommendations(today_activity_calories, dominant, weight_kg)

        return jsonify({
            "calories": macros["total_calories"],
            "protein": macros["protein_g"],
            "carbs": macros["carbs_g"],
            "fats": macros["fat_g"],
            "bmr": macros["bmr"],
            "activity_offset": macros["activity_offset"],
            "steps_calories": macros["steps_calories"],
            "logged_activities_calories": round(today_activity_calories)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/barcode/<barcode>", methods=["GET"])
def get_barcode_product(barcode):
    """Retrieve product details from Open Food Facts using the barcode, checking cache first."""
    barcode = barcode.strip()
    if not barcode:
        return jsonify({"error": "Barcode is required"}), 400

    # 1. Check local cache
    cached = get_nutrition_cache(barcode)
    if cached:
        try:
            return jsonify(json.loads(cached))
        except Exception:
            pass

    # 2. Call Open Food Facts API (100% Free, no cost, preferred)
    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    try:
        resp = requests.get(url, headers={"User-Agent": "HealthTerminal - V1.0"}, timeout=15)
        if resp.status_code != 200:
            return jsonify({"error": f"Open Food Facts API error: {resp.status_code}"}), resp.status_code

        data = resp.json()
        if data.get("status") != 1 or "product" not in data:
            return jsonify({"error": "Product not found on Open Food Facts"}), 404

        product = data["product"]
        nutriments = product.get("nutriments", {})

        # Extract nutritional facts per 100g
        calories = nutriments.get("energy-kcal_100g")
        if calories is None:
            # Fallback
            energy_100g = nutriments.get("energy_100g", 0)
            calories = round(energy_100g / 4.184) if energy_100g else 0

        parsed_product = {
            "barcode": barcode,
            "name": product.get("product_name", "Unknown Product"),
            "brand": product.get("brands", "Generic"),
            "calories_100g": round(float(calories)) if calories is not None else 0,
            "protein_100g": round(float(nutriments.get("proteins_100g", 0)), 1),
            "carbs_100g": round(float(nutriments.get("carbohydrates_100g", 0)), 1),
            "fat_100g": round(float(nutriments.get("fat_100g", 0)), 1),
            "source": "openfoodfacts",
        }

        # 3. Cache the successful result
        set_nutrition_cache(barcode, "off", json.dumps(parsed_product))

        return jsonify(parsed_product)

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve barcode: {str(e)}"}), 500


@nutrition_bp.route("/api/nutrition/search", methods=["GET"])
def search_products():
    """Search products on Open Food Facts to return a selectable list, avoiding NLP queries."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    # Call Open Food Facts search API
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 24,
    }

    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "HealthTerminal - V1.0"}, timeout=15)
        if resp.status_code != 200:
            return jsonify([])

        data = resp.json()
        products = data.get("products", [])
        results = []

        for p in products:
            code = p.get("code")
            if not code:
                continue

            # Fallback parsing to ensure empty names or brands do not render as blank spaces
            prod_name = p.get("product_name") or p.get("product_name_en") or p.get("generic_name")
            if not prod_name or not prod_name.strip():
                prod_name = "Unknown Product"

            brand_name = p.get("brands")
            if not brand_name or not brand_name.strip():
                brand_name = "Generic"

            nutriments = p.get("nutriments", {})
            calories = nutriments.get("energy-kcal_100g")
            if calories is None:
                energy_100g = nutriments.get("energy_100g", 0)
                calories = round(energy_100g / 4.184) if energy_100g else 0

            results.append({
                "barcode": code,
                "name": prod_name,
                "brand": brand_name,
                "calories_100g": round(float(calories)) if calories is not None else 0,
                "protein_100g": round(float(nutriments.get("proteins_100g", 0)), 1),
                "carbs_100g": round(float(nutriments.get("carbohydrates_100g", 0)), 1),
                "fat_100g": round(float(nutriments.get("fat_100g", 0)), 1),
                "image_url": p.get("image_front_small_url", ""),
            })

        return jsonify(results)

    except Exception:
        return jsonify([])


def _search_off_scored(query, limit=8):
    """Search OFF and sort results by keyword relevance to the query.
    Applies strict relevance filtering to avoid returning completely unrelated products
    (e.g., returning a pizza product when searching for 'mozzarella').
    """
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 24,
    }
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "HealthTerminal - V1.0"}, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        products = data.get("products", [])
        results = []
        query_lower = query.lower().strip()
        query_words = set(query_lower.split())
        num_query_words = len(query_words)

        for p in products:
            code = p.get("code")
            if not code:
                continue

            prod_name = p.get("product_name") or p.get("product_name_en") or p.get("generic_name")
            if not prod_name or not prod_name.strip():
                prod_name = "Unknown Product"

            brand_name = p.get("brands")
            if not brand_name or not brand_name.strip():
                brand_name = "Generic"

            nutriments = p.get("nutriments", {})
            calories = nutriments.get("energy-kcal_100g")
            if calories is None:
                energy_100g = nutriments.get("energy_100g", 0)
                calories = round(energy_100g / 4.184) if energy_100g else 0

            cal_val = round(float(calories)) if calories else 0
            if cal_val == 0:
                continue

            name_lower = prod_name.lower()
            brand_lower = brand_name.lower()
            name_words = set(name_lower.split())

            # Count how many query words appear in the product name or brand
            name_hits = sum(1 for w in query_words if w in name_lower)
            brand_hits = sum(1 for w in query_words if w in brand_lower)
            total_hits = name_hits + brand_hits

            # FILTER: Require at least 50% of query words to appear somewhere
            if num_query_words > 0 and name_hits < max(1, num_query_words * 0.5):
                continue

            # Score: reward exact substring match, per-word name hits, penalize name bloat
            score = 0
            score += name_hits * 3
            score += brand_hits * 1

            # Big bonus for exact query appearing as a substring of the product name
            if query_lower in name_lower:
                score += 15

            # Bonus for short, focused product names (likely the actual ingredient, not a combo dish)
            # E.g., "Mozzarella" (1 word) should rank higher than "Pizza Jambon Mozzarella" (3 words)
            if len(name_words) <= num_query_words + 2:
                score += 5

            # Penalize products where the query words are a tiny fraction of the product name
            # (avoids "Picard Pizza N°6 Jambon Speck Roquette Mozzarella" matching "mozzarella")
            if len(name_words) > 0:
                coverage = name_hits / len(name_words)
                if coverage < 0.2:
                    score -= 5

            # Skip products with zero or negative relevance
            if score <= 0:
                continue

            results.append({
                "barcode": code,
                "name": prod_name,
                "brand": brand_name,
                "calories_100g": cal_val,
                "protein_100g": round(float(nutriments.get("proteins_100g", 0)), 1),
                "carbs_100g": round(float(nutriments.get("carbohydrates_100g", 0)), 1),
                "fat_100g": round(float(nutriments.get("fat_100g", 0)), 1),
                "_score": score,
            })

        results.sort(key=lambda x: -x["_score"])
        for r in results:
            r.pop("_score", None)

        return results[:limit]
    except Exception:
        return []


COMMON_FOODS = {
    # Proteins
    "chicken breast": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "unit_weight": 100.0},
    "chicken thigh": {"calories": 209, "protein": 26.0, "carbs": 0.0, "fat": 10.9, "unit_weight": 100.0},
    "chicken": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "unit_weight": 100.0},
    "beef": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "unit_weight": 100.0},
    "ground beef": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "unit_weight": 100.0},
    "steak": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "unit_weight": 100.0},
    "egg": {"calories": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "unit_weight": 50.0},
    "eggs": {"calories": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "unit_weight": 50.0},
    "salmon": {"calories": 208, "protein": 20.0, "carbs": 0.0, "fat": 13.0, "unit_weight": 100.0},
    "tuna": {"calories": 130, "protein": 28.0, "carbs": 0.0, "fat": 0.6, "unit_weight": 100.0},
    # Dairy / Cheese
    "mozzarella": {"calories": 280, "protein": 28.0, "carbs": 3.1, "fat": 17.0, "unit_weight": 100.0},
    "mozarella": {"calories": 280, "protein": 28.0, "carbs": 3.1, "fat": 17.0, "unit_weight": 100.0},
    "mozzarella cheese": {"calories": 280, "protein": 28.0, "carbs": 3.1, "fat": 17.0, "unit_weight": 100.0},
    "cheddar": {"calories": 403, "protein": 25.0, "carbs": 1.3, "fat": 33.0, "unit_weight": 100.0},
    "cheddar cheese": {"calories": 403, "protein": 25.0, "carbs": 1.3, "fat": 33.0, "unit_weight": 100.0},
    "parmesan": {"calories": 431, "protein": 38.0, "carbs": 4.1, "fat": 29.0, "unit_weight": 100.0},
    "cream cheese": {"calories": 342, "protein": 6.0, "carbs": 5.5, "fat": 34.0, "unit_weight": 100.0},
    "cottage cheese": {"calories": 98, "protein": 11.0, "carbs": 3.4, "fat": 4.3, "unit_weight": 100.0},
    "greek yogurt": {"calories": 97, "protein": 9.0, "carbs": 3.6, "fat": 5.0, "unit_weight": 100.0},
    "yogurt": {"calories": 59, "protein": 3.5, "carbs": 5.0, "fat": 3.3, "unit_weight": 100.0},
    # Grains / Carbs
    "oats": {"calories": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "unit_weight": 100.0},
    "oatmeal": {"calories": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "unit_weight": 100.0},
    "rice": {"calories": 130, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "unit_weight": 100.0},
    "white rice": {"calories": 130, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "unit_weight": 100.0},
    "brown rice": {"calories": 111, "protein": 2.6, "carbs": 23.0, "fat": 0.9, "unit_weight": 100.0},
    "pasta": {"calories": 131, "protein": 5.0, "carbs": 25.0, "fat": 1.1, "unit_weight": 100.0},
    "bread": {"calories": 265, "protein": 9.0, "carbs": 49.0, "fat": 3.2, "unit_weight": 100.0},
    "white bread": {"calories": 265, "protein": 9.0, "carbs": 49.0, "fat": 3.2, "unit_weight": 100.0},
    "whole wheat bread": {"calories": 247, "protein": 13.0, "carbs": 43.0, "fat": 3.4, "unit_weight": 100.0},
    "tortilla": {"calories": 312, "protein": 8.0, "carbs": 52.0, "fat": 8.0, "unit_weight": 100.0},
    # Milk
    "1.5% fat milk": {"calories": 47, "protein": 3.4, "carbs": 4.8, "fat": 1.5, "unit_weight": 100.0},
    "semi-skimmed milk": {"calories": 47, "protein": 3.4, "carbs": 4.8, "fat": 1.5, "unit_weight": 100.0},
    "whole milk": {"calories": 62, "protein": 3.2, "carbs": 4.6, "fat": 3.5, "unit_weight": 100.0},
    "skimmed milk": {"calories": 35, "protein": 3.4, "carbs": 5.0, "fat": 0.1, "unit_weight": 100.0},
    "milk": {"calories": 42, "protein": 3.4, "carbs": 5.0, "fat": 1.0, "unit_weight": 100.0},
    "almond milk": {"calories": 15, "protein": 0.6, "carbs": 0.3, "fat": 1.1, "unit_weight": 100.0},
    # Fats / Oils
    "butter": {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81.0, "unit_weight": 100.0},
    "olive oil": {"calories": 884, "protein": 0.0, "carbs": 0.0, "fat": 100.0, "unit_weight": 100.0},
    "coconut oil": {"calories": 862, "protein": 0.0, "carbs": 0.0, "fat": 100.0, "unit_weight": 100.0},
    "peanut butter": {"calories": 588, "protein": 25.0, "carbs": 20.0, "fat": 50.0, "unit_weight": 100.0},
    # Fruits
    "apple": {"calories": 52, "protein": 0.3, "carbs": 14.0, "fat": 0.2, "unit_weight": 100.0},
    "banana": {"calories": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "unit_weight": 100.0},
    "avocado": {"calories": 160, "protein": 2.0, "carbs": 9.0, "fat": 15.0, "unit_weight": 100.0},
    "strawberry": {"calories": 32, "protein": 0.7, "carbs": 7.7, "fat": 0.3, "unit_weight": 100.0},
    "strawberries": {"calories": 32, "protein": 0.7, "carbs": 7.7, "fat": 0.3, "unit_weight": 100.0},
    "blueberries": {"calories": 57, "protein": 0.7, "carbs": 14.5, "fat": 0.3, "unit_weight": 100.0},
    # Vegetables
    "broccoli": {"calories": 34, "protein": 2.8, "carbs": 7.0, "fat": 0.4, "unit_weight": 100.0},
    "spinach": {"calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4, "unit_weight": 100.0},
    "tomato": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2, "unit_weight": 100.0},
    "onion": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1, "unit_weight": 100.0},
    # Potato
    "potato": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "unit_weight": 100.0},
    "potatoes": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "unit_weight": 100.0},
    "sweet potato": {"calories": 86, "protein": 1.6, "carbs": 20.0, "fat": 0.1, "unit_weight": 100.0},
    "sweet potato fries": {"calories": 260, "protein": 2.6, "carbs": 37.0, "fat": 12.0, "unit_weight": 100.0},
    "french fries": {"calories": 312, "protein": 3.4, "carbs": 41.0, "fat": 15.0, "unit_weight": 100.0},
    "fries": {"calories": 312, "protein": 3.4, "carbs": 41.0, "fat": 15.0, "unit_weight": 100.0},
    # Supplements
    "whey": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "whey protein": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "protein powder": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "protein shake": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    # Nuts / Seeds
    "almonds": {"calories": 579, "protein": 21.0, "carbs": 22.0, "fat": 50.0, "unit_weight": 100.0},
    "peanuts": {"calories": 567, "protein": 26.0, "carbs": 16.0, "fat": 49.0, "unit_weight": 100.0},
    "walnuts": {"calories": 654, "protein": 15.0, "carbs": 14.0, "fat": 65.0, "unit_weight": 100.0},
}

def try_local_food_match(text):
    import re
    text_lower = text.lower().strip()
    
    # 1. Match eggs
    egg_match = re.search(r'(\d+)\s*(?:egg|eggs)\b', text_lower)
    if egg_match:
        count = float(egg_match.group(1))
        info = COMMON_FOODS["egg"]
        grams = count * info["unit_weight"]
        mult = grams / 100.0
        return {
            "name": f"{int(count)} eggs ({round(grams)}g)",
            "calories": round(info["calories"] * mult),
            "protein": round(info["protein"] * mult, 1),
            "carbs": round(info["carbs"] * mult, 1),
            "fat": round(info["fat"] * mult, 1),
            "source": "local_database",
        }
        
    # 2. Try generic grams or ml match
    qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|gram|grams|ml|milliliter|milliliters)\b', text_lower)
    grams = 100.0
    unit = "g"
    if qty_match:
        grams = float(qty_match.group(1))
        matched_unit = qty_match.group(0).lower()
        if 'ml' in matched_unit or 'milliliter' in matched_unit:
            unit = "ml"
        
    # Find matching food key — only accept if the key covers a significant portion
    # of the food-name text (strip leading quantity so we compare names to names).
    food_name_text = text_lower
    # Remove leading quantity expression to get just the food name part
    food_name_text = re.sub(r'^\d+(?:\.\d+)?\s*(?:g|gram|grams|ml|milliliter|milliliters)?\s*', '', food_name_text).strip()

    matched_key = None
    for key in sorted(COMMON_FOODS.keys(), key=len, reverse=True):
        if key in food_name_text:
            # Require the key to cover at least 80% of the food-name text length.
            # This prevents "sweet potato" (12) matching "sweet potato fries" (18).
            # Only exact or near-exact matches are accepted.
            if len(key) >= len(food_name_text) * 0.80:
                matched_key = key
                break

    if matched_key:
        info = COMMON_FOODS[matched_key]
        mult = grams / 100.0
        return {
            "name": f"{round(grams)}{unit} {matched_key}" if qty_match else f"{matched_key}",
            "calories": round(info["calories"] * mult),
            "protein": round(info["protein"] * mult, 1),
            "carbs": round(info["carbs"] * mult, 1),
            "fat": round(info["fat"] * mult, 1),
            "source": "local_database",
        }

    return None


def try_db_food_match(text):
    """
    Search SQLite custom_foods and recipes for a match.
    Extracts multiplier/portion quantity and scales macros.
    """
    import re
    text_lower = text.lower().strip()

    c_foods = get_custom_foods()
    recipes_list = get_recipes()

    all_db_items = []
    for f in c_foods:
        all_db_items.append({"id": f["id"], "name": f["name"].lower(), "type": "custom_food", "data": f})
    for r in recipes_list:
        all_db_items.append({"id": r["id"], "name": r["name"].lower(), "type": "recipe", "data": r})

    all_db_items.sort(key=lambda x: len(x["name"]), reverse=True)

    qty = None
    unit = None
    remainder = text_lower

    lead_qty_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:g|gram|grams|ml|milliliter|milliliters|serving|servings|x)?\b\s*(.*)$', text_lower)
    if lead_qty_match:
        val_str = lead_qty_match.group(1)
        cand = lead_qty_match.group(2).strip()
        for item in all_db_items:
            if item["name"] == cand or cand.startswith(item["name"]):
                qty = float(val_str)
                full_match = lead_qty_match.group(0)
                unit_part = full_match[:len(full_match) - len(cand)].strip()
                if 'g' in unit_part or 'gram' in unit_part:
                    unit = 'g'
                elif 'ml' in unit_part or 'milliliter' in unit_part:
                    unit = 'ml'
                else:
                    unit = 'serving'
                remainder = item["name"]
                break

    matched_item = None
    if qty is None:
        for item in all_db_items:
            if item["name"] in text_lower:
                matched_item = item
                remainder = item["name"]
                qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|gram|grams|ml|milliliter|milliliters|serving|servings|x)?\b', text_lower)
                if qty_match:
                    qty = float(qty_match.group(1))
                    matched_unit = qty_match.group(0).lower()
                    if 'g' in matched_unit or 'gram' in matched_unit:
                        unit = 'g'
                    elif 'ml' in matched_unit or 'milliliter' in matched_unit:
                        unit = 'ml'
                    else:
                        unit = 'serving'
                break
    else:
        for item in all_db_items:
            if item["name"] == remainder:
                matched_item = item
                break

    if matched_item:
        f_data = matched_item["data"]
        item_type = matched_item["type"]

        factor = 1.0
        if qty is not None:
            if item_type == "custom_food":
                serving_size = float(f_data.get("serving_size") or 100.0)
                if unit in ('g', 'ml'):
                    factor = qty / serving_size
                else:
                    factor = qty
            else:
                factor = qty

        scaled_qty = qty if qty is not None else (f_data.get("serving_size") if item_type == "custom_food" else 1.0)
        display_unit = unit if unit is not None else (f_data.get("serving_unit") if item_type == "custom_food" else "serving")
        formatted_name = f"{round(scaled_qty)}{display_unit} {f_data['name']}"

        return {
            "name": formatted_name,
            "calories": round(float(f_data["calories"]) * factor),
            "protein": round(float(f_data["protein"]) * factor, 1),
            "carbs": round(float(f_data["carbs"]) * factor, 1),
            "fat": round(float(f_data["fat"]) * factor, 1),
            "source": item_type,
            "db_id": f_data["id"]
        }

    return None




def try_off_fallback_only(text):
    """Query Open Food Facts search API for a single product as a zero-cost fallback."""
    import re
    # Extract grams/ml/eggs
    grams = 100.0
    qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|gram|grams|ml|milliliter|milliliters)\b', text.lower())
    if qty_match:
        grams = float(qty_match.group(1))
    else:
        egg_match = re.search(r'(\d+)\s*(?:egg|eggs)\b', text.lower())
        if egg_match:
            grams = float(egg_match.group(1)) * 50.0

    search_query = re.sub(r'\d+(?:\.\d+)?\s*(?:g|gram|grams|ml|milliliter|milliliters|egg|eggs)\b', '', text, flags=re.IGNORECASE).strip()
    search_query = re.sub(r'[\(\)]', '', search_query).strip()  # remove parentheses
    if not search_query:
        search_query = text

    off_url = "https://world.openfoodfacts.org/cgi/search.pl"
    off_params = {
        "search_terms": search_query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 3,
    }
    try:
        off_resp = requests.get(off_url, params=off_params, headers={"User-Agent": "HealthTerminal - V1.0"}, timeout=10)
        if off_resp.status_code == 200:
            off_data = off_resp.json()
            off_products = off_data.get("products", [])
            if off_products:
                first_p = off_products[0]
                nutriments = first_p.get("nutriments", {})
                
                c_100 = nutriments.get("energy-kcal_100g")
                if c_100 is None:
                    e_100 = nutriments.get("energy_100g", 0)
                    c_100 = round(e_100 / 4.184) if e_100 else 0
                    
                p_100 = float(nutriments.get("proteins_100g", 0))
                carb_100 = float(nutriments.get("carbohydrates_100g", 0))
                f_100 = float(nutriments.get("fat_100g", 0))
                
                mult = grams / 100.0
                
                p_name = first_p.get("product_name") or first_p.get("product_name_en") or first_p.get("generic_name") or search_query
                brand = first_p.get("brands")
                full_name = f"{brand} {p_name}" if brand else p_name
                
                unit = "ml" if "ml" in text.lower() or "milliliter" in text.lower() else "g"
                formatted_qty = f"{int(grams / 50)} eggs" if "egg" in text.lower() else f"{round(grams)}{unit}"
                
                return {
                    "name": f"{formatted_qty} {full_name}",
                    "calories": round(c_100 * mult),
                    "protein": round(p_100 * mult, 1),
                    "carbs": round(carb_100 * mult, 1),
                    "fat": round(f_100 * mult, 1),
                    "source": "openfoodfacts_fallback",
                }
    except Exception:
        pass
    return None


def parse_single_ingredient(text):
    """Parse a single ingredient, using local database, cache, or API Ninjas / OFF fallback."""
    import re
    normalized_query = text.lower().strip()

    # 1. Check custom foods and recipes database match (highest priority)
    db_match = try_db_food_match(text)
    if db_match:
        return db_match

    # 2. Check local database FIRST (always accurate, free, instant)
    local_match = try_local_food_match(text)
    if local_match:
        set_nutrition_cache(normalized_query, "local", json.dumps(local_match))
        return local_match

    # 2. Check local cache (for API results; reject stale entries with 0 calories)
    cached = get_nutrition_cache(normalized_query)
    if cached:
        try:
            cached_data = json.loads(cached)
            if cached_data.get("calories", 0) > 0:
                return cached_data
        except Exception:
            pass

    # 3. Check daily call limit (e.g. 800 free calls)
    usage = get_nutrition_api_usage_today()
    if usage >= 800:
        return {
            "name": text,
            "calories": 0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "source": "limit_reached_placeholder",
            "error": "Daily limit reached. Please search directly."
        }

    # 4. Retrieve API Key
    api_key = get_setting("apininjas_api_key")
    if not api_key:
        off_fallback = try_off_fallback_only(text)
        if off_fallback:
            set_nutrition_cache(normalized_query, "off_fallback", json.dumps(off_fallback))
            return off_fallback
        return {
            "name": text,
            "calories": 0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "source": "missing_api_key_placeholder",
            "error": "API Ninjas API Key not configured."
        }

    # 5. Call API Ninjas Nutrition endpoint
    url = "https://api.api-ninjas.com/v1/nutrition"
    headers = {"X-Api-Key": api_key}
    params = {"query": text}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            off_fallback = try_off_fallback_only(text)
            if off_fallback:
                set_nutrition_cache(normalized_query, "off_fallback", json.dumps(off_fallback))
                return off_fallback
            return {
                "name": text,
                "calories": 0,
                "protein": 0.0,
                "carbs": 0.0,
                "fat": 0.0,
                "source": "api_error_placeholder"
            }

        items = resp.json()
        if not items:
            off_fallback = try_off_fallback_only(text)
            if off_fallback:
                set_nutrition_cache(normalized_query, "off_fallback", json.dumps(off_fallback))
                return off_fallback
            return {
                "name": text,
                "calories": 0,
                "protein": 0.0,
                "carbs": 0.0,
                "fat": 0.0,
                "source": "not_found_placeholder"
            }

        # Aggregate nutrients across all parsed ingredients
        total_calories = 0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        ingredients_list = []

        for item in items:
            c = safe_float(item.get("calories"))
            p = safe_float(item.get("protein_g"))
            carb = safe_float(item.get("carbohydrates_total_g"))
            f = safe_float(item.get("fat_total_g"))

            total_calories += c
            total_protein += p
            total_carbs += carb
            total_fat += f
            ingredients_list.append(f"{safe_float(item.get('serving_size_g', 0))}g {item.get('name')}")

        if total_calories == 0 and total_protein == 0:
            off_fallback = try_off_fallback_only(text)
            if off_fallback:
                set_nutrition_cache(normalized_query, "off_fallback", json.dumps(off_fallback))
                return off_fallback

        parsed_analysis = {
            "name": ", ".join(ingredients_list) if ingredients_list else text,
            "calories": round(total_calories),
            "protein": round(total_protein, 1),
            "carbs": round(total_carbs, 1),
            "fat": round(total_fat, 1),
            "source": "apininjas",
        }

        # Cache result and increment usage
        set_nutrition_cache(normalized_query, "apininjas", json.dumps(parsed_analysis))
        increment_nutrition_api_usage()
        return parsed_analysis

    except Exception:
        off_fallback = try_off_fallback_only(text)
        if off_fallback:
            set_nutrition_cache(normalized_query, "off_fallback", json.dumps(off_fallback))
            return off_fallback
        return {
            "name": text,
            "calories": 0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "source": "error_placeholder"
        }


@nutrition_bp.route("/api/nutrition/analyze", methods=["POST"])
def analyze_generic_ingredients():
    """Analyze generic text inputs (supporting single or comma/and-separated compound inputs)."""
    import re
    body = request.json or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Ingredients description is required"}), 400

    normalized_query = text.lower().strip()

    # 1. Check local cache first for the exact query
    cached = get_nutrition_cache(normalized_query)
    if cached:
        try:
            return jsonify(json.loads(cached))
        except Exception:
            pass

    # Split by comma or "and" word boundaries
    parts = re.split(r',|\band\b', text, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return jsonify({"error": "Ingredients description is required"}), 400

    if len(parts) == 1:
        # Single ingredient parsing
        res = parse_single_ingredient(parts[0])
        if "error" in res and res.get("source") in ["missing_api_key_placeholder", "limit_reached_placeholder"]:
            return jsonify({"error": res["error"]}), 400 if "key" in res["source"] else 429
        return jsonify(res)

    # Multi-item compound query parsing
    parsed_items = []
    total_calories = 0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    for part in parts:
        item_res = parse_single_ingredient(part)
        parsed_items.append(item_res)
        total_calories += item_res.get("calories", 0)
        total_protein += item_res.get("protein", 0.0)
        total_carbs += item_res.get("carbs", 0.0)
        total_fat += item_res.get("fat", 0.0)

    combined_result = {
        "name": text,
        "calories": round(total_calories),
        "protein": round(total_protein, 1),
        "carbs": round(total_carbs, 1),
        "fat": round(total_fat, 1),
        "source": "compound_query",
        "items": parsed_items
    }

    # Cache compound query
    set_nutrition_cache(normalized_query, "compound", json.dumps(combined_result))
    return jsonify(combined_result)


@nutrition_bp.route("/api/nutrition/smart-search", methods=["POST"])
def smart_search():
    """Unified search combining structured AI query translation, local DB matching, API Ninjas and OFF alternatives."""
    import re
    body = request.json or {}
    query = body.get("query", "").strip()
    if not query:
        return jsonify({"error": "Search query is required"}), 400

    api_key = get_setting("openrouter_api_key") or Config.OPENROUTER_API_KEY
    parsed_items = []
    translated_query = ""

    # 1. Attempt structured AI query translation and splitting
    if api_key:
        try:
            translation_system_prompt = (
                "You are an elite, highly precise nutrition parser. Your task is to split a natural language description "
                "of a meal into its INDIVIDUAL distinct ingredients/food items, and format each into a clean portion-based "
                "description (e.g. '200ml milk', '30g protein powder', '150g chicken breast').\n\n"
                "SPLITTING RULES (CRITICAL):\n"
                "- Split on 'and', 'with', '+', commas, and similar connectors that separate DISTINCT ingredients.\n"
                "- 'sweet potato fries with mozzarella cheese and chicken' -> THREE separate items: 'sweet potato fries', 'mozzarella cheese', 'chicken'.\n"
                "- 'oats with milk' -> TWO items: 'oats', 'milk'.\n"
                "- Do NOT keep compound phrases like 'X with Y' as a single item unless they form an inseparable dish name (e.g., 'mac and cheese', 'bread and butter').\n\n"
                "PORTION ESTIMATION (CRITICAL):\n"
                "- If a portion is not specified, ALWAYS estimate a realistic portion based on standard serving sizes.\n"
                "  Examples: 'chicken' -> '150g chicken breast', 'some protein powder' -> '30g protein powder', \n"
                "  'eggs' -> '2 eggs', 'an apple' -> '1 medium apple (182g)', 'sweet potato fries' -> '150g sweet potato fries'.\n"
                "- Never default to 100g for everything — use realistic context-aware portions.\n\n"
                "You MUST return a JSON array of objects, where each object has exactly the following keys:\n"
                "- 'query': The clean descriptive name of the food item (e.g. 'milk', 'protein powder', 'chicken breast')\n"
                "- 'formatted_query': The portioned name of the item (e.g. '200ml milk', '30g protein powder', '150g chicken breast')\n"
                "- 'quantity': The portion weight or count as a number (e.g. 200.0, 30.0, 150.0)\n"
                "- 'unit': The unit of portion, typically 'g', 'ml', or 'serving' (e.g. 'ml', 'g')\n"
                "- 'calories': Estimated calories for THIS portion as an integer\n"
                "- 'protein': Estimated protein in grams for THIS portion as a float\n"
                "- 'carbs': Estimated carbs in grams for THIS portion as a float\n"
                "- 'fat': Estimated fat in grams for THIS portion as a float\n\n"
                "CRITICAL OUTPUT REQUIREMENT:\n"
                "Output ONLY a raw JSON array. DO NOT include any introductory text, markdown code blocks, backticks, or other formatting. "
                "The response must parse successfully with json.loads()."
            )
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": Config.BASE_URL,
                "X-Title": "HealthTerminal",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "google/gemini-2.5-flash:free",
                "messages": [
                    {"role": "system", "content": translation_system_prompt},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 500,
                "temperature": 0.0,
            }
            resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=12)
            if resp.status_code != 200:
                payload["model"] = "meta-llama/llama-3.1-8b-instruct:free"
                resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=12)

            if resp.status_code == 200:
                resp_json = resp.json()
                if "choices" in resp_json and len(resp_json["choices"]) > 0:
                    ai_output = resp_json["choices"][0]["message"]["content"].strip()
                    if ai_output.startswith("```"):
                        lines = ai_output.split("\n")
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        ai_output = "\n".join(lines).strip()
                    
                    parsed_items = json.loads(ai_output)
                    translated_query = ", ".join(item.get("formatted_query", "") or f"{item.get('quantity')}{item.get('unit')} {item.get('query')}" for item in parsed_items)
        except Exception as e:
            print(f"JSON AI query parsing failed: {e}")

    results = []

    # 2. Process AI parsed items if successful
    if parsed_items:
        for item in parsed_items:
            food_name = item.get("query", "").strip()
            formatted_query = item.get("formatted_query", "").strip() or f"{item.get('quantity', 100.0)}{item.get('unit', 'g')} {food_name}"
            quantity = float(item.get("quantity", 100.0))
            unit = item.get("unit", "g")

            # Seek help through the local DB / calorie tracker API pipeline!
            recommended = parse_single_ingredient(formatted_query)

            # Build AI fallback estimate values
            ai_calories = round(float(item.get("calories", 0)))
            ai_protein = round(float(item.get("protein", 0.0)), 1)
            ai_carbs = round(float(item.get("carbs", 0.0)), 1)
            ai_fat = round(float(item.get("fat", 0.0)), 1)
            ai_has_data = ai_calories > 0 or ai_protein > 0

            # Fall back to AI estimation if:
            # a) parse returned nothing / zero macros, OR
            # b) local_database returned a partial-name match where the matched food
            #    name does not contain the full food_name the AI identified AND the AI
            #    has real macro estimates (prevents 'sweet potato' matching 'sweet potato
            #    fries with mozzarella cheese' from overriding AI's richer estimate).
            local_partial = (
                recommended
                and recommended.get("source") == "local_database"
                and food_name.lower() not in recommended.get("name", "").lower()
                and ai_has_data
            )

            if not recommended or (recommended.get("calories", 0) == 0 and recommended.get("protein", 0) == 0) or local_partial:
                recommended = {
                    "name": formatted_query,
                    "calories": ai_calories,
                    "protein": ai_protein,
                    "carbs": ai_carbs,
                    "fat": ai_fat,
                    "source": "ai_estimation"
                }

            # Fetch branded product alternatives from Open Food Facts using the clean query name
            alternatives = _search_off_scored(food_name, limit=6)

            # Filter out alternatives duplicate
            if alternatives and recommended and recommended.get("source") == "openfoodfacts":
                if alternatives[0]["name"].lower() in recommended["name"].lower():
                    alternatives = alternatives[1:]

            results.append({
                "query": food_name,
                "recommended": recommended,
                "alternatives": alternatives,
                "quantity": quantity,
                "unit": unit
            })

    # 3. Fallback to classic keyword parsing if AI parsing failed or returned empty
    if not results:
        # Split by comma or "and" word boundaries
        parts = [p.strip() for p in re.split(r',|\band\b', query, flags=re.IGNORECASE) if p.strip()]
        for part in parts:
            part_lower = part.lower().strip()

            # Parse quantity from query part
            qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|gram|grams|ml|milliliter|milliliters)\b', part_lower)
            quantity = float(qty_match.group(1)) if qty_match else 100.0
            unit = "g"
            if qty_match:
                matched = qty_match.group(0).lower()
                if 'ml' in matched or 'milliliter' in matched:
                    unit = "ml"

            # Extract clean food name (without quantity)
            food_name = re.sub(r'\d+(?:\.\d+)?\s*(?:g|gram|grams|ml|milliliter|milliliters)\b', '', part, flags=re.IGNORECASE).strip()
            food_name = re.sub(r'[()]', '', food_name).strip()
            if not food_name:
                food_name = part

            recommended = parse_single_ingredient(part)

            # Open Food Facts alternatives
            alternatives = _search_off_scored(food_name, limit=6)

            # Promoted best alternative if no recommended
            if not recommended and alternatives:
                best = alternatives[0]
                factor = quantity / 100.0
                recommended = {
                    "name": f"{round(quantity)}{unit} {best['name']}",
                    "calories": round(best["calories_100g"] * factor),
                    "protein": round(best["protein_100g"] * factor, 1),
                    "carbs": round(best["carbs_100g"] * factor, 1),
                    "fat": round(best["fat_100g"] * factor, 1),
                    "source": "openfoodfacts",
                }
                alternatives = alternatives[1:]

            results.append({
                "query": food_name,
                "recommended": recommended,
                "alternatives": alternatives,
                "quantity": quantity,
                "unit": unit
            })

    return jsonify({
        "results": results,
        "parsed_query": translated_query or query
    })


@nutrition_bp.route("/api/nutrition/health-scan", methods=["POST"])
def conduct_ai_health_scan():
    """Conduct a metabolic and training health scan using active OpenRouter Nemotron AI based on the user's daily food log."""
    api_key = get_setting("openrouter_api_key") or Config.OPENROUTER_API_KEY
    if not api_key:
        return jsonify({"error": "OpenRouter API Key not configured. Please add it in Settings to run AI Scans."}), 400

    body = request.json or {}
    foods = body.get("foods", [])

    # Build context from user profile
    weight = get_setting("body_weight")
    height = get_setting("user_height")
    age = get_setting("user_age")
    sex = get_setting("user_sex")
    weight_unit = get_setting("weight_unit") or "kg"

    profile_parts = []
    if weight: profile_parts.append(f"Weight: {weight}{weight_unit}")
    if height: profile_parts.append(f"Height: {height}cm")
    if age: profile_parts.append(f"Age: {age}")
    if sex: profile_parts.append(f"Sex: {sex}")
    profile_str = ", ".join(profile_parts) if profile_parts else "Not provided"

    # Format food list
    if not foods:
        return jsonify({"error": "Daily log is empty. Log some food entries before conducting an AI Scan."}), 400

    food_lines = []
    total_cal = 0
    total_prot = 0
    total_carb = 0
    total_fat = 0

    for f in foods:
        food_lines.append(f"- {f.get('name')} | {f.get('cal')} kcal | P: {f.get('prot')}g | C: {f.get('carb')}g | F: {f.get('fat')}g")
        total_cal += float(f.get('cal', 0))
        total_prot += float(f.get('prot', 0))
        total_carb += float(f.get('carb', 0))
        total_fat += float(f.get('fat', 0))

    food_str = "\n".join(food_lines)

    # Mifflin-St Jeor Formula Context (calculated if possible to assist the model)
    bmr_str = ""
    if weight and height and age and sex:
        try:
            w = float(weight)
            if weight_unit == "lbs":
                w = w * 0.45359237
            h = float(height)
            a = float(age)
            if sex.lower() == "male":
                bmr = 10 * w + 6.25 * h - 5 * a + 5
            else:
                bmr = 10 * w + 6.25 * h - 5 * a - 161
            bmr_str = f"Calculated Mifflin-St Jeor BMR: {round(bmr)} kcal"
        except Exception:
            pass

    # Craft instructions prompt for Nemotron
    scan_prompt = f"""
### User Profile:
{profile_str}
{bmr_str}

### Daily Food Log:
{food_str}
TOTALS: {round(total_cal)} kcal | Protein: {round(total_prot)}g | Carbs: {round(total_carb)}g | Fat: {round(total_fat)}g

---
Please perform a high-performance, biological metabolic health scan on this daily fuel log.
Evaluate the nutrition based on these strict guidelines:
1. Saturated fats and high-bioavailability protein from clean animal sources (e.g. grass-fed steak, pastured eggs, raw A2 dairy) are elite fuels.
2. Refined seed/vegetable oils (canola, sunflower, soybean, corn oil etc.) are toxic, highly inflammatory, and must be strictly flagged if suspected or logged.
3. Vegan/vegetarian limits and soy-based dairy alternatives are inferior and must be discouraged.
4. Dietary cholesterol from clean foods is safe and critical for anabolic hormone synthesis.
5. Mifflin-St Jeor calorie calculations and protein density should align with weight goals.

FORMATTING REQUIREMENTS:
1. Provide a definitive Letter Grade (e.g. "A+", "B-", "D+") based strictly on fuel quality.
2. Highlight a clear summary assessment.
3. List any specific warnings (especially seed oil risks, soy content, or low bioavailability).
4. Outline actionable optimization steps.
5. NEVER use emojis or LaTeX math formatting. Keep it clean and highly technical.
"""

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
                {"role": "user", "content": scan_prompt},
            ],
            "max_tokens": 1500,
        }

        resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            return jsonify({"error": f"OpenRouter API error: {resp.status_code}"}), resp.status_code

        result_data = resp.json()
        ai_response = result_data["choices"][0]["message"]["content"]

        # Parse a grade from response (simple heuristic)
        grade = "A"
        for potential_grade in ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F"]:
            if potential_grade in ai_response[:100] or f"Grade: {potential_grade}" in ai_response or f"Grade {potential_grade}" in ai_response:
                grade = potential_grade
                break

        return jsonify({
            "grade": grade,
            "analysis": ai_response,
            "totals": {
                "calories": round(total_cal),
                "protein": round(total_prot),
                "carbs": round(total_carb),
                "fat": round(total_fat)
            }
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "AI Scan request timed out. Please try again."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/log", methods=["GET"])
def get_daily_food_log():
    """Retrieve logged food entries for a specific date or date range."""
    from datetime import date
    target_date = request.args.get("date", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    with get_db() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT * FROM daily_food_log WHERE log_date >= ? AND log_date <= ? ORDER BY log_date, log_time, id",
                (start_date, end_date)
            ).fetchall()
        else:
            if not target_date:
                target_date = date.today().isoformat()
            rows = conn.execute(
                "SELECT * FROM daily_food_log WHERE log_date = ? ORDER BY log_time, id",
                (target_date,)
            ).fetchall()

        return jsonify([dict(row) for row in rows])


@nutrition_bp.route("/api/nutrition/log", methods=["POST"])
def add_food_log():
    """Log a food item into the database."""
    from datetime import datetime, date
    body = request.json or {}
    name = body.get("name", "").strip()
    calories = safe_float(body.get("calories"))
    protein = safe_float(body.get("protein"))
    carbs = safe_float(body.get("carbs"))
    fat = safe_float(body.get("fat"))
    tag = body.get("tag", "").strip()
    log_date = body.get("date", "").strip()
    log_time = body.get("time", "").strip()

    if not name:
        return jsonify({"error": "Food name is required"}), 400

    if not log_date:
        log_date = date.today().isoformat()
    if not log_time:
        log_time = datetime.now().strftime("%H:%M")

    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO daily_food_log (log_date, log_time, name, calories, protein, carbs, fat, tag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_date, log_time, name, calories, protein, carbs, fat, tag)
        )
        log_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM daily_food_log WHERE id = ?", (log_id,)).fetchone()
        return jsonify(dict(row)), 201


@nutrition_bp.route("/api/nutrition/log/<int:log_id>", methods=["DELETE"])
def delete_food_log(log_id):
    """Delete a logged food entry."""
    with get_db() as conn:
        conn.execute("DELETE FROM daily_food_log WHERE id = ?", (log_id,))
        return jsonify({"success": True})


@nutrition_bp.route("/api/nutrition/log/clear", methods=["POST"])
def clear_food_log():
    """Clear all logged food entries for a target date."""
    from datetime import date
    body = request.json or {}
    target_date = body.get("date", "").strip()
    if not target_date:
        target_date = date.today().isoformat()

    with get_db() as conn:
        conn.execute("DELETE FROM daily_food_log WHERE log_date = ?", (target_date,))
        return jsonify({"success": True})


# === CUSTOM FOODS & RECIPES CRUD ===

@nutrition_bp.route("/api/nutrition/custom-foods", methods=["GET"])
def api_get_custom_foods():
    """Retrieve all saved custom foods."""
    try:
        foods = get_custom_foods()
        return jsonify(foods)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/custom-foods", methods=["POST"])
def api_add_custom_food():
    """Add a new custom food."""
    body = request.json or {}
    name = body.get("name", "").strip()
    calories = safe_float(body.get("calories"))
    protein = safe_float(body.get("protein"))
    carbs = safe_float(body.get("carbs"))
    fat = safe_float(body.get("fat"))
    serving_size = safe_float(body.get("serving_size"), 100.0)
    serving_unit = body.get("serving_unit", "g").strip()

    if not name:
        return jsonify({"error": "Food name is required"}), 400

    try:
        food_id = add_custom_food(name, calories, protein, carbs, fat, serving_size, serving_unit)
        new_food = get_custom_food_by_id(food_id)
        return jsonify(new_food), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/custom-foods/<int:food_id>", methods=["DELETE"])
def api_delete_custom_food(food_id):
    """Delete a custom food."""
    try:
        delete_custom_food(food_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/recipes", methods=["GET"])
def api_get_recipes():
    """Retrieve all saved recipes."""
    try:
        recipes_list = get_recipes()
        return jsonify(recipes_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/recipes", methods=["POST"])
def api_add_recipe():
    """Add a new recipe."""
    body = request.json or {}
    name = body.get("name", "").strip()
    calories = safe_float(body.get("calories"))
    protein = safe_float(body.get("protein"))
    carbs = safe_float(body.get("carbs"))
    fat = safe_float(body.get("fat"))
    instructions = body.get("instructions", "").strip()
    ingredients = body.get("ingredients", "").strip()

    if not name:
        return jsonify({"error": "Recipe name is required"}), 400

    try:
        recipe_id = add_recipe(name, calories, protein, carbs, fat, instructions, ingredients)
        new_recipe = get_recipe_by_id(recipe_id)
        return jsonify(new_recipe), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/recipes/<int:recipe_id>", methods=["DELETE"])
def api_delete_recipe(recipe_id):
    """Delete a recipe."""
    try:
        delete_recipe(recipe_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@nutrition_bp.route("/api/nutrition/recipes/estimate-macros", methods=["POST"])
def api_estimate_recipe_macros():
    """Estimate macros for a recipe name/ingredients using a fast free OpenRouter model."""
    body = request.json or {}
    ingredients = body.get("ingredients", "").strip()
    recipe_name = body.get("name", "").strip()

    if not ingredients:
        return jsonify({"error": "Ingredients description is required"}), 400

    api_key = get_setting("openrouter_api_key") or Config.OPENROUTER_API_KEY
    if not api_key:
        return jsonify({"error": "OpenRouter API Key not configured. Please add it in Settings."}), 400

    prompt = f"""
    You are an elite, highly precise nutrition parser. Estimate the sum total macronutrients (calories, protein, carbs, fat) 
    for the following recipe/meal ingredients:
    
    Recipe Name: {recipe_name}
    Ingredients: {ingredients}
    
    CRITICAL OUTPUT REQUIREMENT:
    You MUST return exactly a JSON object (no markdown, no backticks, no other text) with the following fields:
    - 'calories': Sum total calories as an integer (e.g. 450)
    - 'protein': Sum total protein in grams as a float/number (e.g. 32.5)
    - 'carbs': Sum total carbs in grams as a float/number (e.g. 45.0)
    - 'fat': Sum total fat in grams as a float/number (e.g. 12.0)
    
    Ensure it is valid JSON and parses successfully with json.loads().
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": Config.BASE_URL,
        "X-Title": "HealthTerminal",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "google/gemini-2.5-flash:free",
        "messages": [
            {"role": "system", "content": "You are a precise nutrition database formatter. Respond ONLY with a raw JSON object."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }

    try:
        resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            payload["model"] = "meta-llama/llama-3.1-8b-instruct:free"
            resp = requests.post(Config.OPENROUTER_API_URL, headers=headers, json=payload, timeout=15)

        if resp.status_code != 200:
            return jsonify({"error": f"OpenRouter API error: {resp.status_code}"}), resp.status_code

        resp_json = resp.json()
        ai_output = resp_json["choices"][0]["message"]["content"].strip()
        
        if ai_output.startswith("```"):
            lines = ai_output.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            ai_output = "\n".join(lines).strip()

        parsed_macros = json.loads(ai_output)
        return jsonify({
            "calories": round(safe_float(parsed_macros.get("calories"))),
            "protein": round(safe_float(parsed_macros.get("protein")), 1),
            "carbs": round(safe_float(parsed_macros.get("carbs")), 1),
            "fat": round(safe_float(parsed_macros.get("fat")), 1)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to estimate recipe macros: {str(e)}"}), 500

