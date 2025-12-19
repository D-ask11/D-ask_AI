# 순서: DB저장 -> json 읽기 -> embedding -> vetorDB -> 유사도 검색 -> 답변 생성

import os
import json
import datetime
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.docstore.document import Document
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(BASE_DIR, "..", "crawling.json")
DB_DIR = os.path.join(BASE_DIR, "..", "chroma.db")

embedding_model = HuggingFaceEmbeddings(
    model_name = "jhgan/ko-sbert-nli"
)

def load_json(file_path=JSON_FILE):
    """JSON 파일 읽어서 Document 리스트로 변환"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("crawling", [])
    documents = []
    for item in items:
        title = item.get("title", "")
        contents = item.get("contents", "")

        # PDF 링크 텍스트
        pdf_links = item.get("pdf", [])
        link_text = ""
        for pdf in pdf_links:
            link_text += f"\n- {pdf.get('filename')}: {pdf.get('url')}"

        # 제목 제거: contents + pdf 링크만 embedding
        page_content = contents + link_text

        documents.append(
            Document(
                page_content=page_content,
                metadata={
                    "title": title,                 # 제목은 metadata
                    "link": item.get("link", "")    # 게시글 링크
                }
            )
        )
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
    # Chroma는 기본 컬렉션 이름이 'langchain'입니다. 이를 명시적으로 지정합니다.
    COLLECTION_NAME = "my_rag_collection" # 명시적인 이름을 사용합니다.
    print(f"DEBUG: DB_DIR 경로 = {DB_DIR}")
    print(f"DEBUG: DB_DIR 존재 여부 = {os.path.exists(DB_DIR)}")
    
    if not os.path.exists(DB_DIR) or not os.listdir(DB_DIR):
        # 1. DB가 없으면 생성 시에도 컬렉션 이름 지정
        documents = load_json()
        vectordb = Chroma.from_documents(
            documents,
            embedding=embedding_model,
            persist_directory=DB_DIR,
            collection_name=COLLECTION_NAME # 컬렉션 이름 명시
        )
        vectordb.persist()
        print("VectorDB 최초 생성 완료")
    else:
        # 2. DB 불러오기 시에도 컬렉션 이름 지정
        vectordb = Chroma(
            embedding_function=embedding_model,
            persist_directory=DB_DIR,
            collection_name=COLLECTION_NAME # 컬렉션 이름 명시
        )
        print("기존 VectorDB 불러오기 완료")
        
    #이 부분이 반드시 추가되어야 합니다
    try:
        count = vectordb._collection.count()
        print(f"DB 컬렉션 내 문서 수 확인: {count}개")
        if count == 0:
            print("경고: 문서 수가 0개입니다. DB 재구축이 필요합니다.")
    except Exception as e:
        print(f"DB 카운트 중 오류 발생: {e}")
        
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
당신은 대덕소프트웨어마이스터 고등학교에 대한 정보만 제공하는 지식 도우미입니다.

**!!보안/개인정보 경고!!**
개인정보(이름, 주소, 연락처 등)나 보안이 필요한 정보는 절대 다루지 않으며, [문서]에 없는 내용을 추측하거나 지어내지 않습니다.

---

# [현재 시점] 섹션 (LLM에게 실시간 날짜를 알려주는 핵심)
[현재 시점]
{current_date}을 기준으로 가장가까운 연도 한가지만 설명해주세요.
만약 특정 연도가 있다면 그 연도만 설명해주세요.
만약 현재 연도보다 연도가 더 높으면 그 연도를 기준으로 설명해주세요

#학교 정보 외 질문 거부 지침 강화
학교 정보(학사 일정, 가정 통신문, 규정 등)와 **무관한 일반 상식, 실시간 정보 (예: 날씨, 세계 뉴스 등)**는 답변할 수 없습니다. **단, [현재 시점]에 대한 질문(예: 오늘은 몇월 며칠이야?)에 대해서는 이 정보를 사용하여 정확히 답변하세요.**

---

### 일반 응답 규칙 (RAG 실행 시) ###
위의 예외 사항에 해당하지 않는다면, 아래 [문서]를 참고하여 질문에 한국어로 정확히 답변하세요.
**!!가장 중요!! [문서]에 없는 내용은 절대 추측하거나 지어내지 마세요.** 오직 문서에 포함된 내용만을 바탕으로 답변해야 합니다.

***데이터 시간 우선순위 (필수)***
1. **1순위:** [문서]에서 **'2025년'**에 관련된 정보가 있다면 최우선적으로 해당 정보를 사용하여 답변하세요.
2. **2순위:** 만약 2025년 정보가 없다면, 질문과 관련된 **가장 최근 연도**의 정보를 사용하세요.

---

### 답변 구성 형식 ###

1. **내용 요약:** [문서] 내용이 질문에 대한 충분한 답변을 제공한다면, 상세하고 명확하게 답변하세요.
2. **링크 첨부 필수:** 답변에 사용된 원본 자료나 참고 가능한 **PDF 문서의 링크(URL)**는 답변 하단에 **[참고 자료]** 섹션을 만들어 **반드시 모두 포함**하세요. (메타데이터나 본문에 포함된 링크 활용)

!!최종 중요!! [문서] 내에 **질문의 키워드와 관련된 내용(제목 포함)이 단 한 줄이라도 포함되어 있다면**, 최대한 답변을 구성하고 **링크를 제공하여 답변을 완료**하세요. 
만약 **질문과 전혀 무관한 문서만 검색**되었거나 답변할 수 없는 일반 질문이라면, **'관련 정보를 찾을 수 없습니다.'** 라고 답변하세요.

[문서]
{context}

[질문]
{question}
"""
# ... (PromptTemplate 재정의)

