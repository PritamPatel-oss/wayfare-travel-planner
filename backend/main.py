"""Wayfare - Personalized Travel Itinerary Planner (FastAPI backend)."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import create_access_token, decode_access_token, hash_password, verify_password
from database import TripModel, UserModel, get_db, init_db
from itinerary import generate_itinerary, regenerate_day_itinerary

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
DEFAULT_ORIGINS = "http://localhost:5173,https://wayfare-travel-planner-black.vercel.app"
ORIGINS = [o.strip().rstrip("/") for o in os.getenv("FRONTEND_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist on startup
    init_db()
    yield


app = FastAPI(title="Wayfare API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- models


class UserAuthRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)


class TripRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=120)
    days: int = Field(default=3, ge=1, le=14)
    travelers: int = Field(default=1, ge=1, le=20)
    budget_level: Literal["budget", "moderate", "luxury"] = "moderate"
    budget_amount: Optional[float] = Field(default=None, ge=0)
    currency: Literal["INR", "USD", "EUR"] = "INR"
    travel_style: Literal["relaxed", "balanced", "adventurous"] = "balanced"
    interests: list[str] = Field(default_factory=list, max_length=12)
    start_date: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class RegenRequest(BaseModel):
    preferences: TripRequest
    day_number: int = Field(ge=1, le=14)
    other_places: list[str] = Field(default_factory=list)
    instruction: Optional[str] = Field(default=None, max_length=300)


class TripCreate(BaseModel):
    destination: str
    days: int
    preferences: dict
    itinerary: dict


class TripUpdate(BaseModel):
    itinerary: dict


# ---------------------------------------------------------------- auth


async def current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict:
    """Validate the JWT bearer token and return the authenticated user dict."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in to continue.")
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    user = db.query(UserModel).filter(UserModel.id == payload["sub"]).first()
    if not user:
        raise HTTPException(401, "Account not found. Please sign in again.")
    return {"id": user.id, "email": user.email, "token": token}


