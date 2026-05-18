# HealthTerminal — V1

## 1. Product / Program Description
**Health Terminal** is the new version of the previously released program "HealthPanel". The program includes more functionality as well as a better UI. It utilizes Strava and Hevy to track and display fitness data. It is also built on a significantly more efficient and advanced backend system. The program runs locally on your machine, ensuring your data remains safe and secure. AI assistance is always optional and can be used for fitness, nutrition, and recovery insights by simply pressing a button or asking a specific question about your fitness, nutrition, or recovery. 

## 2. Purpose
The purpose of HealthTerminal is to provide users with an uncompromising, no-nonsense overview of their physical performance. It eliminates the clutter found in typical fitness applications by focusing purely on raw data, progressive overload, and goal tracking. It is built for athletes who demand precision and efficiency from their tools, without unnecessary distractions. The AI is specifically optimized to filter out misleading information, such as claims that soy milk supports men's testosterone levels or that seed oils are beneficial for health.

## 3. Functionality
- **Dashboard & Performance Overview:** High-level metrics for running distance, lifting sessions, and total volume lifted, organized in a clear, brutalist grid.
- **Strava Integration:** Secure OAuth 2.0 connection to automatically pull and parse recent running and cycling activities.
- **Hevy Analysis & Logging:** Native support for strength training data, focusing on progressive overload, max volume, and muscle group distribution.
- **Goal Tracking & Progression:** Define custom, measurable goals (e.g., target 5k time, lifting milestones) and visually track completion percentages dynamically.
- **Activity Calendar:** A robust calendar view for tracking daily activity streaks, workout consistency, and training frequency across different disciplines.
- **Detailed Analytics:** Granular breakdown of individual workouts, highlighting personal bests, heart rate zones, and volume shifts over time.
- **Export Capabilities:** Generate shareable, high-fidelity PNG image summaries of performance statistics directly from the browser, along with Markdown exports for documentation.
- **Responsive Theming:** Includes multiple CSS variable-based themes (e.g., OLED Dark, White mode) built with a responsive grid to accommodate both desktop and mobile viewing.
- **Supplementary AI Insights:** A secondary, on-demand feature that utilizes the OpenRouter API (Nemotron) to offer quick nutritional recaps or training volume suggestions based on locally tracked data.

## 4. Setup Instructions

### Prerequisites
- **Python 3.8+**
- A **Strava API** account (Client ID & Secret)
- An **OpenRouter API** key
- **Hevy linked to Strava:** Ensure your Hevy app is connected to Strava so your lifting sessions are automatically synced and ingested.

### Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/jqvxz/health-terminal.git
   cd health-terminal
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   - Copy the `.env.example` file and rename it to `.env`.
   - Fill in your API credentials:
     ```env
     STRAVA_CLIENT_ID=your_client_id
     STRAVA_CLIENT_SECRET=your_client_secret
     OPENROUTER_API_KEY=your_openrouter_key
     FLASK_SECRET_KEY=your_secure_random_string
     BASE_URL=http://localhost:5000
     ```

5. **Run the Application:**
   ```bash
   python app.py
   ```
   *The app will automatically initialize the local SQLite database (`healthterminal.db`) on startup.*

6. **Access the App:**
   Open your browser and navigate to `http://localhost:5000`.

## 5. Project Structure

The project follows a standard Flask factory/modular structure:

```text
ht-terminal/
│
├── app.py                  # Main Flask application entry point
├── config.py               # Global configurations, prompts, and constants
├── requirements.txt        # Python package dependencies
├── .env                    # Secret environment variables (API keys)
│
├── models/                 # Database Layer
│   └── db.py               # SQLite connection management and queries
│
├── routes/                 # API & View Endpoints
│   ├── ai.py               # OpenRouter / AI integration endpoints
│   ├── strava.py           # OAuth flow and Strava webhook handlers
│   └── goals.py            # CRUD operations for user progress goals
│
├── services/               # Core Logic & Data Ingestion
│   ├── strava_parser.py    # Parsing Strava payload data into DB schema
│   └── nutrition.py        # Caloric and nutritional math/logic
│
├── static/                 # Client-Side Assets
│   ├── css/
│   │   └── style.css       # Core design system and theme variables
│   └── js/
│       └── app.js          # Interactive frontend logic, charts, and exports
│
└── templates/              # Jinja2 HTML Views
    ├── base.html           # Main application layout and sidebar
    ├── dashboard.html      # Primary data overview
    ├── recommendations.html# AI insight interactions
    └── export.html         # Custom data extraction views
```

## 6. Contact
- **GitHub:** [https://github.com/jqvxz](https://github.com/jqvxz)
- **Website:** [https://javon-web.de](https://javon-web.de)
