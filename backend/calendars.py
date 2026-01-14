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

# GET으로 변경, 쿼리 파라미터 사용
@app.get("/calendar", response_model=list[CalendarItem])
def get_calendar(year: int, month: int):
    target_prefix = f"{year}-{month:02d}"

    DATA_PATH = "../data/school_schedules.json"

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    result = []
    for item in json_data:
        if item["date"].startswith(target_prefix):
            result.append(item)

    return result
