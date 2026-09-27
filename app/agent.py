# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import subprocess
import urllib.parse
import urllib.request
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types
from google.genai.types import Modality
from google.oauth2.credentials import Credentials

from app.a2ui_utils import a2ui_callback

# Load local .env environment variables if present
load_dotenv()

# Hardcoded project ID and GCS bucket name as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-23cc191dff3a"
COLLECTION_NAME = "workouts"
GCS_BUCKET_NAME = "tricoach-ai-media-qwiklabs-gcp-02-23cc191dff3a"
MEMORY_BANK_ID = "6274769923206021120"


def get_remote_agent_runtime_id() -> str:
    """Reads remote Agent Engine / Reasoning Engine resource ID from deployment_metadata.json."""
    metadata_path = os.path.join(
        os.path.dirname(__file__), "..", "deployment_metadata.json"
    )
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path) as f:
                data = json.load(f)
                runtime_id = data.get("remote_agent_runtime_id")
                if runtime_id:
                    return runtime_id
        except Exception:
            pass
    return f"projects/15179863729/locations/us-east1/reasoningEngines/{MEMORY_BANK_ID}"


def memory_service_builder() -> VertexAiMemoryBankService:
    """Constructs the Vertex AI Memory Bank service for deployed Agent Runtime instances."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Sends completed turn session to Vertex AI Memory Bank for long-term memory extraction."""
    await callback_context.add_session_to_memory()
    return None


