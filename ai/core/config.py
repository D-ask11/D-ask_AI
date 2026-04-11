# 설정 관리
import os
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, "..", "..", ".env")
load_dotenv(dotenv_path=env_path)


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
    EMBED_MODEL = "models/gemini-embedding-001"
    LLM_MODEL = "models/gemini-2.5-flash"
    SIMILARITY_THRESHOLD = 0.1
