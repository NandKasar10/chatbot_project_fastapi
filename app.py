from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from models import Chat, QueryRequest
from database import create_db_and_tables, get_session, engine
from sqlmodel import Session

from dotenv import load_dotenv
import os
from google import genai

from tenacity import retry, wait_exponential, stop_after_attempt
from google.genai import types
from tools import get_stock_price

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

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)
async def gemini_api_call(question : str):

    chat = client.aio.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            tools=[get_stock_price],
        )
    )

    response = await chat.send_message(question)

    return response.text

async def gemini_response(id : int):

    with Session(engine) as session:

        chat = session.get(Chat,id)

        if not chat:
            return
        
        try :

            response = await gemini_api_call(chat.question)

            chat.answer = response
            chat.status = "completed"

        except Exception as e:
            
            print(f"Gemini api call failed : {e}")
            chat.answer = "Gemini failed to generate response"
            chat.status = "failed"

        finally :

            session.commit()


@app.post("/asking/")
async def asking(
    request : QueryRequest,
    background_tasks : BackgroundTasks,
    session : Session = Depends(get_session)
):
    
    chat = Chat(question=request.question, status="pending")

    session.add(chat)
    session.commit()
    session.refresh(chat)

    background_tasks.add_task(gemini_response, chat.id)

    return {"id":chat.id, "question" : request.question, "status" : "pending"}

@app.get("/status/{task_id}")
async def get_status(
    task_id : int,
    session : Session = Depends(get_session)
):
    
    chat = session.get(Chat, task_id)

    if not chat:
        raise HTTPException(status_code=404, detail="chat withb specified id does not exist")
    
    return{"id" : task_id, "question" : chat.question, "answer" : chat.answer}