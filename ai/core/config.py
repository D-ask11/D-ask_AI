# 설정 관리
import os

class Settings:
    # 프로젝트 루트 경로 계산
    CORE_DIR = os.path.dirname(os.path.abspath(__file__))
    AI_DIR = os.path.dirname(CORE_DIR)
    ROOT_DIR = os.path.dirname(AI_DIR)
    
    # 데이터 및 DB 경로
    DATA_DIR = os.path.join(ROOT_DIR, "data")
    DB_DIR = os.path.join(AI_DIR, "chroma_db")
    COLLECTION_NAME = "my_rag_collection"
    
    # 모델 설정
    EMBED_MODEL = "intfloat/multilingual-e5-small"
    LLM_MODEL = "qwen2.5:1.5b"
    OLLAMA_URL = "http://ollama:11434"
    SIMILARITY_THRESHOLD = 0.25