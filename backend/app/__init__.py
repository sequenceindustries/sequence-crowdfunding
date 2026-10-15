import logging
from datetime import timedelta

import click
from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .extensions import db, limiter, migrate
from .security import enforce_csrf, hash_password


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.permanent_session_lifetime = timedelta(days=7)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    CORS(app, origins=[app.config["FRONTEND_ORIGIN"]], supports_credentials=True)

    from .api import (
        admin, auth, campaigns, deck_drafts, engagement, finance, images, payments, pitch_decks, profiles, verification, assistant,
    )

    for module in (auth, profiles, campaigns, admin, pitch_decks, finance, deck_drafts, payments, engagement,
                   verification, assistant, images):
        app.register_blueprint(module.bp)

    payments.register_cli(app)
    app.before_request(enforce_csrf)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="upload_rejected", message="The file is too large."), 413

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="not_found"), 404

    @app.errorhandler(429)
    def rate_limited(_):
        return jsonify(error="rate_limited"), 429

    @app.errorhandler(500)
    def server_error(_):
        return jsonify(error="server_error"), 500

    @app.cli.command("create-staff")
    @click.argument("email")
    @click.argument("full_name")
    @click.option("--role", type=click.Choice(["admin", "verification_reviewer"]), default="admin")
    @click.password_option()
    def create_staff(email, full_name, role, password):
        """Staff accounts are created from the command line only, never via the public API."""
        from .models import User

        db.session.add(User(email=email.lower(), full_name=full_name, role=role,
                            password_hash=hash_password(password)))
        db.session.commit()
        click.echo(f"Created {role} {email}")

    return app
