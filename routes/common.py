from datetime import datetime
from functools import wraps

from flask import abort
from flask_login import current_user, login_required
from sqlalchemy import update

from extensions import db
from models import FoodDonation, Notification, PickupHistory, PickupRequest


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def notify(user_id, title, message, notification_type="general"):
    db.session.add(
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
        )
    )


def expire_donations():
    expired = FoodDonation.query.filter(
        FoodDonation.status.in_(("available", "reserved")),
        FoodDonation.expiry_time <= datetime.now(),
    ).all()
    for donation in expired:
        donation.status = "expired"
        for pickup in donation.pickup_requests:
            if pickup.status in {"pending", "accepted"}:
                pickup.status = "rejected"
                notify(
                    pickup.ngo_id,
                    "Food donation expired",
                    f"{donation.food_name} passed its expiry time and can no longer be collected.",
                    "pickup",
                )
                notify(
                    pickup.donor_id,
                    "Food donation expired",
                    f"{donation.food_name} passed its expiry time.",
                    "donation",
                )
    db.session.commit()


def transition_pickup(pickup, action, actor_role):
    donation = pickup.donation
    if actor_role == "donor" and action == "reject":
        if pickup.status != "pending":
            return False, "This pickup request can no longer be changed."
        pickup.status = "rejected"
        notify(
            pickup.ngo_id,
            "Pickup request declined",
            f"Your request for {donation.food_name} was declined by the donor.",
            "pickup",
        )
        return True, "Pickup request declined."

    if actor_role == "donor" and action == "accept":
        if pickup.status != "pending":
            return False, "This pickup request can no longer be changed."
        now = datetime.now()
        quantity = pickup.requested_quantity or donation.quantity
        reserved = db.session.execute(
            update(FoodDonation)
            .where(
                FoodDonation.id == donation.id,
                FoodDonation.status == "available",
                FoodDonation.expiry_time > now,
                FoodDonation.quantity >= quantity,
            )
            .values(status="reserved")
            .execution_options(synchronize_session=False)
        )
        if reserved.rowcount != 1:
            if donation.status == "available" and donation.expiry_time <= now:
                donation.status = "expired"
            pickup.status = "rejected"
            notify(
                pickup.ngo_id,
                "Food is no longer available",
                f"{donation.food_name} can no longer be reserved.",
                "pickup",
            )
            return False, "This donation is no longer available in the requested quantity."

        pickup.status = "accepted"
        donation.status = "reserved"
        for other in PickupRequest.query.filter(
            PickupRequest.donation_id == donation.id,
            PickupRequest.id != pickup.id,
            PickupRequest.status == "pending",
        ).all():
            other.status = "rejected"
            notify(
                other.ngo_id,
                "Food request update",
                "Another pickup request was accepted.",
                "pickup",
            )
        notify(
            pickup.ngo_id,
            "Pickup request accepted",
            f"Your request for {donation.food_name} was accepted. Check your dashboard for pickup details.",
            "pickup",
        )
        return True, "Pickup request accepted."

    if actor_role == "ngo" and action == "picked_up":
        if pickup.status != "accepted":
            return False, "This pickup cannot move to that status."
        if donation.expiry_time <= datetime.now():
            donation.status = "expired"
            pickup.status = "rejected"
            notify(
                pickup.ngo_id,
                "Food donation expired",
                f"{donation.food_name} passed its expiry time before collection.",
                "pickup",
            )
            notify(
                pickup.donor_id,
                "Food donation expired",
                f"{donation.food_name} passed its expiry time before collection.",
                "donation",
            )
            return False, "This food has expired and cannot be marked as collected."
        pickup.status = "picked_up"
        notify(
            pickup.donor_id,
            "Food pickup in progress",
            f"{pickup.ngo.display_name} has collected {donation.food_name}.",
            "pickup",
        )
        return True, "Pickup marked as collected."

    if actor_role == "ngo" and action == "completed":
        if pickup.status != "picked_up" or donation.status != "reserved":
            return False, "This pickup cannot be completed in its current state."
        quantity = pickup.requested_quantity or donation.quantity
        meals = pickup.requested_meals
        if meals is None:
            meals = (
                donation.meals
                if quantity >= donation.quantity
                else round(donation.meals * quantity / donation.quantity)
            )
        if quantity > donation.quantity or quantity < 1:
            return False, "The requested quantity is no longer available."

        pickup.status = "completed"
        donation.quantity -= quantity
        donation.meals = max(0, donation.meals - meals)
        donation.status = (
            "available"
            if donation.quantity > 0 and donation.expiry_time > datetime.now()
            else "completed"
        )
        db.session.add(
            PickupHistory(
                donation_id=pickup.donation_id,
                ngo_id=pickup.ngo_id,
                donor_id=pickup.donor_id,
                notes=pickup.notes,
                quantity=quantity,
                meals=meals,
            )
        )
        notify(
            pickup.donor_id,
            "Food pickup completed",
            f"{pickup.ngo.display_name} completed pickup of {quantity} portions of {donation.food_name}.",
            "pickup",
        )
        return True, "Pickup completed and the remaining donation quantity was updated."

    return False, "This pickup cannot move to that status."
