from pydantic import BaseModel

class CalendarRequest(BaseModel):
    year: int
    month: int

class CalendarItem(BaseModel):
    title: str
    date: str
