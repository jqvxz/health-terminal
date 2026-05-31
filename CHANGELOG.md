## Changelog

All notable changes to **HealthTerminal** will be documented in this file.

---

## [v1.2-nutrition_beta] - 2026-05-22

### Added
- **Multi-Item Food Search**: Added support for comma-separated compound ingredient queries (e.g. `2 eggs, 100g white rice`) to automatically parse and sum up macronutrients.
- **Persistent Daily Fuel Logging**: Daily meals and food item logs are now stored persistently in the local SQLite database (`healthterminal.db`).
- **Calendar Nutrition Integration**:
  - Added cyan indicators (`.cal-dot.fuel`) to show days with logged food intake on the calendar view.
  - Day details modal now displays daily fuel metrics summary and a full breakdown table of logged meals alongside training activities.
- **AI Metabolic Health Scan Redesign**: Re-styled the health scan interface, replacing basic inputs and outputs with styled glassmorphic panels matching the main OLED/dark dashboard theme.
