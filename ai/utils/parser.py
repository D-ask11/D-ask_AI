import re
from typing import Optional, Tuple

class QuestionParser:
    @staticmethod
    def extract_grade_class(question: str) -> Tuple[Optional[str], Optional[str]]:
        """질문에서 학년과 반 정보를 추출 (예: 1학년 4반, 1-4, 1/4)"""
        # 1. '1학년 4반' 패턴
        match1 = re.search(r"(\d)\s*학년\s*(\d)\s*반", question)
        if match1:
            return match1.group(1), match1.group(2)
        
        # 2. '1-4' 또는 '1/4' 패턴
        match2 = re.search(r"(\d)[/-](\d)", question)
        if match2:
            return match2.group(1), match2.group(2)
            
        return None, None

    @staticmethod
    def get_query_type(question: str) -> str:
        """질문의 의도를 분류"""
        if any(k in question for k in ["급식", "밥", "메뉴", "석식", "중식", "조식"]):
            return "meal"
        if any(k in question for k in ["시간표", "교시", "수업"]):
            return "timetable"
        return "general"