import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("wayfare.itinerary")

# System prompt shared across AI providers
SYSTEM = (
    "You are an expert travel planner. Reply with ONE valid JSON object only. "
    "No markdown, no commentary, no code fences."
)

DAY_SHAPE = (
    '{"day": 1, "theme": "short theme", "activities": [{"time": "09:00", '
    '"period": "morning|afternoon|evening", "type": "attraction|food|stay|transport", '
    '"title": "place or activity name", "description": "1-2 sentences", '
    '"location": "area or address", "cost": 0}]}'
)

TRIP_SHAPE = (
    '{"title": "short trip title", "summary": "2 sentence overview", '
    '"tips": ["3-5 short practical tips"], "days": [' + DAY_SHAPE + "]}"
)

RULES = (
    "Rules: list activities in time order, 4-6 per day; include breakfast, lunch and dinner "
    "suggestions as type food; put a stay suggestion on day 1 (type stay); add type transport "
    "entries when moving between far-apart areas; cost is the estimated cost for the whole "
    "group in {cur} (0 if free); keep total cost within the budget; use real, well-known places; "
    "relaxed = fewer stops, adventurous = more active and offbeat."
)


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def format_prefs_text(req) -> str:
    budget = f"{req.budget_level} budget"
    if req.budget_amount:
        budget += f" (about {req.budget_amount:,.0f} {req.currency} in total for the group)"
    interests_str = ", ".join(req.interests) if req.interests else "general sightseeing, local food"
    lines = [
        f"Destination: {req.destination}",
        f"Travelers: {req.travelers}",
        f"Travel style: {req.travel_style}",
        f"Budget: {budget}",
        f"Interests: {interests_str}",
    ]
    if getattr(req, "start_date", None):
        lines.append(f"Start date: {req.start_date} (consider season and opening days)")
    if getattr(req, "notes", None):
        lines.append(f"Extra notes: {req.notes}")
    return "\n".join(lines)


# ---------------------------------------------------------------- Gemini Provider
async def call_gemini(prompt: str) -> Optional[dict]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(url, json=payload)
        if r.status_code == 200:
            data = r.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(_strip_fences(text))
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to parse Gemini response: {e}")
                return None
        logger.warning(f"Gemini API returned HTTP {r.status_code}: {r.text[:200]}")
        return None


# ---------------------------------------------------------------- Groq Provider
async def call_groq(prompt: str) -> Optional[dict]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        if r.status_code == 200:
            data = r.json()
            try:
                content = data["choices"][0]["message"]["content"]
                return json.loads(_strip_fences(content))
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to parse Groq response: {e}")
                return None
        logger.warning(f"Groq API returned HTTP {r.status_code}: {r.text[:200]}")
        return None


# ---------------------------------------------------------------- Fallback Generator
THEMES = [
    "Arrival & Iconic Highlights",
    "Historic Landmarks & Cultural Heritage",
    "Local Flavors, Street Markets & Neighborhoods",
    "Scenic Viewpoints, Parks & Nature Walk",
    "Arts, Museums & Artisan Quarters",
    "Adventure, Outdoor Trails & Panoramic Views",
    "Boutique Shopping, Souvenirs & City Architecture",
    "Day Trip Exploration & Surrounding Countryside",
    "Wellness, Waterfront Promenade & Relaxation",
    "Modern Marvels & Contemporary City Life",
    "Culinary Immersion & Hidden Local Spots",
    "Historic Alleys, Cathedrals & Sacred Sites",
    "Sunset Lookout, Photography & Night Markets",
    "Farewell Celebration & Local Keepsakes",
]


def build_fallback_itinerary(req) -> dict:
    dest = req.destination.strip()
    days_count = max(1, min(14, int(req.days)))
    interests = req.interests or ["Sightseeing", "Local Food", "Culture"]
    primary_interest = interests[0] if interests else "Sightseeing"
    travelers = max(1, int(req.travelers))
    style = req.travel_style or "balanced"
    budget_lvl = req.budget_level or "moderate"
    cur = req.currency or "INR"

    # Multipliers for cost estimation
    mult = 0.5 if budget_lvl == "budget" else (2.5 if budget_lvl == "luxury" else 1.0)
    base_unit = 400 if cur == "INR" else (20 if cur in ("USD", "EUR") else 80)

    days_list = []
    for d in range(1, days_count + 1):
        theme = THEMES[(d - 1) % len(THEMES)]
        activities = []

        if d == 1:
            activities.append({
                "time": "09:00",
                "period": "morning",
                "type": "stay",
                "title": f"Check-in & Orientation at {dest}",
                "description": f"Check into your central {budget_lvl} stay in {dest} and get oriented with the neighborhood.",
                "location": f"Central District, {dest}",
                "cost": round(base_unit * 5 * mult * travelers),
            })

        activities.append({
            "time": "10:30",
            "period": "morning",
            "type": "attraction",
            "title": f"Explore {dest} Iconic Landmarks & Heritage",
            "description": f"Walk through iconic plazas, historic architecture, and vibrant morning streets in {dest}.",
            "location": f"Historic Old Town, {dest}",
            "cost": round(base_unit * 1.5 * mult * travelers),
        })

        activities.append({
            "time": "13:00",
            "period": "afternoon",
            "type": "food",
            "title": f"Authentic Regional Lunch & Specialties",
            "description": f"Savor traditional cuisine, street favorites, and chef specials celebrated across {dest}.",
            "location": f"Local Gourmet District, {dest}",
            "cost": round(base_unit * 2 * mult * travelers),
        })

        activities.append({
            "time": "15:30",
            "period": "afternoon",
            "type": "attraction",
            "title": f"{primary_interest.capitalize()} Discovery & Scenic Stroll",
            "description": f"Immerse yourself in curated cultural displays, artisan shops, and scenic viewpoints.",
            "location": f"Arts & Culture Quarter, {dest}",
            "cost": round(base_unit * 1.2 * mult * travelers),
        })

        activities.append({
            "time": "19:30",
            "period": "evening",
            "type": "food",
            "title": f"Evening Dining & Atmosphere in {dest}",
            "description": f"Relax with dinner and drinks in a cozy bistro offering classic regional hospitality.",
            "location": f"Downtown Promenade, {dest}",
            "cost": round(base_unit * 2.5 * mult * travelers),
        })

        days_list.append({
            "day": d,
            "theme": theme,
            "activities": activities,
        })

    return {
        "title": f"{days_count} Days of Wonder in {dest}",
        "summary": f"A personalized {style} itinerary through {dest}, designed for {budget_lvl} travel with focus on {', '.join(interests)}.",
        "tips": [
            f"Wear comfortable shoes to navigate the walking areas of {dest} comfortably.",
            f"Keep local currency ({cur}) handy for market stalls, public transport, and tips.",
            "Pre-book entrance tickets to major monuments online to skip queues.",
            "Download offline maps to easily explore neighborhoods and scenic alleys.",
        ],
        "days": days_list,
    }


