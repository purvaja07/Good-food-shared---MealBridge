import re
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func

from extensions import db
from models import FoodDonation, NGOVerification, PickupHistory, User

auth_bp = Blueprint("auth", __name__)


def valid_coordinates(latitude, longitude):
    if not latitude and not longitude:
        return None, None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Enter valid map coordinates or leave both blank.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("The latitude or longitude is outside the valid range.")
    return lat, lon


@auth_bp.route("/")
def home():
    stats = {
        "donations": FoodDonation.query.count(),
        "meals": db.session.query(func.coalesce(func.sum(PickupHistory.meals), 0)).scalar(),
        "ngos": User.query.filter_by(role="ngo", is_verified=True, is_active=True).count(),
        "donors": User.query.filter_by(role="donor", is_active=True).count(),
    }
    if stats["meals"] == 0:
        stats["meals"] = (
            db.session.query(func.coalesce(func.sum(FoodDonation.meals), 0))
            .filter(FoodDonation.status == "completed")
            .scalar()
        )
    stats["pickups"] = PickupHistory.query.count()
    stats["waste_kg"] = round(stats["meals"] * 0.5, 1)
    recent = (
        FoodDonation.query.filter_by(status="available")
        .filter(FoodDonation.expiry_time > datetime.now())
        .order_by(FoodDonation.expiry_time.asc())
        .limit(3)
        .all()
    )
    return render_template("index.html", stats=stats, recent=recent)


@auth_bp.route("/about")
def about():
    return render_template("about.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        organization = request.form.get("organization_name", "").strip()
        role = request.form.get("role", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if (
            not name
            or len(name) > 120
            or len(email) > 120
            or len(organization) > 150
            or len(phone) > 30
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            flash("Enter your name and a valid email address.", "danger")
        elif role not in {"donor", "ngo"}:
            flash("Choose Food Donor or NGO / Receiver.", "danger")
        elif len(password) < 10:
            flash("Use a password with at least 10 characters.", "danger")
        elif role == "ngo" and not organization:
            flash("Enter the NGO / organization name.", "danger")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account already uses that email address.", "danger")
        else:
            try:
                latitude, longitude = valid_coordinates(
                    request.form.get("latitude", "").strip(),
                    request.form.get("longitude", "").strip(),
                )
            except ValueError as error:
                flash(str(error), "danger")
                return render_template("register.html")

            user = User(
                name=name,
                email=email,
                role=role,
                organization_name=organization or None,
                phone=phone or None,
                address=address or None,
                latitude=latitude,
                longitude=longitude,
                is_verified=(role == "donor"),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            if role == "ngo":
                db.session.add(NGOVerification(ngo_id=user.id, status="pending"))
            db.session.commit()
            login_user(user)
            flash(
                "Your account is ready. An administrator will verify your organization."
                if role == "ngo"
                else "Welcome to MealBridge. You can now share surplus food.",
                "success",
            )
            return redirect(url_for("auth.dashboard"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not user.check_password(password):
            flash("Email or password is incorrect.", "danger")
        elif not user.is_active:
            flash("This account is currently disabled. Contact an administrator.", "danger")
        else:
            login_user(user)
            flash("Welcome back.", "success")
            return redirect(url_for("auth.dashboard"))
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.home"))


@auth_bp.route("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.role == "donor":
        return redirect(url_for("donor.dashboard"))
    if current_user.role == "ngo":
        return redirect(url_for("ngo.dashboard"))
    return redirect(url_for("admin.dashboard"))


@auth_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    from models import Notification

    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for("auth.dashboard"))


@auth_bp.route("/report", methods=["POST"])
def submit_report():
    from models import Report

    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    subject = request.form.get("subject", "").strip()
    details = request.form.get("details", "").strip()
    if not subject or not details or len(subject) > 150 or len(details) > 5000:
        flash("Add a subject and details for your report.", "danger")
    else:
        db.session.add(Report(reporter_id=current_user.id, subject=subject, details=details))
        db.session.commit()
        flash("Thanks. Your report has been sent to the MealBridge team.", "success")
    return redirect(request.referrer or url_for("auth.dashboard"))
