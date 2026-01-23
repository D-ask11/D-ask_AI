from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from models import CalendarItem
import json

app = FastAPI()

# CORS 설정 (GET도 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://d-ask.vercel.app"],
    allow_methods=["GET"], 
    allow_headers=["Content-Type"],
)

# # GET으로 변경, 쿼리 파라미터 사용
@app.get("/calendar", response_model=list[CalendarItem])
def get_calendar(year: int, month: int):
    target_prefix_hyphen = f"{year}-{month:02d}" 
    target_prefix_clean = f"{year}{month:02d}"  
    
    DATA_PATH = "/app/data/school_schedules.json"

    if not os.path.exists(DATA_PATH):
        return []

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        result = []
        for item in json_data:
            raw_date = item.get("date", "").strip()
            
            if raw_date.startswith(target_prefix_hyphen) or raw_date.startswith(target_prefix_clean):
                
                clean_date_8bit = raw_date.replace("-", "")
                
                if len(clean_date_8bit) == 8:
                    item["date"] = clean_date_8bit
                    result.append(item)

        return result

    except Exception:
        return []