def build_fallback_day(req) -> dict:
    p = req.preferences
    dest = p.destination.strip()
    day_num = req.day_number
    interests = p.interests or ["Sightseeing", "Food"]
    travelers = max(1, int(p.travelers))
    budget_lvl = p.budget_level or "moderate"
    cur = p.currency or "INR"

    mult = 0.5 if budget_lvl == "budget" else (2.5 if budget_lvl == "luxury" else 1.0)
    base_unit = 400 if cur == "INR" else (20 if cur in ("USD", "EUR") else 80)

    theme = THEMES[(day_num - 1) % len(THEMES)]
    instruction = req.instruction or "Fresh alternative highlights"

    return {
        "day": day_num,
        "theme": f"{theme} (Alternative)",
        "activities": [
            {
                "time": "09:30",
                "period": "morning",
                "type": "attraction",
                "title": f"Morning Discovery: {instruction[:40]}",
                "description": f"Fresh morning exploration in {dest} aligned with your updated preference.",
                "location": f"Scenic District, {dest}",
                "cost": round(base_unit * 1.5 * mult * travelers),
            },
            {
                "time": "12:30",
                "period": "afternoon",
                "type": "food",
                "title": f"Artisan Cafe & Local Lunch",
                "description": f"Enjoy casual regional fare in a beloved neighborhood cafe in {dest}.",
                "location": f"Artisan Square, {dest}",
                "cost": round(base_unit * 1.8 * mult * travelers),
            },
            {
                "time": "15:00",
                "period": "afternoon",
                "type": "attraction",
                "title": f"Hidden Gems & {interests[0].capitalize() if interests else 'Culture'}",
                "description": f"An off-the-beaten-path stop avoiding previously visited crowded areas.",
                "location": f"Old Town Alleyways, {dest}",
                "cost": round(base_unit * 1.0 * mult * travelers),
            },
            {
                "time": "19:00",
                "period": "evening",
                "type": "food",
                "title": f"Curated Dinner Experience in {dest}",
                "description": f"Wrap up the day with a memorable meal reflecting {dest}'s culinary heritage.",
                "location": f"Culinary Quarter, {dest}",
                "cost": round(base_unit * 2.5 * mult * travelers),
            },
        ],
    }


# ---------------------------------------------------------------- Dispatcher
async def generate_itinerary(req) -> dict:
    prompt = (
        f"Plan a {req.days}-day trip.\n{format_prefs_text(req)}\n\n"
        f"{RULES.format(cur=req.currency)} Return exactly {req.days} days.\n"
        f"Return JSON shaped like: {TRIP_SHAPE}"
    )

    # 1. Try Gemini if configured
    data = await call_gemini(prompt)
    if data and data.get("days"):
        return data

    # 2. Try Groq if configured
    data = await call_groq(prompt)
    if data and data.get("days"):
        return data

    # 3. Fallback generator
    logger.info("Using smart fallback itinerary generator for %s", req.destination)
    return build_fallback_itinerary(req)


async def regenerate_day_itinerary(req) -> dict:
    p = req.preferences
    avoid = ", ".join(req.other_places[:40]) or "none"
    prompt = (
        f"Rewrite day {req.day_number} of a {p.days}-day trip.\n{format_prefs_text(p)}\n"
        f"Do NOT repeat these places already used on other days: {avoid}.\n"
        f"Change request: {req.instruction or 'Give a fresh alternative plan for this day.'}\n\n"
        f"{RULES.format(cur=p.currency)}\nReturn JSON shaped like: {DAY_SHAPE}"
    )

    # 1. Try Gemini
    data = await call_gemini(prompt)
    if data and data.get("activities"):
        return data

    # 2. Try Groq
    data = await call_groq(prompt)
    if data and data.get("activities"):
        return data

    # 3. Fallback generator
    logger.info("Using fallback day generator for %s day %s", p.destination, req.day_number)
    return build_fallback_day(req)
