



# from typing import Optional, List
# from datetime import datetime
# from pydantic import BaseModel, EmailStr, Field

# class SendOtpRequest(BaseModel):
#     phone: str

# class VerifyOtpRequest(BaseModel):
#     phone: str
#     otp_code: str

# class UserRegisterRequest(BaseModel):
#     name: str = Field(..., min_length=2, max_length=255)
#     email: EmailStr
#     password: str = Field(..., min_length=6)
#     phone: str
#     otp_code: str
#     age: Optional[int] = None
#     location: Optional[str] = None

# class UserLoginRequest(BaseModel):
#     email: EmailStr
#     password: str

# class GoogleAuthRequest(BaseModel):
#     email: EmailStr
#     name: Optional[str] = None
#     google_id: Optional[str] = None

# class UserResponse(BaseModel):
#     id: str
#     name: str
#     email: str
#     phone: Optional[str] = None
#     age: Optional[int] = None
#     location: Optional[str] = None
#     profile_image: Optional[str] = None
#     status: str
#     created_at: datetime
#     updated_at: datetime

#     class Config:
#         from_attributes = True

# class PackageResponse(BaseModel):
#     id: str
#     name: str
#     slug: str
#     description: str
#     price: float
#     access_type: str
#     is_active: bool

#     class Config:
#         from_attributes = True

# class JobCreateUpdateRequest(BaseModel):
#     title: str
#     company_name: str
#     category_id: str # it, non-it, banking
#     location: str
#     job_type: str = "Full-time"
#     work_mode: str = "Remote"
#     salary: str
#     experience: str
#     education: str
#     skills: List[str]
#     description: str
#     eligibility: str
#     requirements: str
#     additional_information: Optional[str] = None
#     application_url: str
#     deadline: str
#     status: str = "Published"
#     poster_image: Optional[str] = None

# class JobResponse(BaseModel):
#     id: str
#     title: str
#     slug: str
#     company_name: str
#     category_id: str
#     location: str
#     job_type: str
#     work_mode: str
#     salary: str
#     experience: str
#     education: str
#     skills: List[str]
#     description: str
#     eligibility: str
#     requirements: str
#     additional_information: Optional[str] = None
#     application_url: str
#     deadline: str
#     status: str
#     created_at: datetime
#     updated_at: datetime
#     poster_image: Optional[str] = None

#     class Config:
#         from_attributes = True

# class CreateOrderRequest(BaseModel):
#     package_id: str

# class VerifyPaymentRequest(BaseModel):
#     package_id: str
#     razorpay_order_id: str
#     razorpay_payment_id: str
#     razorpay_signature: str
#     is_simulated: Optional[bool] = False

# class PaymentResponse(BaseModel):
#     id: str
#     user_id: str
#     package_id: str
#     order_id: str
#     payment_id: str
#     amount: float
#     currency: str
#     gateway: str
#     status: str
#     created_at: datetime

#     class Config:
#         from_attributes = True









from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class SendOtpRequest(BaseModel):
    email: EmailStr

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp_code: str

class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)
    otp_code: str
    phone: Optional[str] = None
    age: Optional[int] = None
    location: Optional[str] = None

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class GoogleAuthRequest(BaseModel):
    # The frontend sends the Google JWT token as 'credential'
    credential: str 

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    age: Optional[int] = None
    location: Optional[str] = None
    profile_image: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PackageResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    price: float
    access_type: str
    is_active: bool

    class Config:
        from_attributes = True

class JobCreateUpdateRequest(BaseModel):
    title: str
    company_name: str
    category_id: str # it, non-it, banking
    location: str
    job_type: str = "Full-time"
    work_mode: str = "Remote"
    salary: str
    experience: str
    education: str
    skills: List[str]
    description: str
    eligibility: str
    requirements: str
    additional_information: Optional[str] = None
    application_url: str
    deadline: str
    status: str = "Published"
    poster_image: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    title: str
    slug: str
    company_name: str
    category_id: str
    location: str
    job_type: str
    work_mode: str
    salary: str
    experience: str
    education: str
    skills: List[str]
    description: str
    eligibility: str
    requirements: str
    additional_information: Optional[str] = None
    application_url: str
    deadline: str
    status: str
    created_at: datetime
    updated_at: datetime
    poster_image: Optional[str] = None

    class Config:
        from_attributes = True

class CreateOrderRequest(BaseModel):
    package_id: str

class VerifyPaymentRequest(BaseModel):
    package_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    is_simulated: Optional[bool] = False

class PaymentResponse(BaseModel):
    id: str
    user_id: str
    package_id: str
    order_id: str
    payment_id: str
    amount: float
    currency: str
    gateway: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True