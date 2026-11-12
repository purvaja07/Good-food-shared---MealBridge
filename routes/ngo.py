from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from extensions import db
from models import FoodCategory, FoodDonation, PickupHistory, PickupRequest
from routes.common import notify, role_required, transition_pickup

ngo_bp = Blueprint("ngo", __name__, url_prefix="/ngo")


def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    value = (
        sin(lat_delta / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    )
    return 2 * radius * asin(sqrt(value))


@ngo_bp.route("/dashboard")
@role_required("ngo")
def dashboard():
    pickups = (
        PickupRequest.query.filter_by(ngo_id=current_user.id)
        .order_by(PickupRequest.created_at.desc())
        .all()
    )
    stats = {
        "active": sum(item.status in {"pending", "accepted", "picked_up"} for item in pickups),
        "meals": sum(
            item.meals for item in PickupHistory.query.filter_by(ngo_id=current_user.id)
        ),
        "completed": sum(item.status == "completed" for item in pickups),
    }
    return render_template("ngo_dashboard.html", pickups=pickups, stats=stats)


@ngo_bp.route("/food")
@role_required("ngo")
def available_food():
    from routes.common import expire_donations

    expire_donations()
    query = FoodDonation.query.filter_by(status="available").filter(
        FoodDonation.expiry_time > datetime.now()
    )
    search = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                FoodDonation.food_name.ilike(pattern),
                FoodDonation.description.ilike(pattern),
                FoodDonation.pickup_address.ilike(pattern),
            )
        )
    if category_id.isdigit():
        query = query.filter(FoodDonation.category_id == int(category_id))
    donations = query.order_by(FoodDonation.expiry_time.asc()).all()

    radius = 0
    radius_value = request.args.get("distance", "").strip()
    if radius_value:
        try:
            radius = float(radius_value)
            if not 1 <= radius <= 200:
                raise ValueError
        except ValueError:
            radius = 0
            flash("Distance must be between 1 and 200 km.", "warning")
    has_location = current_user.latitude is not None and current_user.longitude is not None
    if radius > 0 and has_location:
        donations = [
            item
            for item in donations
            if item.latitude is not None
            and item.longitude is not None
            and distance_km(
                current_user.latitude,
                current_user.longitude,
                item.latitude,
                item.longitude,
            )
            <= radius
        ]
    map_markers = [
        {
            "lat": item.latitude,
            "lon": item.longitude,
            "name": item.food_name,
            "address": item.pickup_address,
            "url": url_for("ngo.food_detail", donation_id=item.id),
        }
        for item in donations
        if item.latitude is not None and item.longitude is not None
    ]
    return render_template(
        "available_food.html",
        donations=donations,
        categories=FoodCategory.query.order_by(FoodCategory.name).all(),
        search=search,
        category_id=category_id,
        radius=radius,
        has_location=has_location,
        map_markers=map_markers,
    )


@ngo_bp.route("/food/<int:donation_id>")
@role_required("ngo")
def food_detail(donation_id):
    donation = FoodDonation.query.filter_by(id=donation_id).first_or_404()
    accepted_pickup = PickupRequest.query.filter_by(
        donation_id=donation.id, ngo_id=current_user.id, status="accepted"
    ).first()
    return render_template(
        "food_detail.html",
        donation=donation,
        now=datetime.now(),
        accepted_pickup=accepted_pickup,
    )


