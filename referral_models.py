"""
Creator-referral tables (NEW file - nothing existing is modified).

Tables are created automatically by your existing init_db()
(Base.metadata.create_all) the next time the backend starts, because
routers/referrals.py imports this module before startup.

Design choices that protect your existing code:
  * No foreign keys to users, jobs or payments. Your admin "delete user" loop
    (admin.py) and the hourly expired-job cleanup (database.py) therefore keep
    working exactly as before, and commission history survives job/user deletion.
  * Money uses Numeric(10, 2); times are naive UTC like the rest of your app.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint,
)

from models import Base, generate_uuid


class Creator(Base):
    __tablename__ = "creators"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    handle = Column(String(100))
    platform = Column(String(30))
    contact = Column(String(150))                 # email or phone, used for payouts + self-referral check
    commission_percent = Column(Numeric(5, 2), nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferralLink(Base):
    __tablename__ = "referral_links"
    __table_args__ = (UniqueConstraint("job_id", "creator_id", name="uq_ref_job_creator"),)

    id = Column(String(64), primary_key=True, default=generate_uuid)
    code = Column(String(16), nullable=False, unique=True, index=True)
    job_id = Column(String(64), nullable=False, index=True)      # plain column on purpose (no FK)
    job_title = Column(String(255))                              # snapshot, survives job deletion
    category_id = Column(String(30))                             # snapshot
    creator_id = Column(String(64), ForeignKey("creators.id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferralClick(Base):
    __tablename__ = "referral_clicks"
    __table_args__ = (Index("idx_ref_clicks_link_time", "link_id", "clicked_at"),)

    id = Column(String(64), primary_key=True, default=generate_uuid)
    link_id = Column(String(64), ForeignKey("referral_links.id"), nullable=False)
    visitor_id = Column(String(64))
    clicked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferralSignup(Base):
    """Which link a NEW user registered through. One row per user."""
    __tablename__ = "referral_signups"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    user_id = Column(String(64), nullable=False, unique=True)    # plain column (no FK)
    link_id = Column(String(64), ForeignKey("referral_links.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferralOrderRef(Base):
    """Remembers, server-side, which link a Razorpay order was placed through."""
    __tablename__ = "referral_order_refs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    razorpay_order_id = Column(String(64), nullable=False, unique=True)
    user_id = Column(String(64), nullable=False)
    link_id = Column(String(64), ForeignKey("referral_links.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CreatorPayout(Base):
    __tablename__ = "creator_payouts"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    creator_id = Column(String(64), ForeignKey("creators.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(30))
    reference = Column(String(100))
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReferralConversion(Base):
    """One row per credited purchase. payment_id is UNIQUE => can never be credited twice."""
    __tablename__ = "referral_conversions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    link_id = Column(String(64), ForeignKey("referral_links.id"), nullable=False, index=True)
    creator_id = Column(String(64), ForeignKey("creators.id"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)                 # plain column (no FK)
    payment_id = Column(String(64), nullable=False, unique=True)  # Razorpay payment id
    amount_paid = Column(Numeric(10, 2), nullable=False)
    commission_percent = Column(Numeric(5, 2), nullable=False)    # snapshot at purchase time
    commission_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(12), nullable=False, default="pending")  # pending / paid / reversed
    payout_id = Column(String(64), ForeignKey("creator_payouts.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)