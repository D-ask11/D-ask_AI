
import os
import json
from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.docstore.document import Document
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

class DocumentLoader:
    def __init__(self, settings):
        self.settings = settings

    def load_all_documents(self) -> List[Document]:
        docs = []
        pdf_count = 0
        
        # 1. crawling.json 로드
        crawling_path = os.path.join(self.settings.DATA_DIR, "crawling.json")
        if os.path.exists(crawling_path):
            try:
                with open(crawling_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("crawling", []):
                        txt = item.get("contents", "").strip()
                        if txt:
                            docs.append(Document(page_content=txt, metadata={"source": "crawling.json"}))
            except Exception as e:
                print(f"로그: crawling.json 로드 중 오류: {e}")

        # 2. PDF 로드 (에러 방지 강화)
        if os.path.exists(self.settings.DATA_DIR):
            for fn in os.listdir(self.settings.DATA_DIR):
                if not fn.lower().endswith(".pdf"):
                    continue
                
                pdf_path = os.path.join(self.settings.DATA_DIR, fn)
                print(f"로그: pdf 로드 시도 중 -> {fn}")
                
                try:
                    loader = PyPDFLoader(pdf_path)
                    pages = loader.load()
                    
                    added_in_this_file = 0
                    for i, page in enumerate(pages):
                        page_txt = page.page_content.strip()
                        if page_txt:
                            # 💡 첫 페이지 내용만 살짝 확인
                            if i == 0:
                                print(f"   [미리보기] {fn}: {page_txt[:50]}...")
                            
                            page.metadata["source"] = fn
                            docs.append(page)
                            added_in_this_file += 1
                    
                    if added_in_this_file > 0:
                        pdf_count += 1
                        print(f"로그: {fn} 로드 성공 ({added_in_this_file} 페이지)")
                    else:
                        print(f"⚠️ 경고: {fn}에서 읽을 수 있는 텍스트가 없습니다.")
                        
                except Exception as e:
                    print(f"로그: {fn} 처리 중 에러 발생: {str(e)}")

        print(f"로그: 총 {len(docs)}개의 원본 문서를 확보했습니다. (pdf {pdf_count}개 포함)")

        if not docs:
            return []

        # 3. 텍스트 분할 (검색 효율을 위해 600/100으로 최적화)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=50,
            separators=["\n\n", "\n", " ", ""]
        )
        final_docs = text_splitter.split_documents(docs)
        print(f"로그: 최종 {len(final_docs)}개의 조각으로 분할 완료.")
        
        return final_docs
    
    def get_vector_db(self, embeddings):
        """할당량 제한(429)을 절대 넘지 않는 안전 모드"""
        all_docs = self.load_all_documents()
        chroma_dir = getattr(self.settings, 'DB_DIR', "/app/ai/chroma_db")
        collection_name = getattr(self.settings, 'COLLECTION_NAME', 'langchain')

        if os.path.exists(chroma_dir) and os.listdir(chroma_dir):
            try:
                vector_db = Chroma(
                    collection_name=collection_name,
                    persist_directory=chroma_dir,
                    embedding_function=embeddings,
                )
                existing_count = vector_db._collection.count()
                if all_docs and existing_count < len(all_docs):
                    raise RuntimeError(
                        f"부분적으로만 빌드된 VectorDB 발견: {existing_count} / {len(all_docs)}"
                    )
                vector_db.similarity_search("테스트", k=1)
                return vector_db
            except Exception as exc:
                print(f"로그: 기존 VectorDB 로드 또는 검증 실패: {exc}. 재생성합니다.")
                import chromadb
                client_settings = chromadb.config.Settings(
                    is_persistent=True,
                    persist_directory=chroma_dir,
                )
                client = chromadb.Client(client_settings)
                existing_collections = client.list_collections()
                existing_names = [
                    c if isinstance(c, str) else getattr(c, 'name', None)
                    for c in existing_collections
                ]
                if collection_name in existing_names:
                    client.delete_collection(name=collection_name)

        print(f"VectorDB 생성 시작 (총 {len(all_docs)}개 조각)...")
        
        import time
        # ✅ 배치 크기를 줄여 Google Embedding 쿼터 초과를 방지합니다.
        batch_size = 10
        
        # 첫 번째 배치
        initial_batch = all_docs[:batch_size]
        try:
            vector_db = Chroma.from_documents(
                documents=initial_batch,
                embedding=embeddings,
                collection_name=collection_name,
                persist_directory=chroma_dir
            )
            print(f"로그: 첫 번째 배치 완료 ({batch_size} / {len(all_docs)})")
            time.sleep(10)
            
            # 나머지 배치
            for i in range(batch_size, len(all_docs), batch_size):
                batch = all_docs[i : i + batch_size]
                retry_count = 0
                while True:
                    try:
                        vector_db.add_documents(batch)
                        break
                    except Exception as exc:
                        retry_count += 1
                        message = str(exc)
                        if retry_count >= 3 or "RESOURCE_EXHAUSTED" not in message:
                            raise
                        wait_seconds = 40
                        print(f"로그: 임베딩 쿼터 초과. {wait_seconds}초 후 재시도합니다. (시도 {retry_count}/3)")
                        time.sleep(wait_seconds)
                print(f"로그: 벡터화 진행 중... ({min(i + len(batch), len(all_docs))} / {len(all_docs)})")
                time.sleep(10)
                
            print("로그: VectorDB 생성 완료! 이제 PDF 질문이 가능합니다.")
            return vector_db
        except Exception as exc:
            print(f"로그: VectorDB 생성 실패: {exc}. VectorDB를 사용할 수 없습니다.")
            return None
