from fastapi import FastAPI, HTTPException
from models import CalendarRequest, CalendarItem
from database import database
from datetime import datetime

app = FastAPI()

@app.post("/calendar", response_model=list[CalendarItem])
def get_calendar(req: CalendarRequest):
    year, month = req.year, req.month
    today = datetime.today()

    # 예외 처리 1: 너무 과거 or 미래(404)
    if (year, month) not in database:
        raise HTTPException(status_code=404, detail="아직 오지 않았거나 찾을 수 없는 달입니다.")

    # 데이터 반환
    return database[(year, month)]
