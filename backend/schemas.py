from pydantic import BaseModel

    
class userquestion(BaseModel):
    question: str
    
class AIanswer(BaseModel):
    answer:str
