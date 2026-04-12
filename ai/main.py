import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI
from pydantic import BaseModel
from ai.core.engine import bot  # 절대 경로로 임포트하는 것이 가장 안전합니다.

class QuestionRequest(BaseModel):
    question: str
    user_id: str | None = None

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "D-ask AI 서버가 작동 중입니다."}

@app.post("/qna")
async def rag_query_endpoint(request: QuestionRequest):
    if not request.question:
        return {"answer": "질문을 입력해 주세요."}
    
    try:
        # engine.py의 bot.ask 실행
        answer = bot.ask(request.question)
        return {"answer": answer}
    except Exception as e:
        return {"answer": f"서버 오류가 발생했습니다: {str(e)}"}

@app.post("/ai/qna")
async def rag_query_endpoint_with_prefix(request: QuestionRequest):
    # Proxy setups sometimes keep the /ai prefix.
    return await rag_query_endpoint(request)


if __name__ == "__main__":
    import uvicorn
    # host를 0.0.0.0으로 설정해야 외부(Docker나 다른 기기)에서도 접근 가능합니다.
    uvicorn.run(app, host="0.0.0.0", port=8000)