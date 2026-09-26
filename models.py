



# """
# PostgreSQL SQLAlchemy 2.0 Async Models
# Enforces unique constraints on payment_id and (user_id, package_id)
# """

# import uuid
# from datetime import datetime
# from sqlalchemy import (
#     Column,
#     String,
#     Integer,
#     Numeric,
#     Boolean,
#     DateTime,
#     ForeignKey,
#     Text,
#     UniqueConstraint,
#     Index,
# )
# from sqlalchemy.orm import declarative_base, relationship

# Base = declarative_base()

# def generate_uuid():
#     return str(uuid.uuid4())

# class User(Base):
#     __tablename__ = "users"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     name = Column(String(255), nullable=False)
#     email = Column(String(255), unique=True, nullable=False, index=True)
#     password_hash = Column(String(255), nullable=False)
#     google_id = Column(String(255), nullable=True, unique=True)
#     phone = Column(String(50), nullable=True)
#     age = Column(Integer, nullable=True)
#     location = Column(String(255), nullable=True)
#     profile_image = Column(String(500), nullable=True)
#     status = Column(String(50), default="Active", nullable=False) # Active, Disabled
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

#     access_records = relationship("UserAccess", back_populates="user", cascade="all, delete-orphan")
#     payments = relationship("Payment", back_populates="user")


# class Admin(Base):
#     __tablename__ = "admins"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     name = Column(String(255), nullable=False)
#     email = Column(String(255), unique=True, nullable=False, index=True)
#     password_hash = Column(String(255), nullable=False)
#     role = Column(String(50), default="SuperAdmin", nullable=False)
#     status = Column(String(50), default="Active", nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# class Package(Base):
#     __tablename__ = "packages"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     name = Column(String(255), nullable=False)
#     slug = Column(String(50), unique=True, nullable=False) # it, non-it, banking, all
#     description = Column(Text, nullable=False)
#     price = Column(Numeric(10, 2), nullable=False) # in INR
#     access_type = Column(String(50), nullable=False) # IT, NON_IT, BANKING, ALL
#     is_active = Column(Boolean, default=True, nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# class Job(Base):
#     __tablename__ = "jobs"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     title = Column(String(255), nullable=False)
#     slug = Column(String(255), unique=True, nullable=False, index=True)
#     company_name = Column(String(255), nullable=False)
#     category_id = Column(String(50), nullable=False, index=True) # it, non-it, banking
#     location = Column(String(255), nullable=False)
#     job_type = Column(String(50), default="Full-time", nullable=False)
#     work_mode = Column(String(50), default="Remote", nullable=False) # Remote, Hybrid, On-site
#     salary = Column(String(100), nullable=False)
#     experience = Column(String(100), nullable=False)
#     education = Column(String(255), nullable=False)
#     skills = Column(Text, nullable=False) # JSON or comma separated string
#     description = Column(Text, nullable=False)
#     eligibility = Column(Text, nullable=False)
#     requirements = Column(Text, nullable=False)
#     additional_information = Column(Text, nullable=True)
#     application_url = Column(String(1000), nullable=False) # Direct external destination link
#     deadline = Column(String(50), nullable=False)
#     status = Column(String(50), default="Published", nullable=False) # Draft, Published, Archived
#     created_by = Column(String(255), nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
#     poster_image = Column(String(1000), nullable=True)

#     images = relationship("JobImage", back_populates="job", cascade="all, delete-orphan")


# class JobImage(Base):
#     __tablename__ = "job_images"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
#     image_url = Column(String(1000), nullable=False)
#     file_name = Column(String(255), nullable=False)
#     file_size = Column(Integer, nullable=False)
#     mime_type = Column(String(100), nullable=False)
#     is_primary = Column(Boolean, default=False, nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     job = relationship("Job", back_populates="images")


# class Payment(Base):
#     __tablename__ = "payments"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
#     package_id = Column(String, ForeignKey("packages.id"), nullable=False)
#     order_id = Column(String(255), nullable=False, index=True)
#     payment_id = Column(String(255), unique=True, nullable=False, index=True) # Enforce database-level uniqueness
#     amount = Column(Numeric(10, 2), nullable=False)
#     currency = Column(String(10), default="INR", nullable=False)
#     gateway = Column(String(50), default="razorpay", nullable=False)
#     status = Column(String(50), default="Successful", nullable=False) # Successful, Failed, Pending, Refunded
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     user = relationship("User", back_populates="payments")
#     package = relationship("Package")


