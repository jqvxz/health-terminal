"""
HealthTerminal V1 — Flask Application Factory
Main entry point for the web application.
"""

from flask import Flask, render_template, jsonify
from config import Config
from models.db import init_db, get_all_settings, get_setting


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    # Initialize database
    with app.app_context():
        init_db()

    # Register blueprints
    from routes.strava import strava_bp
    from routes.ai import ai_bp
    from routes.export import export_bp
    from routes.goals import goals_bp
    from routes.settings import settings_bp

    app.register_blueprint(strava_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(settings_bp)

    # Page routes
    @app.route("/")
    def index():
        settings = get_all_settings()
        return render_template("dashboard.html", settings=settings, active_tab="dashboard")

    @app.route("/running")
    def running():
        settings = get_all_settings()
        return render_template("running.html", settings=settings, active_tab="running")

    @app.route("/lifting")
    def lifting():
        settings = get_all_settings()
        return render_template("lifting.html", settings=settings, active_tab="lifting")

    @app.route("/progress")
    def progress():
        settings = get_all_settings()
        return render_template("progress.html", settings=settings, active_tab="progress")

    @app.route("/recommendations")
    def recommendations():
        settings = get_all_settings()
        return render_template("recommendations.html", settings=settings, active_tab="recommendations")

    @app.route("/calendar")
    def calendar():
        settings = get_all_settings()
        return render_template("calendar.html", settings=settings, active_tab="calendar")

    @app.route("/export")
    def export_page():
        settings = get_all_settings()
        return render_template("export.html", settings=settings, active_tab="export")

    @app.route("/settings")
    def settings_page():
        settings = get_all_settings()
        return render_template("settings.html", settings=settings, active_tab="settings")

    @app.route("/mobile")
    def mobile_page():
        return render_template("mobile.html")

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("base.html", settings=get_all_settings(),
                               active_tab="", error="Page not found"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("base.html", settings=get_all_settings(),
                               active_tab="", error="Internal server error"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
