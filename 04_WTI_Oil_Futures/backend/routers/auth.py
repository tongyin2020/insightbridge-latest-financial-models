"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import jwt

from deps import db, get_optional_user, logger
from auth_service import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    get_current_user, check_brute_force, record_failed_login, clear_login_attempts,
    generate_reset_token, get_jwt_secret
)
from email_service import EmailService, generate_verification_token

email_service = EmailService()
router = APIRouter()


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class PasswordReset(BaseModel):
    token: str
    new_password: str

class ForgotPassword(BaseModel):
    email: EmailStr


@router.post("/auth/register")
async def register(user_data: UserRegister, response: Response):
    email = user_data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user_data.password)
    user_doc = {
        "email": email,
        "password_hash": hashed,
        "name": user_data.name,
        "role": "user",
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": email, "name": user_data.name, "role": "user"}


@router.post("/auth/login")
async def login(user_data: UserLogin, request: Request, response: Response):
    email = user_data.email.lower()
    identifier = f"{request.client.host}:{email}"
    if await check_brute_force(db, identifier):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user:
        await record_failed_login(db, identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(user_data.password, user["password_hash"]):
        await record_failed_login(db, identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await clear_login_attempts(db, identifier)
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": email, "name": user.get("name", ""), "role": user.get("role", "user")}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request, db)
    return user


@router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    refresh = request.cookies.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(refresh, get_jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload["sub"]
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(user_id, user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
        return {"message": "Token refreshed"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPassword):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}
    token = generate_reset_token()
    await db.password_reset_tokens.insert_one({
        "user_id": str(user["_id"]),
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used": False
    })
    logger.info(f"[Auth] Password reset link: /reset-password?token={token}")
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/auth/reset-password")
async def reset_password(data: PasswordReset):
    token_doc = await db.password_reset_tokens.find_one({
        "token": data.token,
        "used": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    new_hash = hash_password(data.new_password)
    await db.users.update_one(
        {"_id": ObjectId(token_doc["user_id"])},
        {"$set": {"password_hash": new_hash}}
    )
    await db.password_reset_tokens.update_one(
        {"token": data.token},
        {"$set": {"used": True}}
    )
    return {"message": "Password reset successfully"}


@router.post("/auth/send-verification")
async def send_verification_email(request: Request):
    user = await get_current_user(request, db)
    if user.get("email_verified"):
        return {"message": "Email already verified"}
    token = generate_verification_token()
    await db.verification_tokens.insert_one({
        "user_id": user["_id"],
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
        "used": False
    })
    success = await email_service.send_verification_email(
        to_email=user["email"],
        token=token,
        user_name=user.get("name", "Trader")
    )
    if success:
        return {"message": "Verification email sent"}
    else:
        return {"message": "Email queued for delivery (email service may be disabled)"}


@router.post("/auth/verify-email")
async def verify_email(token: str):
    token_doc = await db.verification_tokens.find_one({
        "token": token,
        "used": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    await db.users.update_one(
        {"_id": token_doc["user_id"]},
        {"$set": {"email_verified": True, "verified_at": datetime.now(timezone.utc)}}
    )
    await db.verification_tokens.update_one(
        {"token": token},
        {"$set": {"used": True}}
    )
    return {"message": "Email verified successfully"}
