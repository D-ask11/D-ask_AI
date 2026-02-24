import datetime
import re

def extract_date(question: str) -> str:
    """질문 속 키워드를 분석해 YYYY-MM-DD 형식의 날짜 문자열 반환"""
    today = datetime.datetime.now()
    
    # 요일 처리
    day_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
    for d_name, d_idx in day_map.items():
        if d_name in question and "요일" in question or d_name in ["월", "화", "수", "목", "금"]:
            if d_name in question:
                days_diff = (d_idx - today.weekday() + 7) % 7
                return (today + datetime.timedelta(days=days_diff)).strftime("%Y-%m-%d")

    if "오늘" in question: return today.strftime("%Y-%m-%d")
    if "내일" in question: return (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 구체적 날짜 (MM월 DD일)
    match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", question)
    if match:
        m, d = match.groups()
        return f"{today.year}-{int(m):02d}-{int(d):02d}"
        
    return today.strftime("%Y-%m-%d")