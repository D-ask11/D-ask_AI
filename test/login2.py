from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
import os
from dotenv import load_dotenv
from ..backend.models import User, SessionLocal, UserSignup, UserResponse
import uuid
from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token

load_dotenv()

app = FastAPI()

# 환경 변수
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "your-google-client-id")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Pydantic 모델
class LoginRequest(BaseModel):
    token: str  # Google ID Token

class SignupRequest(BaseModel):
    email: str
    provider: str  # google, naver, kakao

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

# 데이터베이스 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# JWT 토큰 생성
def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None):
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"sub": user_id, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(user_id: str):
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Google OAuth 토큰 검증
def verify_google_token(token: str):
    try:
        idinfo = verify_oauth2_token(token, Request(), GOOGLE_CLIENT_ID)
        
        if idinfo['aud'] != GOOGLE_CLIENT_ID:
            raise ValueError('Token is not valid for this application')
        
        return idinfo
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

# API 엔드포인트

@app.post("/api/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Google OAuth 로그인 API
    - Google ID Token을 받아 검증
    - 기존 사용자 확인, 없으면 자동 회원가입
    """
    try:
        # Google 토큰 검증
        user_info = verify_google_token(request.token)
        
        email = user_info.get('email')
        
        if not email:
            raise HTTPException(status_code=400, detail="Email Not found in token")
        
        # 사용자 확인
        existing_user = db.query(User).filter(User.email == email).first()
        
        if existing_user:
            # 기존 사용자 로그인
            access_token = create_access_token(existing_user.id)
            refresh_token = create_refresh_token(existing_user.id)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user_id": existing_user.id,
                "email": existing_user.email,
                "provider": existing_user.provider,
                "is_new": False
            }
        else:
            # 새 사용자 - 회원가입 API 호출
            new_user_id = str(uuid.uuid4())
            new_user = User(
                id=new_user_id,
                email=email,
                provider="google"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # 토큰 생성
            access_token = create_access_token(new_user.id)
            refresh_token = create_refresh_token(new_user.id)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user_id": new_user.id,
                "email": new_user.email,
                "provider": new_user.provider,
                "is_new": True
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/auth/signup")
async def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """
    사용자 회원가입 API
    - email과 provider를 받아 USERS 테이블에 추가
    """
    try:
        # 기존 이메일 확인
        existing_user = db.query(User).filter(User.email == request.email).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail=f"User with email {request.email} already exists"
            )
        
        # 새 사용자 생성
        user_id = str(uuid.uuid4())
        new_user = User(
            id=user_id,
            email=request.email,
            provider=request.provider
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # 토큰 생성
        access_token = create_access_token(new_user.id)
        refresh_token = create_refresh_token(new_user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": new_user.id,
            "email": new_user.email,
            "provider": new_user.provider
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")

@app.post("/api/auth/refresh")
async def refresh(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    토큰 재발급 API
    - refresh_token을 받아 새로운 access_token 발급
    """
    try:
        # Refresh Token 검증
        try:
            payload = jwt.decode(request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            token_type: str = payload.get("type")
            
            if token_type != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            
            if user_id is None:
                raise HTTPException(status_code=401, detail="Invalid token")
        
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        # 사용자 확인
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 새 토큰 생성
        new_access_token = create_access_token(user.id)
        new_refresh_token = create_refresh_token(user.id)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")

@app.get("/api/users/{user_id}")
async def get_user(user_id: str, db: Session = Depends(get_db)):
    """
    사용자 정보 조회 API
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "email": user.email,
        "provider": user.provider
    }

# 테스트용 루트
@app.get("/")
async def root():
    return {"message": "OAuth Login Service is running"}
