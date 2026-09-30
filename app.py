from fastapi import FastAPI, HTTPException, Depends
from models import Chat, QueryRequest
from database import create_db_and_tables, get_session
from sqlmodel import Session

from dotenv import load_dotenv
import os
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("gemini api key not provided")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

app = FastAPI()

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.post("/ask/")
async def asking(
    request : QueryRequest,
    session : Session = Depends(get_session)
):
    
    if not request.question.strip():
        raise HTTPException(status_code=404, detail="empty string can't be proccessed")
    
    try:

        chat = Chat(question=request.question)

        session.add(chat)
        session.commit()
        session.refresh(chat)

        response = await client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=request.question
        )

        chat.answer = response.text
        chat.status = "completed"

        session.commit()

        return response.text


    except Exception as e :

        print("Gemini Api not responding",e)

        raise HTTPException(status_code=503, detail="Gemini api not responding")

