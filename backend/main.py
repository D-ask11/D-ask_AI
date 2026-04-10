import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.chat_history import router as chat_history_router
from backend.calendars import router as calendars_router
from backend.login import router as login_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_history_router)
app.include_router(calendars_router)
app.include_router(login_router)

@app.get("/")
async def root():
    return {"message": "backend 서버가 작동 중입니다."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
