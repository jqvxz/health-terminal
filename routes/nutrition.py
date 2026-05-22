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
    get_nutrition_api_usage_today, increment_nutrition_api_usage
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
    """Search OFF and sort results by keyword relevance to the query."""
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
        query_words = set(query.lower().split())

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
            score = 0
            for w in query_words:
                if w in name_lower:
                    score += 3
                elif w in brand_lower:
                    score += 1
            if query.lower() in name_lower:
                score += 10

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
    "chicken breast": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "unit_weight": 100.0},
    "chicken": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "unit_weight": 100.0},
    "beef": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "unit_weight": 100.0},
    "steak": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0, "unit_weight": 100.0},
    "egg": {"calories": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "unit_weight": 50.0},
    "eggs": {"calories": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "unit_weight": 50.0},
    "oats": {"calories": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "unit_weight": 100.0},
    "oatmeal": {"calories": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "unit_weight": 100.0},
    "rice": {"calories": 130, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "unit_weight": 100.0},
    "white rice": {"calories": 130, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "unit_weight": 100.0},
    "brown rice": {"calories": 111, "protein": 2.6, "carbs": 23.0, "fat": 0.9, "unit_weight": 100.0},
    "1.5% fat milk": {"calories": 47, "protein": 3.4, "carbs": 4.8, "fat": 1.5, "unit_weight": 100.0},
    "semi-skimmed milk": {"calories": 47, "protein": 3.4, "carbs": 4.8, "fat": 1.5, "unit_weight": 100.0},
    "whole milk": {"calories": 62, "protein": 3.2, "carbs": 4.6, "fat": 3.5, "unit_weight": 100.0},
    "skimmed milk": {"calories": 35, "protein": 3.4, "carbs": 5.0, "fat": 0.1, "unit_weight": 100.0},
    "milk": {"calories": 42, "protein": 3.4, "carbs": 5.0, "fat": 1.0, "unit_weight": 100.0},
    "butter": {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81.0, "unit_weight": 100.0},
    "apple": {"calories": 52, "protein": 0.3, "carbs": 14.0, "fat": 0.2, "unit_weight": 100.0},
    "banana": {"calories": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "unit_weight": 100.0},
    "broccoli": {"calories": 34, "protein": 2.8, "carbs": 7.0, "fat": 0.4, "unit_weight": 100.0},
    "salmon": {"calories": 208, "protein": 20.0, "carbs": 0.0, "fat": 13.0, "unit_weight": 100.0},
    "tuna": {"calories": 130, "protein": 28.0, "carbs": 0.0, "fat": 0.6, "unit_weight": 100.0},
    "potato": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "unit_weight": 100.0},
    "potatoes": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "unit_weight": 100.0},
    "sweet potato": {"calories": 86, "protein": 1.6, "carbs": 20.0, "fat": 0.1, "unit_weight": 100.0},
    "whey": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "whey protein": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "protein powder": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "protein shake": {"calories": 380, "protein": 80.0, "carbs": 6.0, "fat": 3.0, "unit_weight": 100.0},
    "olive oil": {"calories": 884, "protein": 0.0, "carbs": 0.0, "fat": 100.0, "unit_weight": 100.0},
    "avocado": {"calories": 160, "protein": 2.0, "carbs": 9.0, "fat": 15.0, "unit_weight": 100.0},
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
        
    # Find matching food key
    matched_key = None
    for key in sorted(COMMON_FOODS.keys(), key=len, reverse=True):
        if key in text_lower:
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

    # 1. Check local database FIRST (always accurate, free, instant)
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
    """Unified search combining local DB, API Ninjas, and Open Food Facts with relevance scoring."""
    import re
    body = request.json or {}
    query = body.get("query", "").strip()
    if not query:
        return jsonify({"error": "Search query is required"}), 400

    parts = [p.strip() for p in query.split(",") if p.strip()]
    results = []

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

        # Extract clean food name (without quantity) for OFF search
        food_name = re.sub(r'\d+(?:\.\d+)?\s*(?:g|gram|grams|ml|milliliter|milliliters)\b', '', part, flags=re.IGNORECASE).strip()
        food_name = re.sub(r'[()]', '', food_name).strip()
        if not food_name:
            food_name = part

        recommended = None

        # 1. Local COMMON_FOODS (instant, free, highest priority)
        local_match = try_local_food_match(part)
        if local_match:
            recommended = local_match

        # 2. Check cache for valid result (cal > 0)
        if not recommended:
            cached = get_nutrition_cache(part_lower)
            if cached:
                try:
                    cached_data = json.loads(cached)
                    if cached_data.get("calories", 0) > 0:
                        recommended = cached_data
                except Exception:
                    pass

        # 3. API Ninjas (if no local/cache match)
        if not recommended:
            api_key = get_setting("apininjas_api_key")
            usage = get_nutrition_api_usage_today()
            if api_key and usage < 800:
                try:
                    resp = requests.get(
                        "https://api.api-ninjas.com/v1/nutrition",
                        headers={"X-Api-Key": api_key},
                        params={"query": part},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        items = resp.json()
                        if items:
                            total_cal = sum(safe_float(i.get("calories")) for i in items)
                            total_prot = sum(safe_float(i.get("protein_g")) for i in items)
                            total_carb = sum(safe_float(i.get("carbohydrates_total_g")) for i in items)
                            total_fat = sum(safe_float(i.get("fat_total_g")) for i in items)

                            names = []
                            for i in items:
                                serving = safe_float(i.get("serving_size_g", 0))
                                n = i.get("name", "")
                                names.append(f"{serving}g {n}" if serving else n)

                            if total_cal > 0:
                                result = {
                                    "name": ", ".join(names) if names else part,
                                    "calories": round(total_cal),
                                    "protein": round(total_prot, 1),
                                    "carbs": round(total_carb, 1),
                                    "fat": round(total_fat, 1),
                                    "source": "apininjas",
                                }
                                recommended = result
                                set_nutrition_cache(part_lower, "apininjas", json.dumps(result))
                                increment_nutrition_api_usage()
                except Exception:
                    pass

        # 4. Search OFF for alternatives (always free)
        alternatives = _search_off_scored(food_name, limit=6)

        # 5. If still no recommended, promote best OFF alternative
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
            "query": part,
            "recommended": recommended,
            "alternatives": alternatives,
            "quantity": quantity,
            "unit": unit,
        })

    return jsonify({
        "results": results
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
