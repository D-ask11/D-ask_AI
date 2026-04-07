
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid
from backend.database import Base
from sqlalchemy.sql import func

# SQLAlchemy 모델
# class Chat(Base):
#     __tablename__ = "chats"

#     id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
#     title = Column(String(100), default="새 채팅")
#     created_at = Column(DateTime, default=func.now())


# class Message(Base):
#     __tablename__ = "messages"

#     id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
#     chat_id = Column(String(36), nullable=False)
#     role = Column(String(10), nullable=False)  # "user" or "assistant"
#     content = Column(Text, nullable=False)
#     created_at = Column(DateTime, default=func.now())

class User(Base):
    __tablename__ = "USERS"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True)
    provider = Column(String(50), nullable=False)  # google, naver, kakao

class Chatroom(Base):
    __tablename__ = "CHATROOMS"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    id2 = Column(String(36), ForeignKey("USERS.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Message(Base):
    __tablename__ = "MESSAGES"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    room_id = Column(String(36), ForeignKey("CHATROOMS.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    role = Column(String(50), nullable=False)

# Pydantic 모델
class CalendarRequest(BaseModel):
    year: int
    month: int

class CalendarItem(BaseModel):
    title: str
    date: str

class UserSignup(BaseModel):
    email: str
    provider: str  # google, naver, kakao

class UserResponse(BaseModel):
    id: str
    email: str
    provider: str



