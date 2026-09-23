# Coursework dashboard — minimal end-to-end demo

What's here:
- `backend/app.py` — Flask API: tasks, calendar events, weekly stats, and three
  Claude-powered endpoints (`/api/agent/add`, `/api/agent/syllabus`,
  `/api/agent/weekly-summary`) that turn free text into structured data.
- `public/` — plain HTML + Tailwind (CDN) + Chart.js dashboard with the five
  tabs you described: School, Hobbies & chores, Calendar, This week, Lifetime
  stats.
- SQLite (`backend/data.db`) for storage — fine for one person, zero setup.

## Run it locally

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your real ANTHROPIC_API_KEY
export $(cat .env | xargs)
python app.py
```

Then open `public/index.html` in a browser (or serve it with
`python -m http.server` from inside `public/`, since it fetches `/api/...`
on the same origin — easiest is to point `API` in `app.js` at
`http://localhost:5001` if you serve the frontend separately).

## What's real vs. simplified in this first pass

- Task parsing, syllabus parsing, and the weekly summary all call the real
  Claude API — you need your own `ANTHROPIC_API_KEY`.
- "This week" and the lifetime counter aren't separate stored snapshots —
  they're just queries filtered by date, so there's no reset job to run and
  nothing to break.
- The calendar is a flat upcoming-events list, not a month grid — easy to
  upgrade once the data side is solid.
- No auth — assumes it's just you.

## Deploying like AirGuard (Vercel + Render)

**Important:** Vercel's Python functions have no persistent disk, so the
SQLite file will reset on every deploy (and possibly between invocations).
For a dashboard you'll actually rely on day to day, either:
- run the Flask backend on **Render** instead (add a persistent disk, or
  Render's free web service, which keeps the filesystem between requests as
  long as the service doesn't spin down), or
- swap SQLite for a small hosted Postgres (e.g. Supabase/Neon — both have
  free tiers) if you deploy the backend on Vercel.

`vercel.json` here is a standard Flask+static setup (`@vercel/python` for
`backend/app.py`, `@vercel/static` for `public/`). If your AirGuard project
uses Vercel's newer "Services" structure instead, mirror that same layout
here — same `public/` + `backend/` split, just a different `vercel.json`.

Either way, set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) as an
environment variable on whichever host runs the backend.

## Natural next steps

- Real month-view calendar
- Editing/deleting calendar events pulled from a syllabus (in case the AI
  gets a date wrong)
- A proper "week" concept for the summary endpoint (right now it always
  means the current Mon–Sun)
- Manual add buttons as a fallback when you don't feel like phrasing things
  for the agent
