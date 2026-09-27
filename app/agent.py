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

import datetime
from zoneinfo import ZoneInfo

import json
from pathlib import Path

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback
from .tools import (
    search_recipes,
    get_recipe_details,
    add_recipe,
    scale_recipe_servings,
    fetch_online_recipes,
    geocode_address,
    find_nearby_places,
    generate_recipe_image,
    generate_recipe_video,
)


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_system_prompt = schema_manager.generate_system_prompt(
    role_description=(
        "You are Recipe Concierge, an intelligent culinary assistant. "
        "You help users search for local and online recipes, get detailed cooking instructions, "
        "scale ingredient quantities, generate photos and short videos for dishes, find nearby supermarkets/grocery stores, "
        "run calculations or custom Python data analysis safely in a sandbox, and add new recipes to their collection in Firestore."
    ),
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

agent_instructions = (
    f"{a2ui_system_prompt}\n\n"
    "IMPORTANT ALLERGY & DIETARY MEMORY GUIDELINES:\n"
    "- ALWAYS remember and record any food allergies, sensitivities, intolerances, or dietary restrictions mentioned by the user across conversations.\n"
    "- Actively inspect retrieved user memories at the start of every session for allergy information (e.g., peanuts, gluten, dairy, shellfish, tree nuts).\n"
    "- NEVER recommend, suggest, or generate recipes containing ingredients that conflict with the user's remembered allergies or dietary restrictions unless explicitly requested with substitution advice.\n"
    "- When recommending recipes, proactively highlight allergen safety and confirm that ingredients comply with the user's allergy profile.\n\n"
    "Guidelines for Code Execution:\n"
    "- All code snippets provided will be executed within a secure Python sandbox environment.\n"
    "- Statefulness: All executed code snippets maintain variables across executions.\n"
    "- Output Visibility: Always print the result of code calculations to output.\n\n"
    "Use search_recipes to find recipes in the local Firestore database. "
    "Use fetch_online_recipes to search for real dishes and online recipes from TheMealDB when requested or when local results are insufficient. "
    "Use get_recipe_details when a user wants full ingredients and step-by-step instructions. "
    "Use scale_recipe_servings when a user asks to adjust ingredient quantities for a specific number of servings. "
    "Use generate_recipe_image when a user asks for a photo or image of a dish/recipe. "
    "Use generate_recipe_video when a user asks for a short video or clip of a dish/recipe or cooking technique. "
    "Use geocode_address to convert a street address or city into latitude and longitude coordinates. "
    "Use find_nearby_places to search for nearby grocery stores, supermarkets, or bakeries around given coordinates. "
    "Use add_recipe when a user shares a new recipe to save to their database."
)


def memory_service_builder():
    return VertexAiMemoryBankService(
        project="qwiklabs-gcp-01-c74d36ed01ba",
        location="us-east1",
        agent_engine_id="6774458375611613184",
    )


async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


def _get_code_executor():
    metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
    agent_engine_id = "projects/777935477803/locations/us-east1/reasoningEngines/6774458375611613184"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            agent_engine_id = metadata.get("remote_agent_runtime_id", agent_engine_id)
        except Exception:
            pass

    return AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=agent_engine_id
    )


root_agent = Agent(
    name="recipe_concierge",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=_get_code_executor(),
    instruction=agent_instructions,
    tools=[
        PreloadMemoryTool(),
        search_recipes,
        get_recipe_details,
        add_recipe,
        scale_recipe_servings,
        fetch_online_recipes,
        generate_recipe_image,
        generate_recipe_video,
        geocode_address,
        find_nearby_places,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)





