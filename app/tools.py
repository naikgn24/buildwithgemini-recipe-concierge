import base64
import datetime
import json
import logging
import os
import re
import urllib.parse
import urllib.request

import google.auth
import google.auth.transport.requests
from google import genai
from google.genai import types
from google.cloud import firestore, storage
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

# HARDCODED PROJECT ID and GCS BUCKET - Required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-c74d36ed01ba"
GCS_BUCKET_NAME = "recipe-concierge-images-qwiklabs-gcp-01-c74d36ed01ba"


def _get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def search_recipes(
    cuisine: str = None,
    dietary_tag: str = None,
    max_prep_time: int = None
) -> list[dict]:
    """Search for recipes in the Firestore database filtered by cuisine, dietary tag, or prep time.

    Args:
        cuisine: Optional cuisine filter (e.g., 'Italian', 'Mexican', 'Thai', 'American').
        dietary_tag: Optional dietary tag filter (e.g., 'vegetarian', 'vegan', 'gluten-free').
        max_prep_time: Optional maximum preparation time in minutes.

    Returns:
        A list of matching recipe dictionaries.
    """
    db = _get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()

    results = []
    for doc in docs:
        recipe = doc.to_dict()
        recipe["id"] = doc.id

        # Apply in-memory filtering for flexibility
        if cuisine and cuisine.lower() not in recipe.get("cuisine", "").lower():
            continue

        if dietary_tag:
            tags = [t.lower() for t in recipe.get("dietary_tags", [])]
            if dietary_tag.lower() not in tags:
                continue

        if max_prep_time and recipe.get("prep_time_mins", 0) > max_prep_time:
            continue

        results.append(recipe)

    return results


def get_recipe_details(recipe_id: str) -> dict:
    """Get complete details for a specific recipe by ID.

    Args:
        recipe_id: The unique ID of the recipe document.

    Returns:
        A dictionary containing recipe details or an error message if not found.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("recipes").document(recipe_id)
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Recipe with ID '{recipe_id}' not found."}

    data = doc.to_dict()
    data["id"] = doc.id
    return data


def add_recipe(
    title: str,
    cuisine: str,
    prep_time_mins: int,
    servings: int,
    ingredients: list[str],
    instructions: str,
    dietary_tags: list[str] = None,
    calories_per_serving: int = None
) -> str:
    """Add a new recipe to the Firestore database.

    Args:
        title: The title of the recipe.
        cuisine: The cuisine type (e.g. Italian, Thai, American).
        prep_time_mins: Preparation time in minutes.
        servings: Number of servings.
        ingredients: List of ingredient strings.
        instructions: Step-by-step cooking instructions.
        dietary_tags: Optional list of dietary tags (e.g. ['vegetarian', 'gluten-free']).
        calories_per_serving: Optional estimated calories per serving.

    Returns:
        A confirmation message with the assigned recipe ID.
    """
    db = _get_firestore_client()

    # Generate document ID from title
    doc_id = title.lower().replace(" ", "-").replace("&", "and")
    # Sanitize doc_id
    doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")

    recipe_data = {
        "id": doc_id,
        "title": title,
        "cuisine": cuisine,
        "prep_time_mins": prep_time_mins,
        "servings": servings,
        "ingredients": ingredients,
        "instructions": instructions,
        "dietary_tags": dietary_tags or [],
        "calories_per_serving": calories_per_serving
    }

    db.collection("recipes").document(doc_id).set(recipe_data)
    return f"Successfully added recipe '{title}' to Firestore with ID: '{doc_id}'."


def scale_recipe_servings(recipe_id: str, target_servings: int) -> dict:
    """Scale ingredient quantities of a recipe to match a target number of servings.

    Args:
        recipe_id: The unique ID of the recipe document.
        target_servings: The desired number of servings to scale to.

    Returns:
        A dictionary containing the scaled recipe details and ingredients.
    """
    recipe = get_recipe_details(recipe_id)
    if "error" in recipe:
        return recipe

    original_servings = recipe.get("servings", 1)
    if original_servings <= 0:
        original_servings = 1

    scale_factor = target_servings / original_servings

    scaled_ingredients = []
    for ing in recipe.get("ingredients", []):
        def scale_match(match):
            val = float(match.group(0))
            scaled_val = val * scale_factor
            return f"{scaled_val:.2f}".rstrip('0').rstrip('.')

        scaled_ing = re.sub(r'^\d+(\.\d+)?', scale_match, ing)
        scaled_ingredients.append(scaled_ing)

    return {
        "recipe_id": recipe_id,
        "title": recipe.get("title"),
        "original_servings": original_servings,
        "target_servings": target_servings,
        "scale_factor": round(scale_factor, 2),
        "scaled_ingredients": scaled_ingredients,
        "instructions": recipe.get("instructions")
    }


def fetch_online_recipes(query: str) -> list[dict]:
    """Search for real recipes online using TheMealDB public API.

    Args:
        query: Search keyword for dish or main ingredient (e.g. 'chicken', 'pasta', 'arrabiata', 'curry').

    Returns:
        A list of online recipe dictionaries containing title, category, cuisine area, instructions, and ingredients.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RecipeConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            meals = data.get("meals")
            if not meals:
                return []

            results = []
            for meal in meals[:5]:
                ingredients = []
                for i in range(1, 21):
                    ing = meal.get(f"strIngredient{i}")
                    measure = meal.get(f"strMeasure{i}")
                    if ing and ing.strip():
                        item = f"{measure.strip()} {ing.strip()}".strip() if measure else ing.strip()
                        ingredients.append(item)

                results.append({
                    "id": meal.get("idMeal"),
                    "title": meal.get("strMeal"),
                    "category": meal.get("strCategory"),
                    "cuisine": meal.get("strArea"),
                    "instructions": meal.get("strInstructions"),
                    "thumbnail": meal.get("strMealThumb"),
                    "ingredients": ingredients
                })
            return results
    except Exception as e:
        logger.error(f"Error fetching online recipes: {e}")
        return [{"error": f"Failed to fetch online recipes: {str(e)}"}]


