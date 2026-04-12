import json
import os
import uuid
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# NOTE:
# The frontend (D-ask_FE/page2/script.js) calls:
# - POST   /api/chat/create
# - GET    /api/chat/read_chat
# - GET    /api/chat/read_message/{roomId}
# - POST   /api/chat/update/{roomId}
# - DELETE /api/chat/delete/{roomId}
#
# Previously the backend container only served calendars.py, so chat was never persisted.

from models import Base, Chatroom, CalendarItem, Message, SessionLocal, User, engine


Base.metadata.create_all(bind=engine)

app = FastAPI()

# Be permissive by default; lock this down with explicit origins on deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


def _placeholder_email(provider: str) -> str:
    provider = (provider or "google").strip().lower()
    return f"placeholder-{provider}@d-ask.local"


def get_or_create_user(provider: str, db: Session) -> User:
    """
    FE doesn't send a stable user id here (it uses OAuth tokens client-side),
    so we associate chatrooms to a per-provider placeholder user.
    """
    email = _placeholder_email(provider)
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user

    user = User(email=email, provider=(provider or "google"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _default_room_title() -> str:
    return "새 채팅"


def _title_from_first_message(message: str) -> str:
    text = (message or "").strip().replace("\n", " ")
    if not text:
        return _default_room_title()
    # Keep it short for sidebar rendering
    return text[:24]


class ChatUpdateRequest(BaseModel):
    message: str
    role: str  # "user" | "ai" | "assistant"


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat() + "Z"}


# -----------------------
# Calendar
# -----------------------
@app.get("/calendar", response_model=list[CalendarItem])
def get_calendar(year: int, month: int):
    target_prefix_hyphen = f"{year}-{month:02d}"
    target_prefix_clean = f"{year}{month:02d}"

    # docker-compose mounts ./data -> /app/data
    data_path = os.getenv("SCHEDULE_PATH", "/app/data/school_schedules.json")
    if not os.path.exists(data_path):
        return []

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        result = []
        for item in json_data:
            raw_date = (item.get("date", "") or "").strip()
            if not (raw_date.startswith(target_prefix_hyphen) or raw_date.startswith(target_prefix_clean)):
                continue

            clean_date_8bit = raw_date.replace("-", "")
            if len(clean_date_8bit) == 8:
                item["date"] = clean_date_8bit
                result.append(item)

        return result
    except Exception:
        return []


# -----------------------
# Chat history API (for FE)
# -----------------------
@app.post("/api/chat/create")
def create_room(provider: str = "google", db: Session = Depends(get_db)):
    user = get_or_create_user(provider, db)
    room = Chatroom(
        id=str(uuid.uuid4()),
        title=_default_room_title(),
        id2=user.id,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "title": room.title}


@app.get("/api/chat/read_chat")
def read_chat(provider: str = "google", db: Session = Depends(get_db)):
    user = get_or_create_user(provider, db)
    rooms = (
        db.query(Chatroom)
        .filter(Chatroom.id2 == user.id)
        .order_by(Chatroom.updated_at.desc())
        .all()
    )
    return [{"id": r.id, "title": r.title} for r in rooms]


@app.get("/api/chat/read_message/{room_id}")
def read_message(room_id: str, provider: str = "google", db: Session = Depends(get_db)):
    user = get_or_create_user(provider, db)
    room = db.query(Chatroom).filter(Chatroom.id == room_id, Chatroom.id2 == user.id).first()
    if not room:
        raise HTTPException(status_code=404, detail="room not found")

    messages = (
        db.query(Message)
        .filter(Message.room_id == room_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in messages]


@app.post("/api/chat/update/{room_id}")
def update_room(room_id: str, payload: ChatUpdateRequest, provider: str = "google", db: Session = Depends(get_db)):
    user = get_or_create_user(provider, db)
    room = db.query(Chatroom).filter(Chatroom.id == room_id, Chatroom.id2 == user.id).first()
    if not room:
        raise HTTPException(status_code=404, detail="room not found")

    role = (payload.role or "").strip().lower()
    # FE uses "user" / "ai"; keep legacy "assistant" too.
    if role == "ai":
        role = "assistant"
    if role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="invalid role")

    msg = Message(
        id=str(uuid.uuid4()),
        content=payload.message or "",
        room_id=room_id,
        role=role,
    )
    db.add(msg)

    # Set a title on first user message so the sidebar isn't stuck at "새 채팅".
    if role == "user" and room.title == _default_room_title():
        room.title = _title_from_first_message(payload.message)
    room.updated_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


@app.delete("/api/chat/delete/{room_id}")
def delete_room(room_id: str, provider: str = "google", db: Session = Depends(get_db)):
    user = get_or_create_user(provider, db)
    room = db.query(Chatroom).filter(Chatroom.id == room_id, Chatroom.id2 == user.id).first()
    if not room:
        raise HTTPException(status_code=404, detail="room not found")

    db.query(Message).filter(Message.room_id == room_id).delete()
    db.delete(room)
    db.commit()
    return {"ok": True}