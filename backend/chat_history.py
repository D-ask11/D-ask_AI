import uuid
import logging
from fastapi import FastAPI, APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from google import genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GEMINI_API_KEY = "AIzaSyCS6Q9S-PRTIs_-QUq0lBXZCYQUIJZTbAM"
client = genai.Client(api_key=GEMINI_API_KEY)

router = APIRouter()
chats = {}
messages = {}

MAX_HISTORY = 20  # 최대 히스토리 개수


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
    - 반드시 '명사형 제목'으로 작성
    - 질문 형태 금지
    - 2~4단어
    - 핵심 키워드만 사용
    문장: {content}
    """
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        if response and response.text:
            title = response.text.strip().replace("\n", "")
            chats[chat_id]["title"] = title
            logger.info(f"[{chat_id}] 제목 생성 완료: {title}")
    except Exception as e:
        logger.error(f"[{chat_id}] 제목 생성 실패: {e}")
        chats[chat_id]["title"] = content.strip()[:20]


@router.post("/chats")
def create_chats():
    chat_id = str(uuid.uuid4())
    chats[chat_id] = {"id": chat_id, "title": "새 채팅"}
    messages[chat_id] = []
    return {"chat_id": chat_id}


@router.get("/chats")
def get_chats():
    return list(chats.values())


@router.get("/chats/{chat_id}")
def get_chat_messages(chat_id: str):
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    return messages.get(chat_id, [])


@router.post("/chats/{chat_id}/messages")
def add_message(chat_id: str, req: MessageRequest, background_tasks: BackgroundTasks):
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")

    user_message = {"role": "user", "content": req.content}
    messages[chat_id].append(user_message)

    if chats[chat_id]["title"] == "새 채팅":
        background_tasks.add_task(generate_ai_title, chat_id, req.content)

    contents = build_gemini_contents(messages[chat_id][-MAX_HISTORY:])
    response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)

    ai_message = {
        "role": "assistant",
        "content": response.text.strip() if response and response.text else "응답 생성 실패"
    }
    messages[chat_id].append(ai_message)
    return {"chat_id": chat_id, "messages": [user_message, ai_message]}


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str):
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방")
    chats.pop(chat_id)
    messages.pop(chat_id)
    return {"result": "삭제 완료"}


app = FastAPI()
app.include_router(router)