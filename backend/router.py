from fastapi import APIRouter
from backend.schemas import AIanswer, userquestion



    
router = APIRouter(prefix="/api/QnA", tags=["QnA"])

@router.post("/auto-reply", response_model=AIanswer)
def answer(question: userquestion):
    return AIanswer(question = f"질문:{question.question}") # ai모델 답변 생성

    