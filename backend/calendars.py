from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import CalendarRequest, CalendarItem
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

@app.post("/calendar", response_model=list[CalendarItem])
def get_calendar(req: CalendarRequest):
    year, month = req.year, req.month
    target_prefix = f"{year}-{month:02d}"

    DATA_PATH = "../data/school_schedules.json"

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    result = []
    for item in json_data:
        if item["date"].startswith(target_prefix):
            result.append(item)

    return result
