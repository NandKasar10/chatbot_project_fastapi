from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from models import Chat, QueryRequest, Message, Thread,Roles
from database import create_db_and_tables, get_session, engine
from sqlmodel import Session

from dotenv import load_dotenv
import os
from google import genai

from tenacity import retry, wait_exponential, stop_after_attempt
from google.genai import types
from tools import get_stock_price

import numpy as np

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

@app.post("/chat/new_thread")
async def chat_with_history(
    message : str,
    session : Session = Depends(get_session),
):
    thread = Thread()

    session.add(thread)
    session.commit()
    session.refresh(thread)

    chat = client.aio.chats.create(
        model = MODEL_NAME
    )

    response = await chat.send_message(message)

    message1 = Message(thread_id = thread.id,roles = Roles.user, content=message)

    message2 = Message(thread_id = thread.id,roles = Roles.model, content=response.text)

    session.add(message1)
    session.add(message2)

    session.commit()

    return {"thread_id" : thread.id, "user_message" : message, "model_response" : response.text}


@app.post("/chat/{thread_id}")
async def chat_with_history(
    thread_id : int,
    message : str,
    session : Session = Depends(get_session),
):
    thread = session.get(Thread,thread_id)

    if not thread :
        raise HTTPException(status_code=404,detail="No thread associated with given thread id")
    
    formatted_history = []

    for msg in thread.messages:

        role_string = msg.roles.value

        formatted_history.append(
            types.Content(
                role=role_string,
                parts= [types.Part.from_text(text=msg.content)]
            )
        )

    chat = client.aio.chats.create(
        model = MODEL_NAME,
        history=formatted_history
    )

    response = await chat.send_message(message)

    message1 = Message(thread_id = thread_id,roles = Roles.user, content=message)

    message2 = Message(thread_id = thread_id,roles = Roles.model, content=response.text)

    session.add(message1)
    session.add(message2)

    session.commit()

    return {"thread_id" : thread_id, "user_message" : message, "model_response" : response.text}

knowledge_base = []


def smart_chunker(text : str, max_size : int = 250) -> list[str]:
    sentences = text.split('. ')
    curr_chunk = ""
    chunks = []

    for sentence in sentences:

        if not sentence.endswith('.'):
            sentence = sentence.strip() + '.'

        if len(curr_chunk) + len(sentence) < max_size :
            curr_chunk += " " + sentence

        else :
            
            if curr_chunk.strip():
                chunks.append(curr_chunk.strip())

            curr_chunk = sentence
    
    if curr_chunk.strip():
        chunks.append(curr_chunk.strip())

    return chunks
    


@app.post("/upload_knowledge")
async def upload_knowledge(
    text : str
):
    if not text.strip():
        raise HTTPException(status_code=404, detail="Knowledge can't be empty")
    
    chunks = smart_chunker(text=text)

    result = await client.aio.models.embed_content(
        model="gemini-embedding-001",
        contents=chunks
    )

    for i, chunk in enumerate(chunks):

        knowledge_base.append({
            "chunk" : chunk,
            "embedding" : result.embeddings[i].values
        })

    return {
        "message" : f"Successfully uploaded {len(chunks)} chunks",
        "knowledge_base_size" : len(knowledge_base)
    }

@app.post("/ask-from-knowledge")
async def ask_from_knowledge(
    question : str
):
    
    if not knowledge_base : 
        raise HTTPException(status_code=400, detail="Knowledge is not provided yet, knowledge base is empty.")
    
    if not question.strip():
        raise HTTPException(status_code=404, detail="Question can't be empty.")
    
    question_result = await client.aio.models.embed_content(
        model = "gemini-embedding-001",
        contents=question
    )

    question_vector = question_result.embeddings[0].values

    # best_score = -1
    # best_chunk = "" 

    # for item in knowledge_base :

    #     chunk_vector = item["embedding"]

    #     score = np.dot(question_vector, chunk_vector)

    #     if score > best_score:
    #         best_chunk = item["chunk"]
    #         best_score = score

        
    score_list = []

    for item in knowledge_base:

        score = np.dot(question_vector,item["embedding"])
        score_list.append((score,item["chunk"]))

    score_list.sort(key=lambda x : x[0], reverse=True)

    top_3 = score_list[:3]

    combined_context = "\n---\n".join([chunk for score, chunk in top_3])

    prompt = f"""
    System/Instruction: You are an expert assistant. Answer the user's question STRICTLY using ONLY the provided context. 
    If the answer is not in the context, say "I don't have enough information". Do not use outside knowledge.

    Context: {combined_context}

    Question: {question}
    """

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    return{
        "answer" : response.text,
        "context" : combined_context
    }


