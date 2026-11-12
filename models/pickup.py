from datetime import datetime

from extensions import db


class PickupRequest(db.Model):
    __tablename__ = "pickup_requests"

    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(
        db.Integer, db.ForeignKey("food_donations.id"), nullable=False, index=True
    )
    ngo_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    pickup_date = db.Column(db.DateTime, nullable=False)
    pickup_time = db.Column(db.String(50))
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    notes = db.Column(db.Text)
    requested_quantity = db.Column(db.Integer)
    requested_meals = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    donation = db.relationship("FoodDonation", back_populates="pickup_requests")
    ngo = db.relationship("User", foreign_keys=[ngo_id])
    donor = db.relationship("User", foreign_keys=[donor_id])


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50))
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="notifications")


class PickupHistory(db.Model):
    __tablename__ = "pickup_history"

    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("food_donations.id"), nullable=False)
    ngo_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    donor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    meals = db.Column(db.Integer, nullable=False, default=0)

    donation = db.relationship("FoodDonation")
    ngo = db.relationship("User", foreign_keys=[ngo_id])
    donor = db.relationship("User", foreign_keys=[donor_id])


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    subject = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reporter = db.relationship("User")
