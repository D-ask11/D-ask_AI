import os
import uuid
from urllib.parse import urlencode

import dotenv
import requests
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models import SessionLocal, User, UserResponse

# .env 로드
dotenv.load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("GOOGLE_CLIENT_ID 및 GOOGLE_CLIENT_SECRET을 .env에 설정하세요")

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 명세: api/auth/login
class LoginRequest(BaseModel):
    social_kind: str
    email: str | None = None


@app.post("/api/auth/login")
def api_auth_login(payload: LoginRequest, db: Session = Depends(get_db)):
    if payload.social_kind != "google":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="지원하지 않는 social_kind")

    # 이메일이 들어왔을 때 DB 확인
    if payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
        if user:
            return {"id": user.id}
        else:
            # 없는 사용자라면 id 빈값
            return {"id": None}

    # 이메일이 없으면 프런트에서 구글 OAuth flow 시작용 URL 반환
    state = str(uuid.uuid4())
    q = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    login_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(q)}"
    return {"login_url": login_url}


# 명세: api/auth/register
class RegisterRequest(BaseModel):
    UserID: str
    email: str


@app.post("/api/auth/register")
def api_auth_register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if not payload.UserID or not payload.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UserID와 email을 입력하세요")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        return {"id": existing.id}

    user = User(email=payload.email, provider="google")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id}


@app.get("/login/google")
def login_with_google():
    state = str(uuid.uuid4())
    query = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(query)}"
    return RedirectResponse(url)


@app.get("/auth/google/callback")
def google_callback(code: str | None = None, state: str | None = None, db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code 누락")

    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_resp = requests.post(
        GOOGLE_TOKEN_ENDPOINT,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google 토큰 교환 실패")

    token_json = token_resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="access_token 없음")

    userinfo_resp = requests.get(
        GOOGLE_USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )

    if userinfo_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google 사용자 정보 조회 실패")

    userinfo = userinfo_resp.json()
    email = userinfo.get("email")
    name = userinfo.get("name")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google 이메일 없음")

    user = db.query(User).filter(User.email == email).first()
    is_new_user = False
    if not user:
        user = User(email=email, provider="google")
        db.add(user)
        db.commit()
        db.refresh(user)
        is_new_user = True

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "user": UserResponse(id=user.id, email=user.email, provider=user.provider).dict(),
            "is_new_user": is_new_user,
            "google_profile": {"name": name, "email": email},
        },
    )


@app.get("/api/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {"users": [UserResponse(id=u.id, email=u.email, provider=u.provider).dict() for u in users]}


@app.get("/health")
def health_check():
    return {"status": "ok"}
