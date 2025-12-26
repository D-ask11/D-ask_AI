from fastapi.middleware.cors import CORSMiddleware
from models import CalendarRequest, CalendarItem
from json import json
from datetime import datetime
from fastapi import FastAPI, HTTPException

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
    today = datetime.today()

    if (year, month) not in database:
        return ""

    return database[(year, month)]