prompt = PromptTemplate(
    input_variables=["context", "question", "current_date"],
    template=template
)

# retriever 준비
vectordb = load_db()
retriever = vectordb.as_retriever(search_kwargs={"k": 3})

def docs_to_text(docs):
    """Document 객체 리스트 → 문자열"""
    return "\n".join([doc.page_content for doc in docs])

def get_current_date():
    """현재 날짜와 요일을 문자열로 변환"""
    return datetime.datetime.now().strftime("%Y년 %m월 %d일 %A")

rag_chain = (
    RunnablePassthrough.assign(  # 입력으로 받은 question을 다음 단계로 전달하면서 context를 추가
        context=(lambda x: x["question"]) | retriever | docs_to_text, current_date = RunnableLambda(lambda x: get_current_date())
        
    )
    | prompt  # question과 context를 포함한 입력으로 PromptTemplate 적용
    | llm
    | StrOutputParser()
)


def get_rag_chain():
    """초기화된 RAG 체인 객체를 반환"""
    return rag_chain


def rag_inference(question: str) -> str:
    """실제 추론을 수행하는 핵심 함수 (수정된 디버깅 로직)"""
    
    # 1. Retriever를 사용하여 Context를 가져오는 부분만 체인으로 실행
    # Context를 가져오는 Runnable 정의 (rag_chain의 첫 번째 단계와 동일)
    context_retrieval_chain = (
        RunnablePassthrough()
        |(lambda x: x["question"])
        | retriever 
    )
    
    # Context 문서 객체를 직접 가져옴
    try:
        retrieved_docs = context_retrieval_chain.invoke({"question": question})
    except Exception as e:
        print(f"ontext Retrieval 오류 발생: {e}")
        # 오류 발생 시 빈 리스트 반환하여 다음 단계로 진행
        retrieved_docs = []


    # 2. 검색 결과 터미널 출력 (디버깅)
    print("\n--- RAG 검색 결과 디버깅 시작 ---")
    if not retrieved_docs:
        print("!! 검색된 문서가 0개입니다. Retriever가 실패했거나, 질문에 대한 관련 문서가 없습니다. !!")
    for i, doc in enumerate(retrieved_docs):
        #  여기서 PDF 링크가 포함되었는지 꼭 확인하세요!
        print(f"[{i+1}] Title: {doc.metadata.get('title', 'No title')}")
        print(f"    Preview: {doc.page_content[:100]}...")
    print("------------------------------------\n")
    
    # 3. 전역 변수로 초기화된 rag_chain 사용
    try:
        # get_current_date()는 rag_chain 내에서 호출되므로 여기서 추가 인자는 필요 없음
        result = rag_chain.invoke({"question": question}) 
        return result
    except Exception as e:
        # LLM 호출 오류 (Ollama 연결, 모델 로딩 등) 발생 시
        print(f"RAG 체인 실행 중 치명적인 오류 발생: {e}")
        return f"AI 추론 오류 발생: {e}"
