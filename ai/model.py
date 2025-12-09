# 순서: DB저장 -> json 파일 읽기 -> embedding -> vetorDB -> 유사도 검색 -> 답변 생성

import os
import json
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader

JSON_FILE = "crawling.json"
PERSIST_DIR = "./chroma.db"

embedding_model = HuggingFaceEmbeddings(
    model_name = "sentence-transformers/all-mpnet-base-v2"
)

with open("crawling.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    
    
if os.path.exists(PERSIST_DIR):
    vectordb = Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embedding_model
    )
else:
    vectordb = Chroma.from_texts([], embedding=embedding_model, persist_directory=PERSIST_DIR)

def get_doc_id(text):
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()

existing_ids = set()
for doc in vectordb.get(include=["metadatas"]):
    if "id" in doc["metadata"]:
        existing_ids.add(doc["metadata"]["id"])
        
new_texts = []
new_metadatas = []

for sentence in data:
    text = f"{sentence["title"]}\n{sentence["content"]}"
    
    if "pdf" in sentence and sentence["pdf"]:
        for pdf_item in sentence["pdf"]:
            pdf_url = pdf_item.get("url")
            
            if pdf_url:
                loader = PyPDFLoader(pdf_url)
                pdf_pages = loader.load()
                for page in pdf_pages:
                    text += "\n" + page.page_content
                    
    doc_id = get_doc_id(text)
    if doc_id not in existing_ids:
        new_texts.append(text)
        new_metadatas.append(text)
        new_metadatas.append({"id": doc_id, "title": sentence["title"]})
        
if new_texts:
    vectordb.add_texts(new_texts, metadatas=new_metadatas)
    vectordb.persist()
    print(f"{len(new_texts)}개의 새롤운 문서를 vetordb에 추가했습니다.")
else:
    print("새로운 문서가 없습니다.")