def geocode_address(address: str) -> dict:
    """Geocode a street address or location name into latitude and longitude coordinates.

    Args:
        address: Address or place name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A dictionary with the formatted address and latitude/longitude coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set."}

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            results = data.get("results", [])
            if not results:
                return {"error": f"No geocoding results found for address: '{address}'"}

            top_result = results[0]
            location = top_result.get("geometry", {}).get("location", {})
            return {
                "address": top_result.get("formatted_address"),
                "location": {
                    "latitude": location.get("lat"),
                    "longitude": location.get("lng")
                }
            }
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return {"error": f"Failed to geocode address: {str(e)}"}


def find_nearby_places(latitude: float, longitude: float, place_type: str = "supermarket", radius_meters: float = 5000.0) -> list[dict]:
    """Find nearby places (such as grocery stores or supermarkets) of a given type around coordinates using Places API (New).

    Args:
        latitude: Latitude of the center location.
        longitude: Longitude of the center location.
        place_type: Type of place to search for (e.g., 'supermarket', 'grocery_store', 'bakery', 'restaurant').
        radius_meters: Radius in meters around the center location (default 5000.0).

    Returns:
        A list of matching places with name, formatted address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is not set."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
    }

    body = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius_meters
            }
        }
    }

    try:
        json_data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            places = data.get("places", [])

            results = []
            for p in places:
                display_name = p.get("displayName", {}).get("text", "")
                results.append({
                    "name": display_name,
                    "address": p.get("formattedAddress"),
                    "location": p.get("location")
                })
            return results
    except Exception as e:
        logger.error(f"Nearby places search error: {e}")
        return [{"error": f"Failed to find nearby places: {str(e)}"}]


