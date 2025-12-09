# 순서: DB저장 -> embedding -> vetorDB -> 유사도 검색 -> 답변 생성

import os
import json
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.docstore.document import Document
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableMap, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # model.py 기준 폴더
JSON_FILE = os.path.join(BASE_DIR, "..", "crawling.json")
DB_DIR = os.path.join(BASE_DIR, "..", "chroma.db")

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

def load_json(file_path=JSON_FILE):
    """JSON 파일 읽어서 Document 리스트로 변환"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # crawling 리스트 추출
    items = data.get("crawling", [])
    
    documents = [
        Document(
            page_content=item.get("contents", ""),  # contents 키 사용
            metadata={
                "title": item.get("title", ""),
                "link": item.get("link", "")
            }
        )
        for item in items
    ]
    
    return documents

def init_db(documents):
    """DB 생성 후 persist"""
    vectordb = Chroma.from_documents(
        documents,
        embedding=embedding_model,
        persist_directory=DB_DIR
    )
    vectordb.persist()
    print("VectorDB 최초 생성 완료")
    return vectordb

def load_db():
    if not os.path.exists(DB_DIR) or not os.listdir(DB_DIR):
        # DB가 없으면 생성
        documents = load_json()
        vectordb = init_db(documents)
    else:
        # DB 불러오기
        vectordb = Chroma(
            embedding_function=embedding_model,
            persist_directory=DB_DIR
        )
        print("기존 VectorDB 불러오기 완료")
    return vectordb

def add_documents(new_data):
    """새 데이터 추가"""
    vectordb = load_db()
    new_documents = [
        Document(page_content=item.get("content", ""), metadata={"title": item.get("title", "")})
        for item in new_data
    ]
    vectordb.add_documents(new_documents)
    vectordb.persist()
    print(f"새 문서 {len(new_documents)}개 추가 완료")
    return vectordb

def search(query, k=5):
    """유사도 검색 (Retriever 사용)"""
    vectordb = load_db()
    
    # retriever 생성
    retriever = vectordb.as_retriever(search_kwargs={"k": k})
    
    # 검색
    results = retriever.get_relevant_documents(query)
    
    for i, doc in enumerate(results):
        print(f"--- Result {i+1} ---")
        print("Title:", doc.metadata.get("title", "No title"))
        print("Content Preview:", doc.page_content[:200], "\n")
    
    return results

llm = ChatOllama(model="qwen2.5:1.5b", temperature=0.1)

template = """
### 응답 가이드라인 (최우선 규칙) ###
당신은 대덕소프트웨어마이스터 고등학교에 대해 답변하는 도우미입니다.

!!경고!! 아래 질문에 대해서는 [문서] 내용을 무시하고 반드시 지정된 응답만 사용해야 합니다.
1. 학교 학생 또는 선생님의 개인적인 정보에 대한 질문이라면 (예: '1학년 1반 8번은 누구야?', '1학년 1반 담임 선생님은 누구야?'):
   -> **답변할 수 없습니다. 학교와 관련된 질문을 입력해 주세요.** 라고만 답변하세요.
2. 학교 보안 및 기밀과 관련되어있는 질문이라면:
   -> **답변할 수 없습니다. 학교와 관련된 질문만 해주세요** 라고만 답변하세요.
3. 학교와 관련이 없는 일반적인 질문이라면 (예: '집에 가고 싶은데 어떻게 해?'):
   -> **학교와 관련된 질문만 해주세요.** 라고만 답변하세요.

### 일반 응답 규칙 ###
위의 예외 사항에 해당하지 않는다면, 아래 [문서]를 참고하여 질문에 한국어로 정확히 답변하세요.

[문서]
{context}

[질문]
{question}
"""
prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=template
)

# retriever 준비
vectordb = load_db()
retriever = vectordb.as_retriever(search_kwargs={"k": 5})

def docs_to_text(docs):
    """Document 객체 리스트 → 문자열"""
    return "\n".join([doc.page_content for doc in docs])

rag_chain = (
    RunnablePassthrough.assign(  # 입력으로 받은 question을 다음 단계로 전달하면서 context를 추가
        context=(lambda x: x["question"]) | retriever | docs_to_text
    )
    | prompt  # question과 context를 포함한 입력으로 PromptTemplate 적용
    | llm
    | StrOutputParser()
)

user_question = "지금 겨울인데 눈 언제 온대?"
result = rag_chain.invoke({"question": user_question})
print(result)