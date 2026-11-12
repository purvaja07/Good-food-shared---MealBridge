import json
from functools import lru_cache
from datetime import datetime, timedelta
from functools import wraps
from math import asin, cos, radians, sin, sqrt
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, jsonify, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import FoodCategory, FoodDonation, Notification, PickupRequest, User
from routes.common import transition_pickup

map_bp = Blueprint("map", __name__)


@lru_cache(maxsize=128)
def lookup_address(query):
    search_queries = [query]
    normalized_query = re.sub(
        r"\b(?:taluka|taluk|tehsil|district|dist\.?)\b", "", query, flags=re.IGNORECASE
    )
    normalized_query = re.sub(r"\s+", " ", normalized_query)
    normalized_query = re.sub(r"\s*,\s*", ", ", normalized_query).strip(" ,")
    if normalized_query and normalized_query.casefold() != query.casefold():
        search_queries.append(normalized_query)

    last_error = None
    for search_query in search_queries:
        params = urlencode(
            {
                "q": search_query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "in",
            }
        )
        geocoder_url = f"https://nominatim.openstreetmap.org/search?{params}"
        geocoder_request = Request(
            geocoder_url,
            headers={
                "User-Agent": "MealBridgeFoodRescue/1.0 (local community food-rescue app)",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(geocoder_request, timeout=8) as response:
                results = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            continue
        if not results:
            continue
        result = results[0]
        return {
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
            "display_name": result.get("display_name", search_query),
        }
    if last_error:
        raise last_error
    return None


def api_roles(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify(error="Sign in to use the MealBridge map API."), 401
            if current_user.role not in roles:
                return jsonify(error="You do not have permission to use this endpoint."), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def valid_coordinate_pair(latitude, longitude):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def distance_km(lat1, lon1, lat2, lon2):
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    arc = (
        sin(lat_delta / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(arc))


def donation_payload(donation):
    return {
        "id": donation.id,
        "food_name": donation.food_name,
        "description": donation.description or "",
        "category": donation.category.name,
        "category_id": donation.category_id,
        "quantity": donation.quantity,
        "meals": donation.meals,
        "preparation_time": donation.preparation_time.isoformat(),
        "expiry_time": donation.expiry_time.isoformat(),
        "pickup_address": donation.pickup_address,
        "latitude": donation.latitude,
        "longitude": donation.longitude,
        "status": donation.status,
        "image_url": (
            url_for("static", filename=f"uploads/{donation.image_filename}")
            if donation.image_filename
            else None
        ),
        "donor_name": donation.donor.display_name,
        "detail_url": url_for("ngo.food_detail", donation_id=donation.id),
        "request_url": url_for("ngo.food_detail", donation_id=donation.id),
    }


@map_bp.route("/ngo/map")
@login_required
def food_map():
    categories = FoodCategory.query.order_by(FoodCategory.name).all()
    return render_template(
        "food_map.html",
        categories=categories,
    )


@map_bp.route("/api/donations")
@api_roles("ngo", "donor", "admin")
def api_donations():
    donations = (
        FoodDonation.query.filter_by(status="available")
        .filter(
            FoodDonation.expiry_time > datetime.now(),
            FoodDonation.latitude.isnot(None),
            FoodDonation.longitude.isnot(None),
        )
        .order_by(FoodDonation.expiry_time.asc())
        .all()
    )
    category_id = request.args.get("category", type=int)
    if category_id:
        donations = [item for item in donations if item.category_id == category_id]
    return jsonify(donations=[donation_payload(item) for item in donations])


@map_bp.route("/api/ngos")
@api_roles("ngo", "donor", "admin")
def api_ngos():
    ngos = User.query.filter_by(
        role="ngo", is_verified=True, is_active=True
    ).filter(User.latitude.isnot(None), User.longitude.isnot(None)).all()
    return jsonify(
        ngos=[
            {
                "id": ngo.id,
                "name": ngo.display_name,
                "latitude": ngo.latitude,
                "longitude": ngo.longitude,
                "address": ngo.address or "",
                "is_current_user": ngo.id == current_user.id,
            }
            for ngo in ngos
        ]
    )


@map_bp.route("/api/geocode")
@api_roles("ngo", "donor", "admin")
def api_geocode():
    query = request.args.get("q", "").strip()
    if not query or len(query) > 200:
        return jsonify(error="Enter an address or place name of up to 200 characters."), 400
    if not any(character.isalpha() for character in query):
        return jsonify(error="Enter a valid address or place name."), 400
    if "india" not in query.lower():
        query = f"{query}, India"
    try:
        result = lookup_address(query)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as error:
        current_app.logger.warning("Address lookup failed: %s", error)
        return jsonify(error="Address search is temporarily unavailable. Try again shortly."), 502
    if result is None:
        return jsonify(error="No matching address found in India. Try adding your town or district."), 404
    return jsonify(result)


@map_bp.route("/api/donations/nearby")
@api_roles("ngo", "donor")
def api_nearby_donations():
    coordinates = valid_coordinate_pair(
        request.args.get("lat", current_user.latitude),
        request.args.get("lon", current_user.longitude),
    )
    if not coordinates:
        return jsonify(error="Share your location or save valid coordinates in your NGO profile."), 400
    latitude, longitude = coordinates

    try:
        radius_km = float(request.args.get("radius_km", "20"))
        needed_quantity = int(request.args.get("needed_quantity", "1"))
        capacity = int(request.args.get("capacity", "100000"))
    except (TypeError, ValueError):
        return jsonify(error="Distance and quantity filters must be valid numbers."), 400
    if not 1 <= radius_km <= 200 or not 1 <= needed_quantity <= capacity <= 100000:
        return jsonify(error="Choose a distance from 1–200 km and a valid quantity/capacity."), 400

    category_id = request.args.get("category", type=int)
    query = FoodDonation.query.filter_by(status="available").filter(
        FoodDonation.expiry_time > datetime.now(),
        FoodDonation.latitude.isnot(None),
        FoodDonation.longitude.isnot(None),
        FoodDonation.quantity >= needed_quantity,
    )
    if category_id:
        query = query.filter(FoodDonation.category_id == category_id)

    now = datetime.now()
    matches = []
    for donation in query.all():
        distance = distance_km(
            latitude, longitude, donation.latitude, donation.longitude
        )
        if distance > radius_km:
            continue
        estimated_travel_minutes = distance / 20 * 60 + 15
        if now + timedelta(minutes=estimated_travel_minutes) >= donation.expiry_time:
            continue
        minutes_to_expiry = max(0, (donation.expiry_time - now).total_seconds() / 60)
        urgency = max(0, 1 - minutes_to_expiry / (24 * 60))
        score = distance - urgency * 1.5
        item = donation_payload(donation)
        item.update(
            {
                "distance_km": round(distance, 2),
                "estimated_travel_minutes": round(estimated_travel_minutes),
                "match_score": round(score, 3),
                "recommended_quantity": min(donation.quantity, capacity),
            }
        )
        matches.append(item)

    matches.sort(key=lambda item: (item["match_score"], item["expiry_time"]))
    return jsonify(
        donations=matches,
        matching_note=(
            "Travel time is a rough 20 km/h estimate with a 15-minute pickup buffer. "
            "It is not a food-safety guarantee; confirm safe collection with the donor."
        ),
    )


@map_bp.route("/api/pickup/request", methods=["POST"])
@api_roles("ngo")
def api_pickup_request():
    if not current_user.is_verified:
        return jsonify(error="Your NGO must be verified before requesting food."), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send the pickup details as JSON."), 400
    try:
        donation_id = int(data.get("donation_id"))
        quantity = int(data.get("quantity"))
        pickup_date = datetime.fromisoformat(str(data.get("pickup_date", "")))
    except (TypeError, ValueError):
        return jsonify(error="Enter a valid donation, quantity, and pickup time."), 400
    if pickup_date.tzinfo is not None:
        pickup_date = pickup_date.astimezone().replace(tzinfo=None)
    notes = str(data.get("notes", "")).strip()
    if len(notes) > 1000:
        return jsonify(error="Pickup notes must be 1,000 characters or fewer."), 400

    donation = db.session.get(FoodDonation, donation_id)
    if not donation:
        return jsonify(error="Food donation not found."), 404
    now = datetime.now()
    if donation.status != "available" or donation.expiry_time <= now:
        return jsonify(error="This donation is no longer available."), 409
    if not 1 <= quantity <= donation.quantity:
        return jsonify(error=f"Choose a quantity between 1 and {donation.quantity}."), 400
    if pickup_date <= now or pickup_date > donation.expiry_time:
        return jsonify(error="Pickup must be in the future and before the listed expiry."), 400

    existing = PickupRequest.query.filter(
        PickupRequest.donation_id == donation.id,
        PickupRequest.ngo_id == current_user.id,
        PickupRequest.status.in_(("pending", "accepted", "picked_up")),
    ).first()
    if existing:
        return jsonify(error="You already have an active request for this donation."), 409

    requested_meals = (
        donation.meals
        if quantity == donation.quantity
        else round(donation.meals * quantity / donation.quantity)
    )
    pickup = PickupRequest(
        donation_id=donation.id,
        ngo_id=current_user.id,
        donor_id=donation.donor_id,
        pickup_date=pickup_date,
        pickup_time=pickup_date.strftime("%H:%M"),
        status="pending",
        notes=notes or None,
        requested_quantity=quantity,
        requested_meals=requested_meals,
    )
    db.session.add(pickup)
    db.session.add(
        Notification(
            user_id=donation.donor_id,
            title="New pickup request",
            message=f"{current_user.display_name} requested {quantity} portions of {donation.food_name}.",
            type="pickup",
        )
    )
    db.session.commit()
    return jsonify(request_id=pickup.id, status=pickup.status, message="Pickup request sent."), 201


@map_bp.route("/api/pickup/requests")
@api_roles("ngo", "donor")
def api_pickup_requests():
    query = (
        PickupRequest.query.filter_by(ngo_id=current_user.id)
        if current_user.role == "ngo"
        else PickupRequest.query.filter_by(donor_id=current_user.id)
    )
    pickups = query.order_by(PickupRequest.created_at.desc()).limit(100).all()
    return jsonify(
        requests=[
            {
                "id": item.id,
                "donation_id": item.donation_id,
                "food_name": item.donation.food_name,
                "organization": (
                    item.ngo.display_name
                    if current_user.role == "donor"
                    else item.donor.display_name
                ),
                "requested_quantity": item.requested_quantity or item.donation.quantity,
                "requested_meals": (
                    item.requested_meals
                    if item.requested_meals is not None
                    else item.donation.meals
                ),
                "pickup_date": item.pickup_date.isoformat(),
                "status": item.status,
                "notes": item.notes or "",
            }
            for item in pickups
        ]
    )


@map_bp.route("/api/pickup/update", methods=["PUT"])
@api_roles("ngo", "donor")
def api_update_pickup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send the pickup update as JSON."), 400
    try:
        request_id = int(data.get("request_id"))
    except (TypeError, ValueError):
        return jsonify(error="A valid pickup request ID is required."), 400
    pickup = db.session.get(PickupRequest, request_id)
    if not pickup:
        return jsonify(error="Pickup request not found."), 404
    if current_user.role == "donor" and pickup.donor_id != current_user.id:
        return jsonify(error="You can only update requests for your donations."), 403
    if current_user.role == "ngo" and pickup.ngo_id != current_user.id:
        return jsonify(error="You can only update your organization's pickup requests."), 403

    action = str(data.get("action", ""))
    success, message = transition_pickup(pickup, action, current_user.role)
    if not success:
        db.session.commit()
        return jsonify(error=message), 409
    db.session.commit()
    return jsonify(request_id=pickup.id, status=pickup.status, message=message)
