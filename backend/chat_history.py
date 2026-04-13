import logging
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google import genai
from backend.database import get_db
from backend.models import Chatroom, Message
from backend.login import get_user_info_internal
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
    # content에는 유저의 첫 질문이 전달되어야 합니다.
    prompt = f"다음 문장을 요약해서 아주 짧은 채팅방 제목을 만들어줘(최대 10자, 특수문자 제외): {content}"
    
    try:
        # 모델명을 현재 사용 가능한 버전으로 변S경
        response = client.models.generate_content(
            model="gemini-2.0-flash",  # 2.5는 존재하지 않습니다. 2.0 또는 1.5 사용
            contents=prompt
        )
        
        new_title = response.text.strip()
        
        # 새로운 DB 세션을 열어서 업데이트 (기존 방식 유지 시)
        from backend.database import SessionLocal
        db = SessionLocal()
        chat = db.query(Chatroom).filter(Chatroom.id == chat_id).first()
        if chat:
            chat.title = new_title
            db.commit()
            logger.info(f"제목 업데이트 성공: {new_title}")
        db.close()
    except Exception as e:
        logger.error(f"제목 생성 실패: {str(e)}")


def authenticate_user(provider: str, authorization: str, db: Session):
    user_info = get_user_info_internal(provider, authorization, db=db)
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

    # if chat.title == DEFAULT_TITLE:
    #     messages = db.query(Message).filter(Message.room_id == chat_id).all()
    #     user_count = len([m for m in messages if m.role == "user"])
    #     assistant_count = len([m for m in messages if m.role == "assistant"])
    #     if user_count == 1 and assistant_count == 1:
    #         generate_ai_title(chat.id, payload.message)
    #         db.refresh(chat)

    # return {"title": chat.title}

    if chat.title == DEFAULT_TITLE:
        messages = db.query(Message).filter(Message.id == chat_id).all()
        user_msgs = [m for m in messages if m.role == "user"]
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        
        # 유저가 질문하고, AI가 답변을 마친 시점(둘 다 메시지가 1개씩 있을 때)
        if len(user_msgs) == 1 and len(assistant_msgs) == 1:
            # 중요: AI 답변이 아니라 유저의 '첫 번째 질문' 내용을 기반으로 제목 생성
            first_question = user_msgs[0].content
            generate_ai_title(chat.id, first_question)
            db.refresh(chat) # 변경된 제목 반영

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