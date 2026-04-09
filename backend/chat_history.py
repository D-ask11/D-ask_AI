import logging
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google import genai
from backend.database import get_db
from backend.models import Chatroom, Message
from backend.login import get_user_info
import os
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

api_key = os.getenv("API_KEY")

if not api_key:
    raise ValueError("API_KEY 없음 (.env 확인해라)")

client = genai.Client(api_key=api_key)

router = APIRouter(prefix="/chat")
MAX_HISTORY = 20
DEFAULT_TITLE = "새 채팅"


class UpdateChatRequest(BaseModel):
    message: str
    role: str


def build_gemini_contents(chat_messages: list) -> list:
    contents = []
    for msg in chat_messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    return contents


def generate_ai_title(chat_id: str, content: str):
    prompt = f"""
    다음 문장을 기반으로 채팅 제목을 만들어라.
    조건:
    - 다음은 문장을 기반으로 한 채팅 제목들입니다. 이런거 넣지말고 내용과 관련된 제목만 넣어라
    - 반드시 '명사형 제목'으로 작성
    - 질문 형태 금지
    - 50단어 이하로 작성, 10단어 이하 권장
    - 핵심 키워드만 사용
    문장: {content}
    """
    try:
        db = next(get_db())
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        if response and response.text:
            title = response.text.strip().replace("\n", "")
            chat = db.query(Chatroom).filter(Chatroom.id == chat_id).first()
            if chat:
                chat.title = title
                db.commit()
                logger.info(f"[{chat_id}] 제목 생성 완료: {title}")
    except Exception as e:
        logger.error(f"[{chat_id}] 제목 생성 실패: {e}")


def authenticate_user(provider: str, authorization: str, db: Session):
    user_info = get_user_info(provider, authorization, db=db)
    return user_info


@router.post("/create")
def create_chats(
    provider: str = Query(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_info = authenticate_user(provider, authorization, db)
    
    # 기존 "새 채팅" 채팅방이 있는지 확인
    existing_chat = db.query(Chatroom).filter(
        Chatroom.id2 == user_info["user_id"],
        Chatroom.title == DEFAULT_TITLE
    ).first()
    
    if existing_chat:
        return {"title": existing_chat.title, "id": existing_chat.id}
    
    chat = Chatroom(title=DEFAULT_TITLE, id2=user_info["user_id"])
    db.add(chat)
    db.commit()
    db.refresh(chat)

    return {"title": chat.title, "id": chat.id}


@router.get("/read_chat")
def get_chats(
    provider: str = Query(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_info = authenticate_user(provider, authorization, db)
    chats = db.query(Chatroom).filter(Chatroom.id2 == user_info["user_id"]).all()
    return [{"title": c.title, "id": c.id} for c in chats]


@router.get("/read_message/{chat_id}")
def get_chat_messages(
    chat_id: str,
    provider: str = Query(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_info = authenticate_user(provider, authorization, db)
    chat = db.query(Chatroom).filter(Chatroom.id == chat_id, Chatroom.id2 == user_info["user_id"]).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    messages = db.query(Message).filter(Message.room_id == chat_id).order_by(Message.created_at).all()
    return [{"message_id": m.id, "content": m.content} for m in messages]


@router.post("/update/{chat_id}")
def update_chat(
    chat_id: str,
    payload: UpdateChatRequest,
    provider: str = Query(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_info = authenticate_user(provider, authorization, db)
    chat = db.query(Chatroom).filter(Chatroom.id == chat_id, Chatroom.id2 == user_info["user_id"]).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")

    msg = Message(room_id=chat_id, role=payload.role, content=payload.message)
    db.add(msg)
    db.commit()

    if chat.title == DEFAULT_TITLE:
        messages = db.query(Message).filter(Message.room_id == chat_id).all()
        user_count = len([m for m in messages if m.role == "user"])
        assistant_count = len([m for m in messages if m.role == "assistant"])
        if user_count == 1 and assistant_count == 1:
            generate_ai_title(chat.id, payload.message)
            db.refresh(chat)

    return {"title": chat.title}


@router.delete("/delete/{chat_id}")
def delete_chat(
    chat_id: str,
    provider: str = Query(...),
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_info = authenticate_user(provider, authorization, db)
    chat = db.query(Chatroom).filter(Chatroom.id == chat_id, Chatroom.id2 == user_info["user_id"]).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    db.query(Message).filter(Message.room_id == chat_id).delete()
    db.delete(chat)
    db.commit()
    return {}


app = FastAPI()
app.include_router(router)