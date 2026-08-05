"""
portal_routes.py -- auth + profile API for the investor portal.

Endpoints (all under /portal):
  POST /portal/auth/register     {email, password, name?}  -> {token, user}
  POST /portal/auth/login        {email, password}         -> {token, user}
  GET  /portal/auth/me                                     -> user            (Bearer)
  GET  /portal/profile                                     -> {onboarding, parameters}
  PUT  /portal/profile/onboarding {hasExistingPortfolio, investmentAmount, goal}
  PUT  /portal/profile/parameters {alpha, lambda, gamma, confidence?, source?}
  GET  /portal/health                                      -> {db: "up"|"down"}
"""
import re
import datetime as dt

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

import portal_db
from portal_auth import hash_password, verify_password, make_token, get_current_user_id

router = APIRouter(prefix="/portal", tags=["portal"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- request models ---------------------------------------------------------
class RegisterReq(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str | None = None


class LoginReq(BaseModel):
    email: str
    password: str


class AccountReq(BaseModel):
    name: str | None = None


class OnboardingReq(BaseModel):
    hasExistingPortfolio: bool | None = None
    investmentAmount: float | None = None
    goal: str | None = None


class ParametersReq(BaseModel):
    alpha: float | None = None
    lambda_: float | None = Field(default=None, alias="lambda")
    gamma: float | None = None
    confidence: dict | None = None
    source: str | None = None

    model_config = {"populate_by_name": True}


# ---- helpers ----------------------------------------------------------------
def _public_user(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "email": doc["email"], "name": doc.get("name")}


def _norm_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please enter a valid email address")
    return email


# ---- auth -------------------------------------------------------------------
@router.post("/auth/register")
def register(req: RegisterReq):
    email = _norm_email(req.email)
    users = portal_db.users()
    if users.find_one({"email": email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")
    doc = {
        "email": email,
        "name": (req.name or "").strip() or None,
        "password_hash": hash_password(req.password),
        "created_at": dt.datetime.utcnow(),
    }
    res = users.insert_one(doc)
    doc["_id"] = res.inserted_id
    portal_db.profiles().update_one(
        {"user_id": str(res.inserted_id)},
        {"$setOnInsert": {"user_id": str(res.inserted_id), "onboarding": {}, "parameters": {}}},
        upsert=True,
    )
    return {"token": make_token(str(res.inserted_id)), "user": _public_user(doc)}


@router.post("/auth/login")
def login(req: LoginReq):
    email = _norm_email(req.email)
    doc = portal_db.users().find_one({"email": email})
    if not doc or not verify_password(req.password, doc.get("password_hash", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return {"token": make_token(str(doc["_id"])), "user": _public_user(doc)}


@router.get("/auth/me")
def me(uid: str = Depends(get_current_user_id)):
    doc = portal_db.users().find_one({"_id": ObjectId(uid)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _public_user(doc)


@router.put("/account")
def update_account(req: AccountReq, uid: str = Depends(get_current_user_id)):
    portal_db.users().update_one(
        {"_id": ObjectId(uid)},
        {"$set": {"name": (req.name or "").strip() or None}},
    )
    doc = portal_db.users().find_one({"_id": ObjectId(uid)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _public_user(doc)


# ---- profile ----------------------------------------------------------------
@router.get("/profile")
def get_profile(uid: str = Depends(get_current_user_id)):
    p = portal_db.profiles().find_one({"user_id": uid}) or {}
    updated = p.get("updated_at")
    return {
        "onboarding": p.get("onboarding", {}),
        "parameters": p.get("parameters", {}),
        "updated_at": updated.isoformat() if isinstance(updated, dt.datetime) else None,
    }


@router.put("/profile/onboarding")
def put_onboarding(req: OnboardingReq, uid: str = Depends(get_current_user_id)):
    portal_db.profiles().update_one(
        {"user_id": uid},
        {"$set": {"onboarding": req.model_dump(), "updated_at": dt.datetime.utcnow()},
         "$setOnInsert": {"user_id": uid}},
        upsert=True,
    )
    return {"ok": True}


@router.put("/profile/parameters")
def put_parameters(req: ParametersReq, uid: str = Depends(get_current_user_id)):
    params = {
        "alpha": req.alpha,
        "lambda": req.lambda_,
        "gamma": req.gamma,
        "confidence": req.confidence,
        "source": req.source,
    }
    portal_db.profiles().update_one(
        {"user_id": uid},
        {"$set": {"parameters": params, "updated_at": dt.datetime.utcnow()},
         "$setOnInsert": {"user_id": uid}},
        upsert=True,
    )
    return {"ok": True}


# ---- health -----------------------------------------------------------------
@router.get("/health")
def health():
    try:
        portal_db.ping()
        return {"db": "up"}
    except Exception as e:
        return {"db": "down", "detail": str(e)}
