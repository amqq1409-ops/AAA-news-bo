import os
import re
import threading
import time
from datetime import date
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from analytics_engine import AnalyticsEngine
from data_store import ArticleStore
from summarizer import NewsSummarizer


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("NEWS_DB_PATH", str(ROOT / "data" / "news.db")))
CACHE_TTL_SECONDS = 30


def create_app(store=None) -> Flask:
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    article_store = store or ArticleStore(DB_PATH)
    analytics = AnalyticsEngine(article_store)
    cache: dict[str, tuple[float, Any]] = {}
    cache_lock = threading.Lock()

    def cached(key: str, builder: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with cache_lock:
            item = cache.get(key)
            if item and now - item[0] < CACHE_TTL_SECONDS:
                return item[1]
        value = builder()
        with cache_lock:
            expired = [cache_key for cache_key, (created, _) in cache.items()
                       if now - created >= CACHE_TTL_SECONDS]
            for cache_key in expired:
                del cache[cache_key]
            if len(cache) >= 128:
                cache.pop(next(iter(cache)))
            cache[key] = (now, value)
        return value

    @app.after_request
    def cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.errorhandler(Exception)
    def handle_error(error):
        if isinstance(error, HTTPException):
            return jsonify({"error": error.description}), error.code
        app.logger.exception("Dashboard request failed")
        return jsonify({"error": "Internal server error"}), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/map")
    def map_page():
        return render_template("map.html")

    @app.get("/analytics")
    def analytics_page():
        return render_template("analytics.html")

    @app.get("/search")
    def search_page():
        return render_template("search.html")

    @app.get("/api/stats")
    def stats():
        try:
            hours = int(request.args.get("hours", 24))
            if not 1 <= hours <= 8760:
                raise ValueError
        except ValueError:
            return jsonify({"error": "hours must be between 1 and 8760"}), 400
        return jsonify(cached(f"stats:{hours}", lambda: analytics.get_stats(hours)))

    @app.get("/api/countries")
    def countries():
        return jsonify(cached("countries", article_store.get_country_distribution))

    @app.get("/api/topics")
    def topics():
        return jsonify(cached("topics", article_store.get_topic_distribution))

    @app.get("/api/languages")
    def languages():
        return jsonify(cached("languages", article_store.get_language_distribution))

    @app.get("/api/sentiment")
    def sentiment():
        return jsonify(cached("sentiment", analytics.get_sentiment))

    @app.get("/api/trends")
    def trends():
        try:
            days = int(request.args.get("days", 30))
            if not 1 <= days <= 365:
                raise ValueError
        except ValueError:
            return jsonify({"error": "days must be between 1 and 365"}), 400
        period = request.args.get("period", "daily").lower()
        if period not in {"daily", "weekly", "monthly"}:
            return jsonify({"error": "period must be daily, weekly, or monthly"}), 400
        return jsonify(cached(f"trends:{days}:{period}", lambda: analytics.get_trends(days, period)))

    @app.get("/api/sources")
    def sources():
        return jsonify(cached("sources", analytics.get_sources))

    @app.get("/api/search")
    def search():
        filters = {
            key: request.args.get(key, "").strip()
            for key in (
                "q", "country", "language", "topic", "source", "start_date", "end_date",
            )
        }
        if len(filters["q"]) > 200:
            return jsonify({"error": "q must be at most 200 characters"}), 400
        for key in ("start_date", "end_date"):
            if filters[key]:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", filters[key]):
                    return jsonify({"error": f"{key} must use YYYY-MM-DD format"}), 400
                try:
                    date.fromisoformat(filters[key])
                except ValueError:
                    return jsonify({"error": f"{key} must use YYYY-MM-DD format"}), 400
        if filters["start_date"] and filters["end_date"] and filters["start_date"] > filters["end_date"]:
            return jsonify({"error": "start_date must not be after end_date"}), 400
        sentiment_label = request.args.get("sentiment", "").strip().lower()
        if sentiment_label and sentiment_label not in {"positive", "negative", "neutral"}:
            return jsonify({"error": "sentiment must be positive, negative, or neutral"}), 400
        filters["sentiment"] = sentiment_label
        source_score = request.args.get("min_source_score", "").strip()
        if source_score:
            try:
                filters["min_source_score"] = int(source_score)
                if not 0 <= filters["min_source_score"] <= 120:
                    raise ValueError
            except ValueError:
                return jsonify({"error": "min_source_score must be between 0 and 120"}), 400
        for key, default in (("limit", "50"), ("offset", "0")):
            try:
                filters[key] = int(request.args.get(key, default))
                if filters[key] < 0 or (key == "limit" and filters[key] == 0):
                    raise ValueError
            except ValueError:
                return jsonify({"error": f"{key} must be a valid non-negative integer"}), 400
        return jsonify(analytics.search(filters))

    @app.get("/api/summarize")
    def summarize():
        text = request.args.get("text", "")
        if len(text) > 5000:
            return jsonify({"error": "text must be at most 5000 characters"}), 400
        return jsonify(NewsSummarizer().summarize(text))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
        port=int(os.getenv("DASHBOARD_PORT", "5000")),
        debug=False,
    )
