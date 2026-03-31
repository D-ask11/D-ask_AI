import sys
import os
from dotenv import load_dotenv
load_dotenv()

# 프로젝트 루트를 sys.path에 추가 (임포트 에러 방지)
current_file_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_file_path))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import re
from typing import Dict, Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 만든 모듈들 임포트
from ai.core.config import Settings
from ai.core.loaders import DocumentLoader
from ai.utils.parser import QuestionParser
from ai.utils.date_helper import extract_date

class Dask_AI:
    def __init__(self):
        self.settings = Settings()
        
        # 유틸리티 및 로더 초기화
        self.loader = DocumentLoader(self.settings)
        
        # AI 모델 설정
        self.embeddings = HuggingFaceEmbeddings(
                    model_name=self.settings.EMBED_MODEL,
                    model_kwargs={"device": "cpu"}
                )
        api_key = os.getenv("GOOGLE_API_KEY")
        self.llm = ChatGoogleGenerativeAI(
            model=self.settings.LLM_MODEL,
            google_api_key=api_key,
            temperature=0.1,
            convert_system_message_to_human=True # LangChain 버전 이슈 방지용 추가
        )
        
        # 데이터 캐시 및 VectorDB
        self.meal_cache = {}
        self.timetable_cache = {}
        self.vector_db = None
        self._initialize()

    def _initialize(self):
        """데이터 로드 및 시스템 준비"""
        print("로그: Dask_AI 엔진 초기화 중...")
        self._load_meal_data()
        self._load_timetable_data()
        # loaders.py의 기능을 사용하여 DB 설정
        self.vector_db = self.loader.get_vector_db(self.embeddings)
        print("로그: 엔진 준비 완료.")

    def _load_meal_data(self):
        """급식 JSON 파싱 및 캐싱"""
        path = os.path.join(self.settings.DATA_DIR, "school_meal.json")
        if not os.path.exists(path): return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    raw_date = str(item.get("날짜", "")).replace("-", "").strip()
                    if len(raw_date) == 8:
                        date_key = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                        time_key = item.get("시간", "")
                        menu = ", ".join(item.get("요리명", []))
                        if date_key not in self.meal_cache: self.meal_cache[date_key] = {}
                        self.meal_cache[date_key][time_key] = f"[{time_key}] {menu}"
        except Exception as e:
            print(f"급식 데이터 로드 실패: {e}")

    def _load_timetable_data(self):
        """시간표 JSON 파싱 - '원래 과목' 계층까지 완벽하게 파싱"""
        path = os.path.join(self.settings.DATA_DIR, "comcigan.json")
        if not os.path.exists(path): return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    for grade, classes in item.items():
                        for class_name, dates in classes.items():
                            # "1학년", "1반"에서 숫자만 추출
                            g_num = re.search(r"\d+", grade)
                            c_num = re.search(r"\d+", class_name)
                            if not (g_num and c_num): continue
                            
                            class_key = f"{g_num.group()}-{c_num.group()}"
                            if class_key not in self.timetable_cache: 
                                self.timetable_cache[class_key] = {}
                                
                            for r_date, periods in dates.items():
                                # "20260223-월요일" 에서 8자리 날짜만 추출
                                d_match = re.search(r"(\d{8})", r_date)
                                if not d_match: continue
                                d8 = d_match.group(1)
                                d_key = f"{d8[:4]}-{d8[4:6]}-{d8[6:]}" # 2026-02-23 형태
                                
                                lines = []
                                for p_name, info in periods.items():
                                    # 일반 과목 확인
                                    subj = info.get("과목")
                                    teacher = info.get("선생님")
                                    
                                    # 만약 비어있다면 '원래 과목' 안에서 찾기
                                    if not subj and "원래 과목" in info:
                                        orig = info["원래 과목"].get(p_name, {})
                                        subj = orig.get("과목")
                                        teacher = orig.get("선생님")
                                    
                                    if subj:
                                        lines.append(f"{p_name}: {subj} ({teacher})")
                                
                                if lines:
                                    self.timetable_cache[class_key][d_key] = "\n".join(lines)
            print("로그: 시간표 데이터 캐싱 완료.")
        except Exception as e:
            print(f"시간표 데이터 로드 실패: {e}")

    def ask(self, question: str) -> str:
        q_type = QuestionParser.get_query_type(question)
        date = extract_date(question)

        # 급식 질문 처리 (필터링 로직 추가)
        if q_type == "meal":
            meals = self.meal_cache.get(date, {})
            if not meals: return f"{date} 급식 정보가 없습니다."
            
            # 키워드 필터링
            target_time = None
            if any(k in question for k in ["아침", "조식"]): target_time = "조식"
            elif any(k in question for k in ["점심", "중식"]): target_time = "중식"
            elif any(k in question for k in ["저녁", "석식"]): target_time = "석식"
            
            if target_time and target_time in meals:
                return f"### {date} {target_time} 정보 ###\n{meals[target_time]}"
            
            # 특정 끼니 언급 없으면 전체 출력
            return f"{date} 급식 정보 \n" + "\n".join(meals.values())

        # 2. 시간표 질문 처리 (에러 방지 및 로직 개선)
        if q_type == "timetable":
            g, c = QuestionParser.extract_grade_class(question)
            if not g or not c: return "학년과 반 정보를 알려주세요. (예: 1학년 1반)"
            
            res = self.timetable_cache.get(f"{g}-{c}", {}).get(date)
            # 데이터가 비어있는지(교시 내용이 없는지) 체크
            if res and "(" in res and res.count("()") < 3: # 내용이 어느정도 있는 경우
                 return f"{g}-{c} 시간표 ({date}) \n{res}"
            else:
                 return f"{g}학년 {c}반의 {date} 시간표 정보를 찾을 수 없거나 아직 업데이트되지 않았습니다."

        return self._run_rag(question)

    def _run_rag(self, question: str) -> str:
        """VectorDB와 LLM을 사용한 질의응답"""
        if not self.vector_db: return "데이터베이스가 준비되지 않았습니다."
        
        results = self.vector_db.similarity_search_with_score(question, k=3)
        # 설정값(Threshold)에 맞는 문서만 필터링
        docs = [d for d, s in results if s <= self.settings.SIMILARITY_THRESHOLD]
        
        if not docs:
            return "학교 관련 정보에서 답변을 찾을 수 없습니다."
        
        context = "\n".join([d.page_content for d in docs])
        template = "당신은 학교 도우미 D-ASK입니다. 아래 문맥을 사용하여 질문에 답하세요.\n\n문맥:\n{context}\n\n질문: {question}\n\n답변: 단, 마크 다운 문법을 사용하지말고 답변하세요. 또한, pdf가 있을 경우 pdf 링크를 마지막에 출력해 주세요."
        
        prompt = PromptTemplate.from_template(template)
        chain = prompt | self.llm | StrOutputParser()
        
        return chain.invoke({"context": context, "question": question})

# 싱글톤 인스턴스 생성
bot = Dask_AI()