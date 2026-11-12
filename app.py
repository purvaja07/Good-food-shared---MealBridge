import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user
from sqlalchemy import inspect, text

from config import Config
from extensions import db, login_manager
from models import FoodCategory, FoodDonation, NGOVerification, Notification, User
from routes import admin_bp, auth_bp, donor_bp, ngo_bp
from routes.map import map_bp
from routes.common import expire_donations


DEFAULT_CATEGORIES = (
    "Cooked meals",
    "Bakery",
    "Produce",
    "Dairy",
    "Packaged food",
    "Other",
)


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or Config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(donor_bp)
    app.register_blueprint(ngo_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(map_bp)

    with app.app_context():
        db.create_all()
        ensure_schema_compatibility()
        for category_name in DEFAULT_CATEGORIES:
            if not FoodCategory.query.filter_by(name=category_name).first():
                db.session.add(FoodCategory(name=category_name))
        db.session.commit()

    @app.before_request
    def protect_forms_and_refresh_expiry():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("_csrf_token", "")
            supplied = request.form.get("_csrf_token", "") or request.headers.get(
                "X-CSRF-Token", ""
            )
            if not expected or not secrets.compare_digest(expected, supplied):
                abort(400, description="The form expired or could not be verified. Please try again.")
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("Your account is currently disabled.", "warning")
            return redirect(url_for("auth.login"))
        if request.method == "GET" and request.endpoint != "static":
            expire_donations()

    @app.context_processor
    def inject_template_helpers():
        def csrf_token():
            if "_csrf_token" not in session:
                session["_csrf_token"] = secrets.token_urlsafe(32)
            return session["_csrf_token"]

        unread_count = 0
        recent_notifications = []
        if current_user.is_authenticated:
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
            recent_notifications = (
                Notification.query.filter_by(user_id=current_user.id)
                .order_by(Notification.created_at.desc())
                .limit(5)
                .all()
            )
        return {
            "csrf_token": csrf_token,
            "unread_notification_count": unread_count,
            "recent_notifications": recent_notifications,
        }

    @app.errorhandler(400)
    def bad_request(error):
        return render_template(
            "error.html", code=400, message=getattr(error, "description", "Invalid request.")
        ), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template(
            "error.html", code=403, message="You do not have permission to view this page."
        ), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template(
            "error.html", code=404, message="The page or record you requested could not be found."
        ), 404

    @app.errorhandler(413)
    def request_too_large(_error):
        return render_template(
            "error.html", code=413, message="That upload is too large. Food images must be 5 MB or less."
        ), 413

    @app.cli.command("create-admin")
    def create_admin():
        """Create an administrator account without public admin signup."""
        name = click.prompt("Administrator name").strip()
        email = click.prompt("Administrator email").strip().lower()
        password = click.prompt(
            "Password (at least 10 characters)",
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 10:
            raise click.ClickException("Password must contain at least 10 characters.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("An account already uses that email.")
        admin = User(
            name=name,
            email=email,
            role="admin",
            is_verified=True,
            is_active=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Administrator account created for {email}.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add demonstration accounts and sample food (development only)."""
        donor_email = "donor@mealbridge.local"
        ngo_email = "ngo@mealbridge.local"
        donor = User.query.filter_by(email=donor_email).first()
        if not donor:
            donor = User(
                name="Asha Rao",
                email=donor_email,
                role="donor",
                organization_name="Green Bowl Kitchen",
                phone="+91 98765 43210",
                address="Muktainagar, Jalgaon, Maharashtra, India",
                latitude=21.04655,
                longitude=76.05938,
                is_verified=True,
            )
            donor.set_password("MealBridgeDemo!2026")
            db.session.add(donor)
        ngo = User.query.filter_by(email=ngo_email).first()
        if not ngo:
            ngo = User(
                name="Community Meals Team",
                email=ngo_email,
                role="ngo",
                organization_name="Muktainagar Community Meals",
                phone="+91 98765 12345",
                address="Muktainagar, Jalgaon, Maharashtra, India",
                latitude=21.04655,
                longitude=76.05938,
                is_verified=True,
            )
            ngo.set_password("MealBridgeDemo!2026")
            db.session.add(ngo)
            db.session.flush()
            db.session.add(NGOVerification(ngo_id=ngo.id, status="verified"))
        donor.address = "Muktainagar, Jalgaon, Maharashtra, India"
        donor.latitude = 21.04655
        donor.longitude = 76.05938
        ngo.organization_name = "Muktainagar Community Meals"
        ngo.address = "Muktainagar, Jalgaon, Maharashtra, India"
        ngo.latitude = 21.04655
        ngo.longitude = 76.05938
        ngo.is_verified = True
        if not NGOVerification.query.filter_by(ngo_id=ngo.id).first():
            db.session.add(NGOVerification(ngo_id=ngo.id, status="verified"))
        db.session.flush()
        sample_donation = FoodDonation.query.filter_by(
            donor_id=donor.id, food_name="Fresh vegetable biryani"
        ).first()
        if not sample_donation:
            category = FoodCategory.query.filter_by(name="Cooked meals").first()
            now = datetime.now()
            sample_donation = FoodDonation(
                donor_id=donor.id,
                category_id=category.id,
                food_name="Fresh vegetable biryani",
                description="Freshly prepared, safely packed vegetarian meals.",
                quantity=24,
                meals=24,
                preparation_time=now - timedelta(minutes=45),
                expiry_time=now + timedelta(hours=5),
                pickup_address="Muktainagar, Jalgaon, Maharashtra, India",
                latitude=21.04655,
                longitude=76.05938,
                status="available",
            )
            db.session.add(sample_donation)
        else:
            sample_donation.pickup_address = "Muktainagar, Jalgaon, Maharashtra, India"
            sample_donation.latitude = 21.04655
            sample_donation.longitude = 76.05938
            if sample_donation.status == "expired":
                now = datetime.now()
                sample_donation.preparation_time = now - timedelta(minutes=45)
                sample_donation.expiry_time = now + timedelta(hours=5)
                sample_donation.status = "available"
        db.session.commit()
        click.echo(
            "Demo data is ready. Both donor@mealbridge.local and ngo@mealbridge.local use "
            "MealBridgeDemo!2026. Change or remove these accounts before deployment."
        )

    return app


def ensure_schema_compatibility():
    """Add the account-status column to databases created by earlier MealBridge versions."""
    additions = {
        "users": {"is_active": "BOOLEAN NOT NULL DEFAULT 1"},
        "pickup_requests": {
            "requested_quantity": "INTEGER",
            "requested_meals": "INTEGER",
        },
        "pickup_history": {
            "quantity": "INTEGER NOT NULL DEFAULT 0",
            "meals": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    with db.engine.begin() as connection:
        for table_name, columns_to_add in additions.items():
            existing_columns = {
                column["name"] for column in inspect(db.engine).get_columns(table_name)
            }
            for column_name, column_definition in columns_to_add.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN "
                            f"{column_name} {column_definition}"
                        )
                    )


app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true"},
    )
