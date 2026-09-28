## HealthTerminal

A simple fitness dashboard for athletes who want their data in one place.

HealthTerminal combines training, health, and nutrition data into a clean local interface without subscriptions or unnecessary bloat.

Data is collected through the separate Android app [SimpleHC](https://github.com/jqvxz/simple-hc), which connects to Android Health Connect.

## Features

- Training and activity tracking
- Running and lifting statistics
- Goals and progress tracking
- Activity calendar
- Nutrition logging
- Health Connect data
- Readiness score
- Optional AI insights
- PNG and Markdown exports
- OLED Dark and White mode

## Setup

### Requirements

- Python 3.8+
- Android device with Health Connect
- [SimpleHC](https://github.com/jqvxz/simple-hc)
- OpenRouter API key for AI features

### Installation

```bash
git clone https://github.com/jqvxz/health-terminal.git
cd health-terminal

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

On Windows:

```powershell
venv\Scripts\activate
```

Create `.env` from `.env.example` and configure it:

```env
OPENROUTER_API_KEY=your_api_key
FLASK_SECRET_KEY=your_secret_key
BASE_URL=http://localhost:5000
```

Start the application:

```bash
python app.py
```

Open `http://localhost:5000`.

## Tech Stack

- Python
- Flask
- SQLite
- Android Health Connect
- SimpleHC
- OpenRouter
- Open Food Facts

## License

MIT
