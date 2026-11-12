from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from extensions import db
from models import FoodCategory, FoodDonation, PickupHistory, PickupRequest, User
from routes.common import notify, role_required, transition_pickup

donor_bp = Blueprint("donor", __name__, url_prefix="/donor")


def donation_form_error(donation):
    food_name = request.form.get("food_name", "").strip()
    description = request.form.get("description", "").strip()
    pickup_address = request.form.get("pickup_address", "").strip()
    try:
        category_id = int(request.form.get("category_id", ""))
        quantity = int(request.form.get("quantity", ""))
        meals = int(request.form.get("meals", ""))
        preparation_time = datetime.fromisoformat(request.form.get("preparation_time", ""))
        expiry_time = datetime.fromisoformat(request.form.get("expiry_time", ""))
    except (TypeError, ValueError):
        return "Choose a food category and enter valid quantity, meal, preparation, and expiry values."

    category = db.session.get(FoodCategory, category_id)
    if not category:
        return "Choose a valid food category."
    if (
        not food_name
        or len(food_name) > 150
        or len(description) > 2000
        or not pickup_address
        or len(pickup_address) > 1000
    ):
        return "Food name and pickup address are required."
    if not 1 <= quantity <= 100000 or not 1 <= meals <= 1000000:
        return "Quantity and meal count must be positive and within the supported limits."
    now = datetime.now()
    if preparation_time > now:
        return "Preparation time cannot be in the future."
    if preparation_time >= expiry_time or expiry_time <= now:
        return "Expiry must be after preparation and in the future."
    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()
    if bool(latitude) != bool(longitude):
        return "Enter both pickup coordinates, or leave both blank."
    try:
        lat = float(latitude) if latitude else None
        lon = float(longitude) if longitude else None
        if lat is not None and not -90 <= lat <= 90:
            raise ValueError
        if lon is not None and not -180 <= lon <= 180:
            raise ValueError
    except ValueError:
        return "Enter valid map coordinates."

    image = request.files.get("image")
    filename = donation.image_filename if donation else None
    if image and image.filename:
        safe_name = secure_filename(image.filename)
        extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
            return "Use a JPG, PNG, or WebP food image."
        filename = f"{uuid4().hex}.{extension}"
        image.save(Path(current_app.config["UPLOAD_FOLDER"]) / filename)

    donation.food_name = food_name
    donation.description = description or None
    donation.category_id = category.id
    donation.quantity = quantity
    donation.meals = meals
    donation.preparation_time = preparation_time
    donation.expiry_time = expiry_time
    donation.pickup_address = pickup_address
    donation.latitude = lat
    donation.longitude = lon
    donation.image_filename = filename
    return None


def categories():
    return FoodCategory.query.order_by(FoodCategory.name).all()


@donor_bp.route("/dashboard")
@role_required("donor")
def dashboard():
    donations = (
        FoodDonation.query.filter_by(donor_id=current_user.id)
        .order_by(FoodDonation.created_at.desc())
        .all()
    )
    pickup_requests = (
        PickupRequest.query.filter_by(donor_id=current_user.id)
        .order_by(PickupRequest.created_at.desc())
        .all()
    )
    stats = {
        "active": sum(item.status in {"available", "reserved"} for item in donations),
        "meals": sum(
            item.meals for item in PickupHistory.query.filter_by(donor_id=current_user.id)
        ),
        "requests": sum(item.status == "pending" for item in pickup_requests),
    }
    return render_template(
        "donor_dashboard.html",
        donations=donations,
        pickup_requests=pickup_requests,
        stats=stats,
    )


@donor_bp.route("/add-food", methods=["GET", "POST"])
@role_required("donor")
def add_food():
    donation = FoodDonation(
        donor_id=current_user.id,
        quantity=1,
        meals=1,
        preparation_time=datetime.now(),
        expiry_time=datetime.now(),
        pickup_address="",
    )
    if request.method == "POST":
        error = donation_form_error(donation)
        if error:
            flash(error, "danger")
        else:
            donation.status = "available"
            db.session.add(donation)
            db.session.flush()
            verified_ngos = User.query.filter_by(
                role="ngo", is_verified=True, is_active=True
            ).all()
            for ngo in verified_ngos:
                notify(
                    ngo.id,
                    "New food available",
                    f"{donation.food_name} is available for pickup in {donation.pickup_address}.",
                    "donation",
                )
            db.session.commit()
            flash("Your food donation is now listed for verified NGOs.", "success")
            return redirect(url_for("donor.dashboard"))
    return render_template("add_food.html", donation=None, categories=categories())


@donor_bp.route("/donations/<int:donation_id>/edit", methods=["GET", "POST"])
@role_required("donor")
def edit_food(donation_id):
    donation = FoodDonation.query.filter_by(
        id=donation_id, donor_id=current_user.id
    ).first_or_404()
    if donation.status != "available":
        flash("Only available donations can be edited.", "warning")
        return redirect(url_for("donor.dashboard"))
    if request.method == "POST":
        old_image = donation.image_filename
        error = donation_form_error(donation)
        if error:
            flash(error, "danger")
        else:
            if old_image and old_image != donation.image_filename:
                (Path(current_app.config["UPLOAD_FOLDER"]) / old_image).unlink(missing_ok=True)
            db.session.commit()
            flash("Donation details updated.", "success")
            return redirect(url_for("donor.dashboard"))
    return render_template("add_food.html", donation=donation, categories=categories())


@donor_bp.route("/donations/<int:donation_id>/delete", methods=["POST"])
@role_required("donor")
def delete_food(donation_id):
    donation = FoodDonation.query.filter_by(
        id=donation_id, donor_id=current_user.id
    ).first_or_404()
    if donation.status != "available":
        flash("This donation cannot be removed because it has already been reserved or completed.", "warning")
    else:
        donation.status = "withdrawn"
        for pickup in donation.pickup_requests:
            if pickup.status == "pending":
                pickup.status = "rejected"
                notify(
                    pickup.ngo_id,
                    "Donation withdrawn",
                    f"{donation.food_name} is no longer available.",
                    "pickup",
                )
        db.session.commit()
        if donation.image_filename:
            (Path(current_app.config["UPLOAD_FOLDER"]) / donation.image_filename).unlink(
                missing_ok=True
            )
        flash("Donation removed from available listings.", "success")
    return redirect(url_for("donor.dashboard"))


@donor_bp.route("/requests/<int:request_id>/<action>", methods=["POST"])
@role_required("donor")
def decide_request(request_id, action):
    pickup = PickupRequest.query.filter_by(
        id=request_id, donor_id=current_user.id
    ).first_or_404()
    if action not in {"accept", "reject"}:
        flash("Choose a valid pickup action.", "danger")
        return redirect(url_for("donor.dashboard"))
    success, message = transition_pickup(pickup, action, "donor")
    db.session.commit()
    flash(message, "success" if success else "warning")
    return redirect(url_for("donor.dashboard"))


@donor_bp.route("/profile", methods=["POST"])
@role_required("donor")
def update_profile():
    name = request.form.get("name", "").strip()
    organization = request.form.get("organization_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    if len(name) > 120 or len(organization) > 150 or len(phone) > 30 or len(address) > 2000:
        flash("One or more profile fields are too long.", "danger")
        return redirect(url_for("donor.dashboard"))
    current_user.name = name or current_user.name
    current_user.organization_name = organization or None
    current_user.phone = phone or None
    current_user.address = address or None
    db.session.commit()
    flash("Your organization profile was updated.", "success")
    return redirect(url_for("donor.dashboard"))
