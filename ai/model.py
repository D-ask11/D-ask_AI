# 순서: DB저장 -> json 읽기 -> embedding -> vetorDB -> 유사도 검색 -> 답변 생성
import os
import json
import datetime
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_community.docstore.document import Document
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from typing import List, Dict, Any, Optional

# 설정 및 초기화
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_DIR = os.path.join(BASE_DIR, "..", "chroma.db")
COLLECTION_NAME = "my_rag_collection"

# 임베딩 모델 (global scope 유지)
embedding_model = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-small",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# LLM (global scope 유지)
llm = ChatOllama(model="qwen2.5:1.5b", temperature=0.1)

# [핵심] JSON 데이터 메모리 캐싱 (global scope 유지)
CACHED_MEAL_DATA: Dict[str, Dict[str, str]] = {}
CACHED_TIMETABLE_DATA: Dict[str, Dict[str, str]] = {}

def load_pdf_documents(data_dir):
    """DATA_DIR 내의 모든 PDF 파일을 로드"""
    pdf_docs = []
    for filename in os.listdir(data_dir):
        if filename.endswith(".pdf"):
            file_path = os.path.join(data_dir, filename)
            try:
                loader = PyPDFLoader(file_path)
                # PDF의 각 페이지를 Document 객체로 변환
                pages = loader.load()
                for page in pages:
                    # 메타데이터에 파일 타입과 출처 명시
                    page.metadata["type"] = "school_rule" 
                    page.metadata["source"] = filename
                pdf_docs.extend(pages)
                print(f"로드 성공: {filename}")
            except Exception as e:
                print(f"PDF 로드 실패 ({filename}): {e}")
    return pdf_docs

