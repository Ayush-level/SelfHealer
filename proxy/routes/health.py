"""Health check route."""

from flask import Blueprint, jsonify, current_app

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint returning 200 OK."""
    storage_mode = current_app.config.get("STORAGE_MODE", "prometheus")
    return jsonify({
        "status": "healthy",
        "storage_mode": storage_mode,
    }), 200
