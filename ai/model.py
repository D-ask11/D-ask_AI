# 순서: DB저장 -> json 읽기 -> embedding -> vetorDB -> 유사도 검색 -> 답변 생성
import os
import json
import datetime
import re
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
    """모든 JSON을 LangChain Document로 로드 (DB 생성용)"""
    docs = []
    docs.extend(load_crawling_json(os.path.join(DATA_DIR, "crawling.json")))
    print(f"총 {len(docs)}개 Document 생성 (일반 및 학사일정)")
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
1. [문맥 정보]에 없는 내용은 절대 추측하거나 지어내지 마세요.
2. 정보가 없다고 명시되어 있으면, '관련 정보를 찾을 수 없습니다'라고 답변하세요.
3. 답변은 [답변] 섹션만 출력하고, PDF 링크는 [참고 자료] 섹션에만 Markdown 리스트로 나열하세요. 링크가 없으면 '없음'이라고 명확히 출력하세요.

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
def rag_inference(question: str) -> str:
    q_type = get_type_from_question(question)
    context_text = ""
    current_date_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %A")

    # 1. 급식/시간표/일정은 LLM 추론 없이 바로 답변 (빠른 응답)
    if q_type == "meal":
        context_text = handle_meal(question)
        # LLM을 거치지 않으므로 프롬프트 템플릿 형식에 맞게 직접 포맷팅
        return f"[답변]\n{context_text}\n\n[참고 자료]\n없음"
        
    elif q_type == "timetable":
        context_text = handle_timetable(question)
        # LLM을 거치지 않으므로 프롬프트 템플릿 형식에 맞게 직접 포맷팅
        return f"[답변]\n{context_text}\n\n[참고 자료]\n없음"
        
    elif q_type == "schedule":
        # RAG나 LLM을 거치지 않고 바로 응답을 반환 (고정 답변)
        return "[답변]\n별도의 학사일정 정보는 제공하지 않으며, 학교 공식 캘린더를 참고해주세요.\n\n[참고 자료]\n없음"
    
    # 2. 일반 정보(general)는 ChromaDB 검색 및 LLM 추론 (RAG)
    elif q_type == "general":
        try:
            vectordb = load_db() 
            
            if vectordb is None:
                context_text = "경고: DB에 저장된 일반 정보 문서를 찾을 수 없거나 DB 로드에 실패했습니다."
            else:
                search_kwargs = {"k": 5}
                retriever = vectordb.as_retriever(search_kwargs=search_kwargs)
                docs = retriever.invoke(question)
                context_text = docs_to_text(docs)
                
                # --- [디버깅 출력 유지] ---
                print("\n--- RAG 검색 결과 (Context) ---")
                if docs:
                    print(context_text)
                else:
                    print("!! RAG 검색 결과 없음 !!")
                print("------------------------------\n")
            
                if not context_text:
                    context_text = "죄송합니다. 요청하신 정보에 대한 문서를 찾을 수 없습니다."
        
        except Exception as e:
            context_text = f"**[DB 검색 오류 발생]** {e}"
        
        # 3. LLM 생성 (general 질문에만 LLM 사용)
        prompt = PromptTemplate(
            input_variables=["context", "question", "current_date"],
            template=template
        )
        
        # 체인을 여기서 정의하여 general 질문에만 사용
        chain = prompt | llm | StrOutputParser()
        
        try:
            response = chain.invoke({
                "context": context_text, 
                "question": question,
                "current_date": current_date_str
            })
            return response
        except Exception as e:
            return f"AI 추론 중 오류 발생: {e}"
            
    # 정의되지 않은 유형은 일반 질문으로 처리되도록 함
    return "질문 유형을 인식할 수 없습니다. '급식', '시간표', '일정' 또는 일반 질문으로 다시 시도해주세요."
