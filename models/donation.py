from datetime import datetime

from extensions import db


class FoodCategory(db.Model):
    __tablename__ = "food_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    donations = db.relationship("FoodDonation", back_populates="category", lazy=True)


class FoodDonation(db.Model):
    __tablename__ = "food_donations"

    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("food_categories.id"), nullable=False, index=True
    )
    food_name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    meals = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(255))
    preparation_time = db.Column(db.DateTime, nullable=False)
    expiry_time = db.Column(db.DateTime, nullable=False, index=True)
    pickup_address = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    status = db.Column(db.String(20), nullable=False, default="available", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    donor = db.relationship("User", back_populates="donations")
    category = db.relationship("FoodCategory", back_populates="donations")
    pickup_requests = db.relationship("PickupRequest", back_populates="donation", lazy=True)

    @property
    def is_expired(self):
        return self.expiry_time <= datetime.now()
