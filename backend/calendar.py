from fastapi.middleware.cors import CORSMiddleware
from models import CalendarRequest, CalendarItem
from database import database
from datetime import datetime

app = FastAPI()  

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5501/calenderPage/index.html"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

@app.post("/calendar", response_model=list[CalendarItem])
def get_calendar(req: CalendarRequest):
    year, month = req.year, req.month
    today = datetime.today()

    if (year, month) not in database:
        raise HTTPException(status_code=404, detail="아직 오지 않았거나 찾을 수 없는 달입니다.")

    return database[(year, month)]
