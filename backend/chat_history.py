from fastapi import FastAPI , APIRouter
from pydantic import BaseModel
from typing import List
import uuid

router = APIRouter()
chats={}
messages={}

class MessageRequest(BaseModel):
    content: str
@router.get("/chats")
def create_chats():

    chat_id=str(uuid.uuid4())

    chats[chat_id]={
        "id":chat_id,
        "title":"새 채팅"
    }

    messages[chat_id]=[]

    return {"chat_id": chat_id}


@router.get("/chat")
def get_chats():

    return list(chats.values())

@router.get("/chat/{chat_id}")
def get_chat_messages(chat_id: str):

    return messages.get(chat_id, [])

@router.post("/chat/{chat_id}/message")
def add_message(chat_id: str, req: MessageRequest):

    user_message = {
        "role": "user",
        "content": req.content
    }

    messages[chat_id].append(user_message)

    # 제목 자동 생성 (첫 메시지 기준)
    if chats[chat_id]["title"] == "새 채팅":
        chats[chat_id]["title"] = req.content[:30]

    # AI 응답 (임시)
    ai_message = {
        "role": "assistant",
        "content": "AI 응답 예시"
    }

    messages[chat_id].append(ai_message)

    return {
        "user": user_message,
        "assistant": ai_message
    }

@router.delete("/chat/{chat_id}")
def delete_chat(chat_id: str):

    chats.pop(chat_id, None)
    messages.pop(chat_id, None)

    return {"result": "deleted"}


app = FastAPI()
app.include_router(router)