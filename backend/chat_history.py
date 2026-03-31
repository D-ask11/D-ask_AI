import logging
from fastapi import FastAPI, APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google import genai
from database import get_db, Base, engine
from model import Chat, Message
import os
from dotenv import load_dotenv

Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

api_key = os.getenv("API_KEY")

if not api_key:
    raise ValueError("API_KEY 없음 (.env 확인해라)")

client = genai.Client(api_key=api_key)

router = APIRouter()
MAX_HISTORY = 20


class MessageRequest(BaseModel):
    content: str


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
    - 2~4단어
    - 핵심 키워드만 사용
    문장: {content}
    """
    try:
        db = next(get_db())
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        if response and response.text:
            title = response.text.strip().replace("\n", "")
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            if chat:
                chat.title = title
                db.commit()
                logger.info(f"[{chat_id}] 제목 생성 완료: {title}")
    except Exception as e:
        logger.error(f"[{chat_id}] 제목 생성 실패: {e}")


@router.post("/chats")
def create_chats(db: Session = Depends(get_db)):
    chat = Chat()
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"chat_id": chat.id}


@router.get("/chats")
def get_chats(db: Session = Depends(get_db)):
    return db.query(Chat).all()


@router.get("/chats/{chat_id}")
def get_chat_messages(chat_id: str, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    return db.query(Message).filter(Message.chat_id == chat_id).all()


@router.post("/chats/{chat_id}/messages")
def add_message(chat_id: str, req: MessageRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")

    user_msg = Message(chat_id=chat_id, role="user", content=req.content)
    db.add(user_msg)
    db.commit()

    if chat.title == "새 채팅":
        background_tasks.add_task(generate_ai_title, chat_id, req.content)

    prev_messages = db.query(Message).filter(Message.chat_id == chat_id).all()
    contents = build_gemini_contents([{"role": m.role, "content": m.content} for m in prev_messages])
    contents = contents[-MAX_HISTORY:]

    response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)

    ai_msg = Message(chat_id=chat_id, role="assistant", content=response.text.strip())
    db.add(ai_msg)
    db.commit()

    return {
        "chat_id": chat_id,
        "messages": [
            {"role": user_msg.role, "content": user_msg.content},
            {"role": ai_msg.role, "content": ai_msg.content}
        ]
    }


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.delete(chat)
    db.commit()
    return {"result": "삭제 완료"}


app = FastAPI()
app.include_router(router)