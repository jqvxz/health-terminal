# The application will stop working for free users as soon as Strava removes acces for unpaid accounts to use their API

## HealthTerminal — V2

A fitness dashboard built for athletes who care about raw data, not bloat. HealthTerminal pulls your training and nutrition data into one clean, local interface with no subscriptions, no cloud, no distractions.

## What it does

- **Dashboard** — High-level view of your running distance, lifting sessions, and total volume in a clean brutalist grid.
- **Strava Integration** — OAuth 2.0 connection that automatically pulls your recent runs and rides.
- **Hevy Analysis** — Tracks progressive overload, max volume per session, and muscle group distribution from your lifting data.
- **Goal Tracking** — Set measurable targets (5k time, squat PR, etc.) and watch completion percentages update dynamically.
- **Activity Calendar** — Visual overview of training consistency, streaks, and frequency across all disciplines.
- **Nutrition Logging** — Natural-language food entry (e.g. `2 eggs, 100g white rice`) powered by the Open Food Facts API. Macros are aggregated and shown on the calendar.
- **Readiness Score** — A daily algorithmic score based on sleep quality, resting heart rate, training load, and step count.
- **Android Health Connect** — Sync sleep, steps, heart rate, VO2 max, and body temperature from your phone via a local webhook.
- **AI Insights** — On-demand metabolic scan and training suggestions via OpenRouter (Nemotron). Always optional, always local-context-aware.
- **Export** — Download PNG summaries or Markdown reports of your stats directly from the browser.
- **Theming** — OLED Dark and White mode, fully responsive.

## Getting started

**Prerequisites:** Python 3.8+, a Strava API account, an OpenRouter API key, and Hevy connected to Strava.

```bash
git clone https://github.com/jqvxz/health-terminal.git
cd health-terminal
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials:

```env
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
OPENROUTER_API_KEY=your_openrouter_key
FLASK_SECRET_KEY=your_secure_random_string
BASE_URL=http://localhost:5000
```

Then run:

```bash
python app.py
```

Open `http://localhost:5000`. The SQLite database initializes automatically on first launch.