def get_db() -> firestore.Client:
    """Instantiates a Firestore client with hardcoded project ID."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True
        ).strip()
        credentials = Credentials(token)
        return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials)
    except Exception:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)


def list_workouts(sport: str | None = None, difficulty: str | None = None) -> list[dict[str, Any]]:
    """Lists triathlon and fitness workout plans from the Firestore database.

    Args:
        sport: Optional filter by sport type ('swim', 'bike', 'run', 'brick').
        difficulty: Optional filter by difficulty level ('Beginner', 'Intermediate', 'Advanced').

    Returns:
        A list of workout dictionaries containing details for matching workouts.
    """
    db = get_db()
    query = db.collection(COLLECTION_NAME)

    if sport:
        query = query.where("sport", "==", sport.lower())
    if difficulty:
        query = query.where("difficulty", "==", difficulty)

    docs = query.stream()
    workouts = []
    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id
        workouts.append(item)

    return workouts


def get_workout(workout_id: str) -> dict[str, Any]:
    """Retrieves full details for a specific workout plan from Firestore by its ID.

    Args:
        workout_id: The unique string identifier of the workout (e.g. 'swim_endurance_base', 'bike_ftp_intervals').

    Returns:
        A dictionary containing full workout details or an error message if not found.
    """
    db = get_db()
    doc_ref = db.collection(COLLECTION_NAME).document(workout_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    else:
        return {"error": f"Workout with ID '{workout_id}' not found."}


def add_workout(
    id: str,
    title: str,
    sport: str,
    duration_minutes: int,
    difficulty: str,
    description: str,
    target_zones: str,
) -> dict[str, Any]:
    """Adds a new workout plan or updates an existing workout in Firestore.

    Args:
        id: Unique identifier for the workout (e.g., 'run_hills_builder').
        title: Title of the workout plan (e.g., 'Hill Repeats Endurance Run').
        sport: Sport type ('swim', 'bike', 'run', 'brick').
        duration_minutes: Total workout duration in minutes.
        difficulty: Difficulty level ('Beginner', 'Intermediate', 'Advanced').
        description: Detailed instructions and structure for the workout.
        target_zones: Recommended heart rate or power zones (e.g. 'Zone 3 / Zone 4').

    Returns:
        A confirmation dictionary indicating success.
    """
    db = get_db()
    workout_data = {
        "id": id,
        "title": title,
        "sport": sport.lower(),
        "duration_minutes": duration_minutes,
        "difficulty": difficulty,
        "description": description,
        "target_zones": target_zones,
    }
    db.collection(COLLECTION_NAME).document(id).set(workout_data)
    return {"status": "success", "message": f"Workout '{title}' saved successfully with ID '{id}'."}


def calculate_training_zones(metric_type: str, value: float) -> dict[str, Any]:
    """Calculates personalized 5-zone training targets for power (FTP in Watts) or max heart rate (BPM).

    Args:
        metric_type: Type of baseline metric: 'ftp' for cycling power in Watts, or 'max_hr' for max heart rate in BPM.
        value: The baseline value (e.g., 250 for 250W FTP, or 185 for 185 BPM Max HR).

    Returns:
        A dictionary containing target ranges for Zone 1 through Zone 5.
    """
    m_type = metric_type.lower().strip()
    if "power" in m_type or "ftp" in m_type:
        return {
            "metric": "FTP Power (Watts)",
            "baseline": value,
            "zones": {
                "Zone 1 (Active Recovery)": f"< {round(value * 0.55)} W (<55%)",
                "Zone 2 (Endurance)": f"{round(value * 0.55)} - {round(value * 0.75)} W (55-75%)",
                "Zone 3 (Tempo / Sweetspot)": f"{round(value * 0.76)} - {round(value * 0.90)} W (76-90%)",
                "Zone 4 (Threshold)": f"{round(value * 0.91)} - {round(value * 1.05)} W (91-105%)",
                "Zone 5 (VO2 Max)": f"{round(value * 1.06)} - {round(value * 1.20)} W (106-120%)",
            },
        }
    else:
        return {
            "metric": "Max Heart Rate (BPM)",
            "baseline": value,
            "zones": {
                "Zone 1 (Active Recovery)": f"{round(value * 0.50)} - {round(value * 0.60)} BPM (50-60%)",
                "Zone 2 (Aerobic Endurance)": f"{round(value * 0.60)} - {round(value * 0.70)} BPM (60-70%)",
                "Zone 3 (Tempo)": f"{round(value * 0.70)} - {round(value * 0.80)} BPM (70-80%)",
                "Zone 4 (Threshold)": f"{round(value * 0.80)} - {round(value * 0.90)} BPM (80-90%)",
                "Zone 5 (Anaerobic / VO2 Max)": f"{round(value * 0.90)} - {round(value * 1.00)} BPM (90-100%)",
            },
        }


def get_outdoor_weather_conditions(location: str) -> dict[str, Any]:
    """Fetches live weather and wind conditions for outdoor training via Open-Meteo public API.

    Args:
        location: City or location name (e.g. 'Boulder', 'San Francisco', 'Austin').

    Returns:
        A dictionary with live temperature, wind speed, and training advice.
    """
    try:
        encoded_loc = urllib.parse.quote(location)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_loc}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "TriCoachAI/1.0"})

        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return {"error": f"Location '{location}' not found."}

        res = geo_data["results"][0]
        lat = res["latitude"]
        lon = res["longitude"]
        city = res.get("name", location)
        country = res.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "TriCoachAI/1.0"})
        with urllib.request.urlopen(req_w, timeout=5) as resp_w:
            w_data = json.loads(resp_w.read().decode())

        cw = w_data.get("current_weather", {})
        temp_c = cw.get("temperature", 0)
        temp_f = round((temp_c * 9 / 5) + 32, 1)
        wind_kmh = cw.get("windspeed", 0)
        wind_mph = round(wind_kmh * 0.621371, 1)

        advice = []
        if temp_f > 80:
            advice.append(
                "High heat: Increase hydration by 250-500ml/hr and reduce target heart rate by 5-10 BPM."
            )
        elif temp_f < 45:
            advice.append(
                "Cold conditions: Wear wind-blocking layers and warm up thoroughly."
            )
        if wind_mph > 15:
            advice.append(
                f"Strong winds ({wind_mph} mph): Exercise caution with deep-section bike wheels."
            )

        return {
            "location": f"{city}, {country}".strip(", "),
            "temperature_f": temp_f,
            "temperature_c": temp_c,
            "wind_speed_mph": wind_mph,
            "wind_speed_kmh": wind_kmh,
            "training_advice": (
                " ".join(advice)
                if advice
                else "Conditions look great for outdoor training!"
            ),
        }
    except Exception as e:
        return {"error": f"Failed to fetch weather data: {str(e)}"}


def geocode_address(address: str) -> dict[str, Any]:
    """Converts an address or location name into geographic coordinates (latitude and longitude) using Google Geocoding API.

    Args:
        address: The address or location name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'Boulder, CO').

    Returns:
        A dictionary containing the formatted address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set."}

    try:
        encoded_addr = urllib.parse.quote(address)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_addr}&key={api_key}"

        req = urllib.request.Request(url, headers={"User-Agent": "TriCoachAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") == "OK" and data.get("results"):
            first_res = data["results"][0]
            loc = first_res["geometry"]["location"]
            return {
                "address": first_res.get("formatted_address", address),
                "location": {
                    "latitude": loc["lat"],
                    "longitude": loc["lng"],
                },
            }
        else:
            return {
                "error": f"Geocoding failed with status '{data.get('status')}' for address: {address}"
            }
    except Exception as e:
        return {"error": f"Failed to geocode address: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "gym",
    radius_meters: float = 3000.0,
) -> dict[str, Any]:
    """Finds nearby places (e.g., gyms, parks, sports_complex, athletic tracks) using the Places API (New) REST endpoint.

    Args:
        latitude: Latitude coordinate for the center search point.
        longitude: Longitude coordinate for the center search point.
        place_type: Type of place to search for (e.g., 'gym', 'park', 'sports_complex').
        radius_meters: Search radius in meters (default: 3000.0 meters).

    Returns:
        A dictionary containing a list of matching nearby places with name, formatted address, and location.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set."}

    try:
        places_url = "https://places.googleapis.com/v1/places:searchNearby"
        payload = {
            "includedTypes": [place_type.lower().strip()],
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            places_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            },
        )

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        raw_places = data.get("places", [])
        formatted_places = []
        for p in raw_places:
            formatted_places.append(
                {
                    "name": p.get("displayName", {}).get("text", "Unknown"),
                    "address": p.get("formattedAddress", "N/A"),
                    "location": {
                        "latitude": p.get("location", {}).get("latitude"),
                        "longitude": p.get("location", {}).get("longitude"),
                    },
                }
            )

        return {
            "search_center": {"latitude": latitude, "longitude": longitude},
            "place_type": place_type,
            "places": formatted_places,
        }
    except Exception as e:
        return {"error": f"Failed to search nearby places: {str(e)}"}


def generate_workout_visual(
    prompt: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Generates an image for a triathlon workout, route map, finish line poster, or motivational badge using the gemini-3.1-flash-lite-image model.

    Args:
        prompt: Detailed description of the workout image or poster to generate.
        tool_context: The ADK ToolContext object provided automatically by the framework.

    Returns:
        A dictionary containing the artifact filename and public Cloud Storage image URL.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[Modality.IMAGE],
            ),
        )

        img_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not img_bytes:
            return {"error": "No image bytes were returned by the gemini-3.1-flash-lite-image model."}

        filename = f"triathlon_visual_{uuid.uuid4().hex[:8]}.jpg"

        # 1. Save with tool_context.save_artifact for Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same image bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(img_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "artifact_filename": filename,
            "public_image_url": public_url,
        }
    except Exception as e:
        return {"error": f"Failed to generate workout image: {str(e)}"}


def generate_workout_video(
    prompt: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Generates a short video for a triathlon item (workout demo, race scene, swim/bike/run technique) using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Args:
        prompt: Detailed description of the triathlon item or workout video to generate.
        tool_context: The ADK ToolContext object provided automatically by the framework.

    Returns:
        A dictionary containing the artifact filename and public Cloud Storage video URL.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        response = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=[
                {"type": "text", "text": prompt}
            ],
            generation_config={
                "video_config": {
                    "task": "text_to_video"
                }
            }
        )

        video_bytes = None
        mime_type = "video/mp4"

        if hasattr(response, "output_video") and response.output_video:
            if hasattr(response.output_video, "data") and response.output_video.data:
                video_bytes = base64.b64decode(response.output_video.data)
                if hasattr(response.output_video, "mime_type") and response.output_video.mime_type:
                    mime_type = response.output_video.mime_type

        if not video_bytes and hasattr(response, "steps") and response.steps:
            for step in response.steps:
                if getattr(step, "type", None) == "model_output" and hasattr(step, "content"):
                    for item in step.content:
                        if getattr(item, "type", None) == "video" and hasattr(item, "data"):
                            video_bytes = base64.b64decode(item.data)
                            if hasattr(item, "mime_type") and item.mime_type:
                                mime_type = item.mime_type
                            break

        if not video_bytes:
            return {"error": "No video bytes were returned by the gemini-omni-flash-preview model."}

        filename = f"triathlon_video_{uuid.uuid4().hex[:8]}.mp4"

        # 1. Save with tool_context.save_artifact for Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same video bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "artifact_filename": filename,
            "public_video_url": public_url,
        }
    except Exception as e:
        return {"error": f"Failed to generate workout video: {str(e)}"}


# Initialize A2UI Schema Manager with version 0.8 and BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are TriCoach AI, an expert conversational fitness and triathlon coach.",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

domain_instruction = (
    "CRITICAL MEMORY MANDATE: You MUST proactively remember and retain all user allergies (e.g. food, medication, material, or environmental allergies), "
    "dietary restrictions, medical conditions, and health preferences across conversations. Always consult preloaded user memories "
    "for allergies before providing nutrition, sports drink, energy gel, or training plan recommendations. "
    "You help athletes manage training plans from Firestore (`list_workouts`, `get_workout`, `add_workout`), "
    "compute personalized 5-zone training targets (`calculate_training_zones`), "
    "fetch real-time outdoor weather conditions (`get_outdoor_weather_conditions`), "
    "find nearby training facilities using Google Maps (`geocode_address`, `find_nearby_places`), "
    "generate custom workout images/posters using `generate_workout_visual`, "
    "generate short workout demonstration/race videos using `generate_workout_video`, "
    "and execute Python code in a secure sandbox for fitness calculations and data analysis."
)

full_instruction = f"{a2ui_instruction}\n\n{domain_instruction}"

# Initialize Agent Engine Sandbox Code Executor for stateful code execution
code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=get_remote_agent_runtime_id(),
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=full_instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        list_workouts,
        get_workout,
        add_workout,
        calculate_training_zones,
        get_outdoor_weather_conditions,
        geocode_address,
        find_nearby_places,
        generate_workout_visual,
        generate_workout_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