def init_cached_data():
    """서버 시작 시 급식/시간표 JSON을 메모리에 로드하여 조회용 딕셔너리 구성"""
    global CACHED_MEAL_DATA, CACHED_TIMETABLE_DATA
    
    # 1. 급식 데이터 로드
    meal_path = os.path.join(DATA_DIR, "school_meal.json")
    if os.path.exists(meal_path):
        try:
            with open(meal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    raw_date = str(item.get("날짜", "")).replace("-", "").strip()
                    if len(raw_date) == 8:
                        date_key = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                    else:
                        continue 
                    
                    time_key = item.get("시간", "")
                    menu = ", ".join(item.get("요리명", []))
                    
                    if date_key not in CACHED_MEAL_DATA:
                        CACHED_MEAL_DATA[date_key] = {}
                    CACHED_MEAL_DATA[date_key][time_key] = f"[{time_key}] {menu} ({item.get('칼로리', '')})"
        except Exception as e:
            print(f"급식 데이터 로드 오류: {e}")

    # 2. 시간표 데이터 로드
    time_path = os.path.join(DATA_DIR, "comcigan.json")
    if os.path.exists(time_path):
        try:
            with open(time_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        for grade, classes in item.items():
                            for class_name, dates in classes.items():
                                g_match = re.search(r"\d+", grade)
                                c_match = re.search(r"\d+", class_name)
                                
                                if g_match and c_match:
                                    class_key = f"{g_match.group(0)}-{c_match.group(0)}"
                                else:
                                    class_key = f"{grade}-{class_name}" 

                                if class_key not in CACHED_TIMETABLE_DATA:
                                    CACHED_TIMETABLE_DATA[class_key] = {}
                                
                                for raw_date_key, periods in dates.items():
                                    date_match = re.search(r"(\d{8})", raw_date_key)
                                    if date_match:
                                        raw_date_8digit = date_match.group(1)
                                        date_key = f"{raw_date_8digit[:4]}-{raw_date_8digit[4:6]}-{raw_date_8digit[6:]}"
                                    else:
                                        continue 

                                    lines = []
                                    for period, info in periods.items():
                                        if "원래 과목" in info:
                                            original_data = info["원래 과목"]
                                            # 데이터 구조 처리를 단순화하여 원래 코드 로직 유지
                                            if isinstance(original_data, dict) and period in original_data:
                                                original = original_data[period]
                                                lines.append(f"{period}교시: **{info.get('과목','')}** ({info.get('선생님','')} / *원래: {original.get('과목','')}* )")
                                            else:
                                                lines.append(f"{period}교시: **{info.get('과목','')}** ({info.get('선생님','')} / *원래 변경 정보 오류* )")
                                        else:
                                            lines.append(f"{period}교시: {info.get('과목','')} ({info.get('선생님','')})")

                                    CACHED_TIMETABLE_DATA[class_key][date_key] = "\n".join(lines)
                
        except Exception as e:
            print(f"시간표 데이터 로드 오류: {e}")

# 데이터 로드 실행
init_cached_data()

# JSON -> LangChain Document 로드 및 DB 함수 (DB 구성을 위해 필요)
def load_crawling_json(file_path):
    """일반 공지사항(crawling) 문서를 로드"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    documents = []
    for item in data.get("crawling", []):
        contents = item.get("contents", "")
        pdf_links = item.get("pdf", [])
        link_text = "\n".join([f"- {pdf.get('filename')}: {pdf.get('url')}" for pdf in pdf_links])
        documents.append(Document(page_content=contents + link_text, metadata={"title": item.get("title", ""), "type": "general", "source": "crawling.json"}))
    return documents


def load_all_documents():
    """기존 JSON 데이터와 새로운 PDF 데이터를 모두 로드"""
    docs = []
    
    # 1. 기존 JSON 공지사항 로드
    crawling_path = os.path.join(DATA_DIR, "crawling.json")
    if os.path.exists(crawling_path):
        docs.extend(load_crawling_json(crawling_path))
    
    # 2. 추가된 PDF 문서 로드 (인증제, 기숙사 규정 등)
    docs.extend(load_pdf_documents(DATA_DIR))
    
    print(f"총 {len(docs)}개 Document 생성 완료 (JSON + PDF)")
    return docs

def load_db():
    """ChromaDB를 로드하거나 존재하지 않으면 새로 생성"""
    if not os.path.exists(DB_DIR) or not os.listdir(DB_DIR):
        print("VectorDB 파일이 없으므로, 새롭게 생성합니다...")
        documents = load_all_documents()
        if not documents:
            print("경고: DB 생성을 위한 문서(crawling/schedule)가 없습니다.")
            return None

        vectordb = Chroma.from_documents(
            documents,
            embedding=embedding_model,
            persist_directory=DB_DIR,
            collection_name=COLLECTION_NAME
        )
        print("VectorDB 최초 생성 완료")
    else:
        try:
            vectordb = Chroma(
                embedding_function=embedding_model,
                persist_directory=DB_DIR,
                collection_name=COLLECTION_NAME
            )
            print("기존 VectorDB 불러오기 완료")
        except Exception as e:
            print(f"경고: VectorDB 로드 중 심각한 오류 발생. 오류: {e}")
            return None
    
    return vectordb

# Helper 함수: 날짜, 요일, 학년/반 추출
def get_current_date_str():
    """현재 날짜를 YYYY-MM-DD 형식 문자열로 반환"""
    return datetime.datetime.now().strftime("%Y-%m-%d")

def extract_grade_class(question: str) -> tuple[Optional[str], Optional[str]]:
    """질문에서 학년과 반 정보를 추출 (예: 1학년 4반, 1-4)"""
    match1 = re.search(r"(\d)\s*학년\s*(\d)\s*반", question)
    if match1:
        return match1.group(1), match1.group(2)
    
    match2 = re.search(r"(\d)[/-](\d)", question)
    if match2:
        return match2.group(1), match2.group(2)
        
    return None, None

def extract_date_from_question(question: str) -> Optional[str]:
    """질문에서 날짜/요일을 추출하여 YYYY-MM-DD 형식으로 반환"""
    today = datetime.datetime.now()
    
    day_map = {"월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, 
               "토요일": 5, "일요일": 6, "월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
    
    # 1. 요일 처리 
    for day_name, day_index in day_map.items():
        if day_name in question:
            current_day_index = today.weekday()
            days_until_target = (day_index - current_day_index + 7) % 7
            target_date = today + datetime.timedelta(days=days_until_target)
            return target_date.strftime("%Y-%m-%d")

    # 2. 오늘/내일 처리
    if "오늘" in question:
        return today.strftime("%Y-%m-%d")
    if "내일" in question:
        return (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 3. 구체적인 날짜 (YYYY년 MM월 DD일)
    full_date_match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", question)
    if full_date_match:
        y, m, d = full_date_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    
    # 4. 연도 없는 날짜 (MM월 DD일)
    partial_date_match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", question)
    if partial_date_match:
        m, d = partial_date_match.groups()
        return f"{today.year}-{int(m):02d}-{int(d):02d}"
        
    return None

def get_type_from_question(question: str) -> str:
    if any(k in question for k in ["급식","아침","조식","점심","중식","저녁","석식","메뉴","밥"]):
        return "meal"
    if any(k in question for k in ["시간표","교시","수업"]):
        return "timetable"
    if any(k in question for k in ["일정","행사","언제","날짜"]):
        return "schedule"
    return "general"

def docs_to_text(docs: List[Document]) -> str:
    # RAG 검색 결과를 프롬프트에 넣을 텍스트로 변환
    return "\n---\n".join([f"Source: {doc.metadata.get('source', 'Unknown')} (Type: {doc.metadata.get('type', 'Unknown')})\n{doc.page_content}" for doc in docs])

# 핸들러: 급식 (Meal)
def handle_meal(question: str) -> str:
    """급식 질문에 대해 캐시된 데이터를 조회하여 정확한 정보를 반환"""
    target_date = extract_date_from_question(question)
    if not target_date:
        target_date = get_current_date_str()

    day_data = CACHED_MEAL_DATA.get(target_date)
    
    if not day_data:
        return f"죄송합니다. 날짜({target_date})에 대한 급식 정보가 데이터 파일에 없습니다."

    result = []
    
    # 시간대 필터링
    if any(k in question for k in ["아침", "조식"]):
        if "조식" in day_data: result.append(day_data["조식"])
    elif any(k in question for k in ["점심", "중식"]):
        if "중식" in day_data: result.append(day_data["중식"])
    elif any(k in question for k in ["저녁", "석식"]):
        if "석식" in day_data: result.append(day_data["석식"])
    else:
        # 시간대 언급이 없으면 해당 날짜의 모든 급식 출력
        for time_k in ["조식", "중식", "석식"]:
            if time_k in day_data:
                result.append(day_data[time_k])

    if not result:
        return f"{target_date}에는 해당 시간대 급식이 없습니다."
        
    return f"## {target_date} 급식 정보 ##\n" + "\n".join(result)


# 핸들러: 시간표 (Timetable)
def handle_timetable(question: str) -> str:
    """시간표 질문에 대해 캐시된 데이터를 조회하여 정확한 정보를 반환"""
    grade, cls = extract_grade_class(question)
    target_date = extract_date_from_question(question)

    if not grade or not cls:
        return "시간표를 찾으려면 학년과 반 정보를 정확히 입력해주세요. (예: 1학년 1반)"
    if not target_date:
        target_date = get_current_date_str()
        
    class_key = f"{grade}-{cls}"
    class_data = CACHED_TIMETABLE_DATA.get(class_key)
    
    if not class_data:
        return f"{grade}학년 {cls}반의 시간표 데이터가 캐시에 없습니다. (키: {class_key})"
        
    timetable_text = class_data.get(target_date)
    
    if not timetable_text:
        day_of_week = datetime.datetime.strptime(target_date, "%Y-%m-%d").strftime("%A")
        return f"{target_date} ({day_of_week}) 일자 {grade}학년 {cls}반 시간표 정보는 데이터 파일에 없습니다."

    return f"## {target_date} {grade}학년 {cls}반 시간표 ##\n{timetable_text}"

# -------------------------
# 프롬프트 템플릿 (general 질문용)
# -------------------------
template = """
당신은 대덕소프트웨어마이스터 고등학교 정보 도우미입니다.
아래 [문맥 정보]를 바탕으로 사용자 [질문]에 한국어로 정확히 답변하세요.

**주의사항:**
1. 문맥 정보에 없는 내용은 절대 추측하거나 지어내지 마세요.
2. 정보가 없으면 '관련 정보를 찾을 수 없습니다'라고만 답변하세요.
3. 별표(**), 샵(#), 대시(-), 리스트 기호 등 모든 마크다운 형식을 절대 사용하지 마세요.
4. 오직 줄바꿈과 일반 텍스트로만 답변하세요.
5. 참고 자료가 있다면 마지막에 '참고 자료: 파일명' 형태로 한 줄로 작성하세요.

[현재 시점]: {current_date}

[문맥 정보]
{context}

[질문]
{question}

---
[답변]

[참고 자료]
"""

# Main RAG Inference
VECTOR_DB = load_db()

def rag_inference(question: str) -> str:
    q_type = get_type_from_question(question)
    current_date_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %A")
    
    print(f"\n[DEBUG] 질문: {question}")
    print(f"[DEBUG] 판정 타입: {q_type}")

    # 1. 특수 질문 처리 (LLM 미사용)
    if q_type == "meal": return handle_meal(question)
    if q_type == "timetable": return handle_timetable(question)
    if q_type == "schedule": return "학사일정은 캘린더를 이용해주세요."

    # 2. 일반 질문 처리 (RAG + LLM)
    if q_type == "general":
        try:
            if VECTOR_DB is None:
                return "경고: DB에 저장된 일반 정보 문서를 찾을 수 없거나 DB 로드에 실패했습니다."
            
            # 검색 및 점수 확인
            results = VECTOR_DB.similarity_search_with_score(question, k=3)
            print(f"[DEBUG] 검색된 결과 개수: {len(results)}")

            docs = []
            for i, (doc, score) in enumerate(results):
                # 점수 디버깅 출력
                print(f"[DEBUG] 결과 {i+1} 점수: {score:.4f} | 내용: {doc.page_content[:20]}...")
                
                # 임계값 필터링 (0.25)
                if score <= 0.25:
                    docs.append(doc)
            
            # 검색 결과 검증: 필터링 후 문서가 없으면 LLM에 질문을 넘기지 않음
            if not docs:
                print("!! RAG 검색 결과 없음 (유사도 부족) !!")
                return "현재 DB에는 해당 기술 정보가 없습니다."

            # --- [디버깅 출력: 필터링된 실제 문맥 정보] ---
            context_text = docs_to_text(docs)
            print("\n--- RAG 검색 결과 (Context) ---")
            print(context_text)
            print("------------------------------\n")

            # 문서를 찾은 경우에만 LLM 실행
            print(f"[DEBUG] {len(docs)}개의 문서를 바탕으로 답변 생성 중...")
            
            prompt = PromptTemplate(
                input_variables=["context", "question", "current_date"], 
                template=template
            )
            chain = prompt | llm | StrOutputParser()
            
            return chain.invoke({
                "context": context_text,
                "question": question,
                "current_date": current_date_str
            })

        except Exception as e:
            print(f"[ERROR] 발생: {e}")
            return f"오류가 발생했습니다: {e}"

    return "질문 유형을 인식할 수 없습니다. '급식', '시간표', '일정' 또는 일반 질문으로 다시 시도해주세요."