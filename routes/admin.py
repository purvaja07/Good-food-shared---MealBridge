from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from extensions import db
from models import FoodDonation, NGOVerification, PickupHistory, Report, User
from routes.common import notify, role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@role_required("admin")
def dashboard():
    completed_meals = db.session.query(
        func.coalesce(func.sum(PickupHistory.meals), 0)
    ).scalar()
    if completed_meals == 0:
        completed_meals = (
            db.session.query(func.coalesce(func.sum(FoodDonation.meals), 0))
            .filter(FoodDonation.status == "completed")
            .scalar()
        )
    stats = {
        "donors": User.query.filter_by(role="donor").count(),
        "ngos": User.query.filter_by(role="ngo").count(),
        "pending_ngos": NGOVerification.query.filter_by(status="pending").count(),
        "donations": FoodDonation.query.count(),
        "available": FoodDonation.query.filter_by(status="available").count(),
        "pickups": PickupHistory.query.count(),
        "reports": Report.query.filter_by(status="open").count(),
        "meals": completed_meals,
        "waste_kg": round(completed_meals * 0.5, 1),
    }
    users = User.query.order_by(User.created_at.desc()).limit(100).all()
    verifications = (
        NGOVerification.query.filter(NGOVerification.status != "verified")
        .order_by(NGOVerification.created_at.asc())
        .all()
    )
    reports = Report.query.order_by(Report.created_at.desc()).limit(100).all()
    donations = FoodDonation.query.order_by(FoodDonation.created_at.desc()).limit(50).all()
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        users=users,
        verifications=verifications,
        reports=reports,
        donations=donations,
    )


@admin_bp.route("/ngos/<int:ngo_id>/verify", methods=["POST"])
@role_required("admin")
def verify_ngo(ngo_id):
    ngo = User.query.filter_by(id=ngo_id, role="ngo").first_or_404()
    verification = NGOVerification.query.filter_by(ngo_id=ngo.id).first()
    if not verification:
        verification = NGOVerification(ngo_id=ngo.id, status="pending")
        db.session.add(verification)
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        flash("Choose a valid verification action.", "danger")
        return redirect(url_for("admin.dashboard"))
    verification.status = "verified" if action == "approve" else "rejected"
    verification.notes = request.form.get("notes", "").strip() or None
    ngo.is_verified = action == "approve"
    notify(
        ngo.id,
        "Organization verification update",
        "Your NGO account has been verified."
        if ngo.is_verified
        else "Your NGO verification was not approved. Contact the administrator for details.",
        "account",
    )
    db.session.commit()
    flash(f"{ngo.display_name} verification updated.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot disable your own administrator account.", "warning")
    else:
        user.is_active = not user.is_active
        notify(
            user.id,
            "Account status changed",
            "Your account has been enabled."
            if user.is_active
            else "Your account has been disabled. Contact an administrator if you need help.",
            "account",
        )
        db.session.commit()
        flash(f"{user.display_name} account {'enabled' if user.is_active else 'disabled'}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/reports/<int:report_id>/resolve", methods=["POST"])
@role_required("admin")
def resolve_report(report_id):
    report = Report.query.get_or_404(report_id)
    report.status = "resolved"
    notify(report.reporter_id, "Report reviewed", f'Your report "{report.subject}" was reviewed.', "report")
    db.session.commit()
    flash("Report marked as resolved.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/donations/<int:donation_id>/withdraw", methods=["POST"])
@role_required("admin")
def withdraw_donation(donation_id):
    donation = FoodDonation.query.get_or_404(donation_id)
    if donation.status in {"available", "reserved"}:
        donation.status = "withdrawn"
        notify(
            donation.donor_id,
            "Donation unavailable",
            f"An administrator removed {donation.food_name} from available listings.",
            "donation",
        )
        for pickup in donation.pickup_requests:
            if pickup.status in {"pending", "accepted"}:
                pickup.status = "rejected"
                notify(pickup.ngo_id, "Pickup cancelled", f"{donation.food_name} is no longer available.", "pickup")
        db.session.commit()
        flash("Donation withdrawn from available listings.", "success")
    else:
        flash("This donation is not currently available for withdrawal.", "info")
    return redirect(url_for("admin.dashboard"))
