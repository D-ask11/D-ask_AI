from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ai.model import rag_chain, rag_inference


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["main"])
async def root():
    return {"hello":"wolrd"}

@app.post("/rag/query", tags=["chatbot"])
async def rag_query_endpoint(question: str):
    """
    사용자의 질문을 받아 RAG 체인을 통해 답변을 생성하는 API 엔드포인트
    """
    if not question:
        return {"answer": "질문을 입력해 주세요."}
    
    try:
        # model.py의 핵심 추론 함수를 호출하여 답변을 받습니다.
        answer = rag_inference(question)
        
        return {
            "question": question,
            "answer": answer
        }
        
    except Exception as e:
        # 오류 발생 시 사용자에게 적절한 메시지를 반환1
        return {
            "question": question,
            "answer": f"API 처리 중 오류가 발생했습니다: {str(e)}"
        }