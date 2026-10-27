# Wayfare – Personalized Travel Itinerary Planner

An AI-powered full-stack web app that turns a destination, budget and interests into an editable day-by-day itinerary.

**Stack:** React + Vite (frontend, Vercel) · FastAPI (backend, Render) · Supabase (database + auth) · Groq Llama 3.3 (generative AI) · Unsplash (images)

## Features
- Email sign up / sign in (Supabase Auth)
- Preference form: destination, days, travelers, budget level and amount, pace, interests, notes
- AI-generated itinerary: attractions, meals, stay and transport, each with time, location and estimated cost
- Photos for every day via Unsplash, Google Maps link for every stop
- Edit any stop, add or remove stops, rebuild a single day with your own instruction
- Trips saved per user (Supabase Row Level Security), re-open or delete any time
- Download as PDF (browser print)

## Architecture
```
User -> React (Vercel) <-> FastAPI (Render) -> Supabase (DB + Auth)
                                            -> Groq (Generative AI)
                                            -> Unsplash (Images)
```
The frontend signs in through Supabase and sends the user's access token to FastAPI. FastAPI validates the token, calls Groq/Unsplash, and reads/writes the `trips` table using that same token, so Row Level Security guarantees users only see their own trips.

## Setup (local)

### 1. Get the keys
| Service | Where | What you need |
|---|---|---|
| Supabase | supabase.com -> New project | Project URL and `anon` public key (Settings -> API) |
| Groq | console.groq.com -> API Keys | API key |
| Unsplash | unsplash.com/developers -> New application | Access Key |

### 2. Database
Supabase -> SQL Editor -> paste `backend/schema.sql` -> Run.
For easy testing, turn off *Authentication -> Providers -> Email -> Confirm email*.

### 3. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
uvicorn main:app --reload --port 8000
```
Check http://localhost:8000/health and http://localhost:8000/docs.

### 4. Frontend
```bash
cd frontend
npm install
cp .env.example .env        # fill in Supabase URL, anon key, API URL
npm run dev
```
Open http://localhost:5173.

## Deployment
1. **Backend (Render):** New Web Service from your GitHub repo, root directory `backend`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT` (or use `render.yaml`). Add the env vars from `.env.example`.
2. **Frontend (Vercel):** Import the repo, root directory `frontend`, framework Vite. Add `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (your Render URL).
3. Back on Render set `FRONTEND_ORIGINS` to your Vercel URL (no trailing slash) and redeploy.
4. Supabase -> Authentication -> URL Configuration: set Site URL to your Vercel URL.

Note: Render's free tier sleeps when idle, so the first request can take ~30 seconds.

## API
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/generate` | Generate an itinerary from preferences |
| POST | `/api/regenerate-day` | Rebuild one day |
| GET/POST | `/api/trips` | List / create saved trips |
| GET/PUT/DELETE | `/api/trips/{id}` | Read / update / delete a trip |

## Test checklist (Epic 7)
- [ ] Sign up, sign out, sign in
- [ ] Generate a 3-day trip; every day has 4-6 stops with costs
- [ ] Edit a stop and save; refresh and confirm it persisted
- [ ] Rebuild a day with an instruction
- [ ] Create a second account and confirm it cannot see the first account's trips
- [ ] Delete a trip
- [ ] Download PDF on desktop and check the layout on a phone

## Project structure
```
wayfare/
  backend/   main.py, schema.sql, requirements.txt, .env.example
  frontend/  src/App.jsx, Planner.jsx, Itinerary.jsx, api.js, supabase.js, styles.css
  render.yaml
```