# class UserAccess(Base):
#     __tablename__ = "user_access"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
#     package_id = Column(String, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False, index=True)
#     payment_id = Column(String(255), nullable=False)
#     status = Column(String(50), default="Active", nullable=False) # Active, Expired, Revoked
#     start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
#     expiry_date = Column(DateTime, nullable=True)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     # Database-level unique constraint to guarantee zero race conditions on concurrent purchases
#     __table_args__ = (
#         UniqueConstraint("user_id", "package_id", name="uq_user_package_access"),
#         Index("idx_user_pkg", "user_id", "package_id"),
#     )

#     user = relationship("User", back_populates="access_records")
#     package = relationship("Package")


# class OtpVerification(Base):
#     __tablename__ = "otp_verifications"

#     id = Column(String, primary_key=True, default=generate_uuid)
#     phone = Column(String(20), nullable=False, index=True)
#     otp_code = Column(String(10), nullable=False)
#     session_id = Column(String(255), nullable=True)  # 2Factor.in tracking ID
#     is_verified = Column(Boolean, default=False, nullable=False)
#     expires_at = Column(DateTime, nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)









"""
PostgreSQL SQLAlchemy 2.0 Async Models
Enforces unique constraints on payment_id and (user_id, package_id)
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    google_id = Column(String(255), nullable=True, unique=True)
    phone = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    location = Column(String(255), nullable=True)
    profile_image = Column(String(500), nullable=True)
    status = Column(String(50), default="Active", nullable=False) # Active, Disabled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    access_records = relationship("UserAccess", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="SuperAdmin", nullable=False)
    status = Column(String(50), default="Active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Package(Base):
    __tablename__ = "packages"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(50), unique=True, nullable=False) # it, non-it, banking, all
    description = Column(Text, nullable=False)
    price = Column(Numeric(10, 2), nullable=False) # in INR
    access_type = Column(String(50), nullable=False) # IT, NON_IT, BANKING, ALL
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    category_id = Column(String(50), nullable=False, index=True) # it, non-it, banking
    location = Column(String(255), nullable=False)
    job_type = Column(String(50), default="Full-time", nullable=False)
    work_mode = Column(String(50), default="Remote", nullable=False) # Remote, Hybrid, On-site
    salary = Column(String(100), nullable=False)
    experience = Column(String(100), nullable=False)
    education = Column(String(255), nullable=False)
    skills = Column(Text, nullable=False) # JSON or comma separated string
    description = Column(Text, nullable=False)
    eligibility = Column(Text, nullable=False)
    requirements = Column(Text, nullable=False)
    additional_information = Column(Text, nullable=True)
    application_url = Column(String(1000), nullable=False) # Direct external destination link
    deadline = Column(String(50), nullable=False)
    status = Column(String(50), default="Published", nullable=False) # Draft, Published, Archived
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    poster_image = Column(String(1000), nullable=True)

    images = relationship("JobImage", back_populates="job", cascade="all, delete-orphan")


class JobImage(Base):
    __tablename__ = "job_images"

    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(1000), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="images")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id = Column(String, ForeignKey("packages.id"), nullable=False)
    order_id = Column(String(255), nullable=False, index=True)
    payment_id = Column(String(255), unique=True, nullable=False, index=True) # Enforce database-level uniqueness
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    gateway = Column(String(50), default="razorpay", nullable=False)
    status = Column(String(50), default="Successful", nullable=False) # Successful, Failed, Pending, Refunded
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="payments")
    package = relationship("Package")


class UserAccess(Base):
    __tablename__ = "user_access"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id = Column(String, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id = Column(String(255), nullable=False)
    status = Column(String(50), default="Active", nullable=False) # Active, Expired, Revoked
    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    expiry_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Database-level unique constraint to guarantee zero race conditions on concurrent purchases
    __table_args__ = (
        UniqueConstraint("user_id", "package_id", name="uq_user_package_access"),
        Index("idx_user_pkg", "user_id", "package_id"),
    )

    user = relationship("User", back_populates="access_records")
    package = relationship("Package")


class OtpVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)