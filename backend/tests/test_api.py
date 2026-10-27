import os
import sys
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use an isolated in-memory or file-based SQLite database for testing
os.environ["DATABASE_URL"] = "sqlite:///./test_wayfare.db"
os.environ["JWT_SECRET"] = "test-secret-key-32-characters-minimum"

from database import Base, engine, UserModel, TripModel
from main import app, clean_day
from auth import create_access_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_signup_success():
    payload = {"email": "traveler@example.com", "password": "securepassword123"}
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "traveler@example.com"
    assert "id" in data["user"]


def test_signup_duplicate_email():
    payload = {"email": "dup@example.com", "password": "password123"}
    r1 = client.post("/api/auth/signup", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/auth/signup", json=payload)
    assert r2.status_code == 400
    assert "already exists" in r2.json()["detail"]


def test_signup_invalid_email():
    r = client.post("/api/auth/signup", json={"email": "notanemail", "password": "password123"})
    assert r.status_code == 400
    assert "valid email" in r.json()["detail"]


def test_signup_short_password():
    r = client.post("/api/auth/signup", json={"email": "short@example.com", "password": "123"})
    assert r.status_code == 422


def test_signin_success():
    client.post("/api/auth/signup", json={"email": "login@example.com", "password": "mypassword123"})
    r = client.post("/api/auth/signin", json={"email": "login@example.com", "password": "mypassword123"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["user"]["email"] == "login@example.com"


def test_signin_invalid_password():
    client.post("/api/auth/signup", json={"email": "wrongpass@example.com", "password": "mypassword123"})
    r = client.post("/api/auth/signin", json={"email": "wrongpass@example.com", "password": "wrongpassword"})
    assert r.status_code == 401
    assert "Invalid email or password" in r.json()["detail"]


def test_signin_nonexistent_user():
    r = client.post("/api/auth/signin", json={"email": "ghost@example.com", "password": "password123"})
    assert r.status_code == 401


def test_auth_me():
    r_up = client.post("/api/auth/signup", json={"email": "me@example.com", "password": "password123"})
    token = r_up.json()["access_token"]
    r_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r_me.status_code == 200
    assert r_me.json()["email"] == "me@example.com"


def test_auth_expired_or_invalid_token():
    expired = create_access_token({"sub": "user-123", "email": "exp@example.com"}, expires_delta=timedelta(seconds=-10))
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower() or "session" in r.json()["detail"].lower()

    r_bad = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert r_bad.status_code == 401


def test_trip_crud_flow():
    r_up = client.post("/api/auth/signup", json={"email": "tripper@example.com", "password": "password123"})
    token = r_up.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r_empty = client.get("/api/trips", headers=headers)
    assert r_empty.status_code == 200
    assert r_empty.json() == []

    trip_payload = {
        "destination": "Kyoto, Japan",
        "days": 3,
        "preferences": {"budget_level": "moderate", "currency": "USD"},
        "itinerary": {"title": "3 Days in Kyoto", "days": [{"day": 1, "theme": "Temples", "activities": []}]},
    }
    r_create = client.post("/api/trips", json=trip_payload, headers=headers)
    assert r_create.status_code == 201
    created_trip = r_create.json()
    assert created_trip["destination"] == "Kyoto, Japan"
    trip_id = created_trip["id"]

    r_list = client.get("/api/trips", headers=headers)
    assert len(r_list.json()) == 1
    assert r_list.json()[0]["id"] == trip_id

    r_get = client.get(f"/api/trips/{trip_id}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == trip_id

    update_payload = {"itinerary": {"title": "Updated Kyoto Tour", "days": []}}
    r_patch = client.patch(f"/api/trips/{trip_id}", json=update_payload, headers=headers)
    assert r_patch.status_code == 200
    assert r_patch.json()["itinerary"]["title"] == "Updated Kyoto Tour"

    r_del = client.delete(f"/api/trips/{trip_id}", headers=headers)
    assert r_del.status_code == 204

    r_after_del = client.get(f"/api/trips/{trip_id}", headers=headers)
    assert r_after_del.status_code == 404


def test_cross_user_trip_access_isolation():
    u1 = client.post("/api/auth/signup", json={"email": "alice@example.com", "password": "password123"}).json()
    u2 = client.post("/api/auth/signup", json={"email": "bob@example.com", "password": "password123"}).json()

    h1 = {"Authorization": f"Bearer {u1['access_token']}"}
    h2 = {"Authorization": f"Bearer {u2['access_token']}"}

    trip = client.post(
        "/api/trips",
        json={"destination": "Paris", "days": 2, "preferences": {}, "itinerary": {"title": "Alice in Paris"}},
        headers=h1,
    ).json()

    # Bob cannot view Alice's trip
    assert client.get(f"/api/trips/{trip['id']}", headers=h2).status_code == 404
    # Bob's trip list does not include Alice's trip
    assert len(client.get("/api/trips", headers=h2).json()) == 0
    # Bob cannot edit Alice's trip
    assert client.patch(f"/api/trips/{trip['id']}", json={"itinerary": {}}, headers=h2).status_code == 404
    # Bob cannot delete Alice's trip
    assert client.delete(f"/api/trips/{trip['id']}", headers=h2).status_code == 404


def test_clean_day_robustness():
    # If LLM returns string activities or non-dict objects, clean_day handles it gracefully
    raw_day = {
        "day": 1,
        "theme": "Exploration",
        "activities": ["bad activity format", {"time": "10:00", "title": "Real Place", "period": "morning"}],
    }
    cleaned = clean_day(raw_day, 1)
    assert cleaned["day"] == 1
    assert len(cleaned["activities"]) == 1
    assert cleaned["activities"][0]["title"] == "Real Place"


def test_generate_endpoint_fallback():
    u = client.post("/api/auth/signup", json={"email": "planner@example.com", "password": "password123"}).json()
    headers = {"Authorization": f"Bearer {u['access_token']}"}

    payload = {
        "destination": "Rome, Italy",
        "days": 4,
        "travelers": 2,
        "budget_level": "moderate",
        "currency": "EUR",
        "travel_style": "balanced",
        "interests": ["history", "food"],
    }
    r = client.post("/api/generate", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "Rome" in data["title"] or "Rome" in data["summary"]
    assert len(data["days"]) == 4
    assert len(data["tips"]) > 0
    # Day 1 has stay and activities
    assert len(data["days"][0]["activities"]) >= 4
    assert any(a["type"] == "stay" for a in data["days"][0]["activities"])


def test_regenerate_day_endpoint_fallback():
    u = client.post("/api/auth/signup", json={"email": "regen@example.com", "password": "password123"}).json()
    headers = {"Authorization": f"Bearer {u['access_token']}"}

    payload = {
        "day_number": 2,
        "preferences": {
            "destination": "Tokyo, Japan",
            "days": 5,
            "travelers": 1,
            "budget_level": "budget",
            "currency": "USD",
            "travel_style": "adventurous",
            "interests": ["anime", "ramen"],
        },
        "other_places": ["Shinjuku Gyoen"],
        "instruction": "Focus on Akihabara electronics and hidden ramen alleys",
    }
    r = client.post("/api/regenerate-day", json=payload, headers=headers)
    assert r.status_code == 200
    day = r.json()
    assert day["day"] == 2
    assert len(day["activities"]) >= 3