async def generate_recipe_image(prompt: str, tool_context: ToolContext) -> dict:
    """Generate a presentation photo of a dish using Gemini Image Generation, save as session artifact, and upload to public GCS.

    Args:
        prompt: Description of the dish or recipe photo to generate (e.g., 'A delicious plate of avocado toast with poached eggs').
        tool_context: Injected context for artifact management.

    Returns:
        A dictionary containing the public GCS URL, artifact filename, and status.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global"
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Failed to generate image bytes from model response."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_prompt = re.sub(r'[^a-zA-Z0-9]', '_', prompt[:20]).strip('_').lower()
        filename = f"{sanitized_prompt}_{timestamp}.jpg"

        # 1. Save artifact with tool_context.save_artifact
        artifact = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact)

        # 2. Upload same bytes to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "artifact_filename": filename,
            "public_url": public_url,
            "message": f"Successfully generated image and uploaded to {public_url}"
        }
    except Exception as e:
        logger.error(f"Error generating recipe image: {e}")
        return {"error": f"Failed to generate recipe image: {str(e)}"}


async def generate_recipe_video(prompt: str, tool_context: ToolContext) -> dict:
    """Generate a short video for a recipe or cooking item using Google's Omni model (gemini-omni-flash-preview) in global region, save as session artifact, and upload to public GCS.

    Args:
        prompt: Description of the cooking item or dish video to generate (e.g., 'A 5-second video of sizzling garlic in olive oil' or 'Chopping fresh basil').
        tool_context: Injected context for artifact management.

    Returns:
        A dictionary containing the public GCS URL, artifact filename, and status message.
    """
    try:
        video_bytes = None
        mime_type = "video/mp4"

        # Try client.interactions.create with gemini-omni-flash-preview
        try:
            client = genai.Client(
                vertexai=True,
                project=FIRESTORE_PROJECT_ID,
                location="global"
            )
            response = client.interactions.create(
                model="gemini-omni-flash-preview",
                input=[{"type": "text", "text": prompt}],
                response_format=[{"type": "video"}]
            )

            if hasattr(response, "output_video") and response.output_video:
                ov = response.output_video
                raw_data = getattr(ov, "data", None) or getattr(ov, "bytes", None)
                if raw_data:
                    if isinstance(raw_data, str):
                        video_bytes = base64.b64decode(raw_data)
                    else:
                        video_bytes = raw_data

            if not video_bytes and hasattr(response, "steps") and response.steps:
                for step in reversed(response.steps):
                    content_list = getattr(step, "content", None) or (step.get("content") if isinstance(step, dict) else None)
                    if content_list:
                        for item in content_list:
                            item_dict = item if isinstance(item, dict) else (item.model_dump() if hasattr(item, "model_dump") else {})
                            data_str = item_dict.get("data") or getattr(item, "data", None)
                            if data_str and isinstance(data_str, str):
                                try:
                                    video_bytes = base64.b64decode(data_str)
                                    break
                                except Exception:
                                    pass
                        if video_bytes:
                            break
        except Exception as sdk_err:
            logger.warning(f"SDK interactions call error: {sdk_err}, falling back to REST API")

        # Fallback to direct HTTP REST endpoint if needed
        if not video_bytes:
            credentials, _ = google.auth.default()
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)

            url = f"https://aiplatform.googleapis.com/v1beta1/projects/{FIRESTORE_PROJECT_ID}/locations/global/interactions"
            body = {
                "model": "gemini-omni-flash-preview",
                "input": [{"type": "text", "text": prompt}],
                "response_format": [{"type": "video"}]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                steps = res.get("steps", [])
                for step in reversed(steps):
                    content = step.get("content", [])
                    for item in content:
                        data_b64 = item.get("data")
                        if data_b64:
                            video_bytes = base64.b64decode(data_b64)
                            break
                    if video_bytes:
                        break

        if not video_bytes:
            return {"error": "Failed to generate or retrieve video bytes from model response."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_prompt = re.sub(r'[^a-zA-Z0-9]', '_', prompt[:20]).strip('_').lower()
        filename = f"{sanitized_prompt}_{timestamp}.mp4"

        # 1. Save artifact with tool_context.save_artifact
        artifact = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact)

        # 2. Upload same bytes to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "artifact_filename": filename,
            "public_url": public_url,
            "message": f"Successfully generated video and uploaded to {public_url}"
        }
    except Exception as e:
        logger.error(f"Error generating recipe video: {e}")
        return {"error": f"Failed to generate recipe video: {str(e)}"}