@ngo_bp.route("/food/<int:donation_id>/request", methods=["POST"])
@role_required("ngo")
def request_pickup(donation_id):
    donation = FoodDonation.query.filter_by(id=donation_id).first_or_404()
    if not current_user.is_verified:
        flash("Your NGO must be verified before requesting food.", "warning")
        return redirect(url_for("ngo.food_detail", donation_id=donation.id))
    if donation.status != "available" or donation.expiry_time <= datetime.now():
        flash("This donation is no longer available.", "warning")
        return redirect(url_for("ngo.available_food"))
    try:
        pickup_date = datetime.fromisoformat(request.form.get("pickup_date", ""))
    except (TypeError, ValueError):
        flash("Choose a valid pickup date and time.", "danger")
        return redirect(url_for("ngo.food_detail", donation_id=donation.id))
    if pickup_date <= datetime.now() or pickup_date > donation.expiry_time:
        flash("Pickup must be in the future and no later than the food expiry.", "danger")
        return redirect(url_for("ngo.food_detail", donation_id=donation.id))
    try:
        requested_quantity = int(request.form.get("quantity", donation.quantity))
    except (TypeError, ValueError):
        flash("Enter a valid pickup quantity.", "danger")
        return redirect(url_for("ngo.food_detail", donation_id=donation.id))
    if not 1 <= requested_quantity <= donation.quantity:
        flash(f"Choose a quantity between 1 and {donation.quantity}.", "danger")
        return redirect(url_for("ngo.food_detail", donation_id=donation.id))
    requested_meals = (
        donation.meals
        if requested_quantity == donation.quantity
        else round(donation.meals * requested_quantity / donation.quantity)
    )
    existing = PickupRequest.query.filter(
        PickupRequest.donation_id == donation.id,
        PickupRequest.ngo_id == current_user.id,
        PickupRequest.status.in_(("pending", "accepted", "picked_up")),
    ).first()
    if existing:
        flash("You already have an active request for this food.", "info")
        return redirect(url_for("ngo.dashboard"))

    pickup = PickupRequest(
        donation_id=donation.id,
        ngo_id=current_user.id,
        donor_id=donation.donor_id,
        pickup_date=pickup_date,
        pickup_time=pickup_date.strftime("%H:%M"),
        notes=request.form.get("notes", "").strip() or None,
        requested_quantity=requested_quantity,
        requested_meals=requested_meals,
        status="pending",
    )
    db.session.add(pickup)
    notify(
        donation.donor_id,
        "New pickup request",
        f"{current_user.display_name} requested {donation.food_name}.",
        "pickup",
    )
    db.session.commit()
    flash("Pickup request sent to the donor.", "success")
    return redirect(url_for("ngo.dashboard"))


@ngo_bp.route("/requests/<int:request_id>/status", methods=["POST"])
@role_required("ngo")
def update_pickup_status(request_id):
    pickup = PickupRequest.query.filter_by(
        id=request_id, ngo_id=current_user.id
    ).first_or_404()
    action = request.form.get("action")
    success, message = transition_pickup(pickup, action, "ngo")
    db.session.commit()
    flash(message, "success" if success else "warning")
    return redirect(url_for("ngo.dashboard"))


@ngo_bp.route("/profile", methods=["POST"])
@role_required("ngo")
def update_profile():
    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()
    if bool(latitude) != bool(longitude):
        flash("Enter both latitude and longitude, or leave both blank.", "danger")
        return redirect(url_for("ngo.dashboard"))
    try:
        lat = float(latitude) if latitude else None
        lon = float(longitude) if longitude else None
        if lat is not None and not -90 <= lat <= 90:
            raise ValueError
        if lon is not None and not -180 <= lon <= 180:
            raise ValueError
    except ValueError:
        flash("Enter valid map coordinates.", "danger")
        return redirect(url_for("ngo.dashboard"))
    name = request.form.get("name", "").strip()
    organization = request.form.get("organization_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    if (
        len(name) > 120
        or len(organization) > 150
        or len(phone) > 30
        or len(address) > 2000
    ):
        flash("One or more profile fields are too long.", "danger")
        return redirect(url_for("ngo.dashboard"))
    current_user.name = name or current_user.name
    current_user.organization_name = organization or current_user.organization_name
    current_user.phone = phone or None
    current_user.address = address or None
    current_user.latitude = lat
    current_user.longitude = lon
    db.session.commit()
    flash("Your organization profile was updated.", "success")
    return redirect(url_for("ngo.dashboard"))
