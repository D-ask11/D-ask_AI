import os
import json
from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.docstore.document import Document
from langchain_chroma import Chroma

class DocumentLoader:
    def __init__(self, settings):
        self.settings = settings

    def load_all_documents(self) -> List[Document]:
        """PDF 및 crawling.json 통합 로드"""
        docs = []
        
        # 1. crawling.json (일반 공지사항) 로드
        crawling_path = os.path.join(self.settings.DATA_DIR, "crawling.json")
        if os.path.exists(crawling_path):
            try:
                with open(crawling_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("crawling", []):
                        contents = item.get("contents", "")
                        docs.append(Document(
                            page_content=contents, 
                            metadata={"source": "crawling.json"}
                        ))
            except Exception as e:
                print(f"Error loading crawling.json: {e}")

        # 2. PDF 파일 로드
        if os.path.exists(self.settings.DATA_DIR):
            for fn in os.listdir(self.settings.DATA_DIR):
                if fn.endswith(".pdf"):
                    try:
                        loader = PyPDFLoader(os.path.join(self.settings.DATA_DIR, fn))
                        docs.extend(loader.load())
                    except Exception as e:
                        print(f"Error loading {fn}: {e}")
        return docs

    def get_vector_db(self, embedding_model):
        """VectorDB 로드 또는 생성"""
        # DB 폴더 체크 및 생성
        if not os.path.exists(self.settings.DB_DIR) or not os.listdir(self.settings.DB_DIR):
            print("VectorDB를 새로 생성합니다...")
            docs = self.load_all_documents()
            return Chroma.from_documents(
                documents=docs,
                embedding=embedding_model,
                persist_directory=self.settings.DB_DIR,
                collection_name=self.settings.COLLECTION_NAME
            )
        
        # 기존 DB 로드
        return Chroma(
            embedding_function=embedding_model,
            persist_directory=self.settings.DB_DIR,
            collection_name=self.settings.COLLECTION_NAME
        )