@app.post("/api/auth/signup", status_code=201)
def signup(req: UserAuthRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Please provide a valid email address.")
    existing = db.query(UserModel).filter(UserModel.email == email).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists.")
    user = UserModel(email=email, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": user.id, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email}}


@app.post("/api/auth/signin")
def signin(req: UserAuthRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password.")
    token = create_access_token({"sub": user.id, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email}}


@app.get("/api/auth/me")
def get_me(user: dict = Depends(current_user)):
    return user


# ---------------------------------------------------------------- AI

SYSTEM = (
    "You are an expert travel planner. Reply with ONE valid JSON object only. "
    "No markdown, no commentary."
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


def prefs_text(r: TripRequest) -> str:
    budget = f"{r.budget_level} budget"
    if r.budget_amount:
        budget += f" (about {r.budget_amount:,.0f} {r.currency} in total for the group)"
    lines = [
        f"Destination: {r.destination}",
        f"Travelers: {r.travelers}",
        f"Travel style: {r.travel_style}",
        f"Budget: {budget}",
        f"Interests: {', '.join(r.interests) if r.interests else 'general sightseeing, local food'}",
    ]
    if r.start_date:
        lines.append(f"Start date: {r.start_date} (consider season and opening days)")
    if r.notes:
        lines.append(f"Extra notes: {r.notes}")
    return "\n".join(lines)


RULES = (
    "Rules: list activities in time order, 4-6 per day; include breakfast, lunch and dinner "
    "suggestions as type food; put a stay suggestion on day 1 (type stay); add type transport "
    "entries when moving between far-apart areas; cost is the estimated cost for the whole "
    "group in {cur} (0 if free); keep total cost within the budget; use real, well-known places; "
    "relaxed = fewer stops, adventurous = more active and offbeat."
)


async def groq_json(prompt: str) -> dict:
    if not GROQ_API_KEY:
        raise HTTPException(500, "Server is missing GROQ_API_KEY.")
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json=payload,
            )
        if r.status_code == 429:
            raise HTTPException(429, "The AI is busy right now. Try again in a minute.")
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        return json.loads(content)
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, json.JSONDecodeError):
        raise HTTPException(502, "The AI could not build the itinerary. Please try again.")


def clean_day(day: dict, number: int) -> dict:
    if not isinstance(day, dict):
        return {"day": number, "theme": f"Day {number}", "activities": [], "image": None}
    acts = []
    for a in day.get("activities", []):
        if not isinstance(a, dict):
            continue
        try:
            cost = max(0, float(a.get("cost") or 0))
        except (TypeError, ValueError):
            cost = 0
        acts.append(
            {
                "time": str(a.get("time", "09:00"))[:5],
                "period": a.get("period", "morning"),
                "type": a.get("type") if a.get("type") in ("attraction", "food", "stay", "transport") else "attraction",
                "title": str(a.get("title", "Untitled stop"))[:120],
                "description": str(a.get("description", ""))[:400],
                "location": str(a.get("location", ""))[:160],
                "cost": cost,
            }
        )
    return {"day": number, "theme": str(day.get("theme", f"Day {number}"))[:100], "activities": acts, "image": day.get("image")}


# ---------------------------------------------------------------- images

_img_cache: dict[str, Optional[dict]] = {}


async def unsplash(client: httpx.AsyncClient, query: str) -> Optional[dict]:
    if not UNSPLASH_ACCESS_KEY:
        return None
    if query in _img_cache:
        return _img_cache[query]
    result = None
    try:
        r = await client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        )
        if r.status_code == 200 and r.json().get("results"):
            p = r.json()["results"][0]
            result = {"url": p["urls"]["regular"], "credit": p["user"]["name"], "link": p["links"]["html"]}
    except httpx.HTTPError:
        pass
    _img_cache[query] = result
    return result


async def attach_images(destination: str, days: list[dict], cover: bool = True) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        jobs = [unsplash(client, f"{destination} {d['theme']}") for d in days]
        if cover:
            jobs.append(unsplash(client, f"{destination} travel"))
        found = await asyncio.gather(*jobs)
    for d, img in zip(days, found):
        d["image"] = img
    return found[-1] if cover and found else None


# ---------------------------------------------------------------- routes


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/generate")
async def generate(req: TripRequest, user: dict = Depends(current_user)):
    data = await generate_itinerary(req)
    raw_days = data.get("days") or []
    if not raw_days:
        raise HTTPException(502, "Could not build the itinerary. Please try again.")
    days = [clean_day(d, i + 1) for i, d in enumerate(raw_days[: req.days]) if isinstance(d, dict)]
    cover = await attach_images(req.destination, days)
    return {
        "title": str(data.get("title", f"{req.days} days in {req.destination}"))[:120],
        "summary": str(data.get("summary", ""))[:600],
        "tips": [str(t)[:200] for t in (data.get("tips") or [])[:6]],
        "currency": req.currency,
        "cover": cover,
        "days": days,
    }


@app.post("/api/regenerate-day")
async def regenerate_day(req: RegenRequest, user: dict = Depends(current_user)):
    p = req.preferences
    data = await regenerate_day_itinerary(req)
    day = clean_day(data, req.day_number)
    if not day["activities"]:
        raise HTTPException(502, "Could not rebuild this day. Please try again.")
    await attach_images(p.destination, [day], cover=False)
    return day


@app.get("/api/image")
async def image(query: str):
    async with httpx.AsyncClient(timeout=10) as client:
        return await unsplash(client, query) or {}


@app.post("/api/trips", status_code=201)
def create_trip(
    body: TripCreate,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    trip = TripModel(
        user_id=user["id"],
        destination=body.destination,
        days=body.days,
        preferences=body.preferences,
        itinerary=body.itinerary,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return {
        "id": trip.id,
        "destination": trip.destination,
        "days": trip.days,
        "preferences": trip.preferences,
        "itinerary": trip.itinerary,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
    }


@app.get("/api/trips")
def list_trips(
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    trips = (
        db.query(TripModel)
        .filter(TripModel.user_id == user["id"])
        .order_by(TripModel.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "destination": t.destination,
            "days": t.days,
            "itinerary": t.itinerary,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in trips
    ]


@app.get("/api/trips/{trip_id}")
def get_trip(
    trip_id: str,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    trip = db.query(TripModel).filter(TripModel.id == str(trip_id), TripModel.user_id == user["id"]).first()
    if not trip:
        raise HTTPException(404, "Trip not found.")
    return {
        "id": trip.id,
        "destination": trip.destination,
        "days": trip.days,
        "preferences": trip.preferences,
        "itinerary": trip.itinerary,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
    }


@app.put("/api/trips/{trip_id}")
@app.patch("/api/trips/{trip_id}")
def update_trip(
    trip_id: str,
    body: TripUpdate,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    trip = db.query(TripModel).filter(TripModel.id == str(trip_id), TripModel.user_id == user["id"]).first()
    if not trip:
        raise HTTPException(404, "Trip not found.")
    trip.itinerary = body.itinerary
    trip.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trip)
    return {
        "id": trip.id,
        "destination": trip.destination,
        "days": trip.days,
        "preferences": trip.preferences,
        "itinerary": trip.itinerary,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
    }


@app.delete("/api/trips/{trip_id}", status_code=204)
def delete_trip(
    trip_id: str,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    trip = db.query(TripModel).filter(TripModel.id == str(trip_id), TripModel.user_id == user["id"]).first()
    if not trip:
        raise HTTPException(404, "Trip not found.")
    db.delete(trip)
    db.commit()
    return Response(status_code=204)
