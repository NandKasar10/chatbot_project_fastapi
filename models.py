from sqlmodel import SQLModel, Field, Relationship
from pydantic import BaseModel
from enum import Enum
from datetime import datetime,timezone

class Chat(SQLModel, table = True):

    id : int | None = Field(default=None, primary_key=True)
    question : str
    answer : str | None
    status : str = "pending"

class QueryRequest(BaseModel):
    question : str

class Roles(str,Enum):
    model = "model"
    user = "user"

class Thread(SQLModel, table=True):

    id : int | None = Field(default=None,  primary_key=True)
    created_at : datetime = Field(default_factory= lambda : datetime.now(timezone.utc))

    messages : list["Message"] = Relationship(back_populates="thread")

class Message(SQLModel, table = True):

    id : int | None = Field(default=None, primary_key=True)

    thread_id : int | None = Field(default=None, foreign_key="thread.id")

    roles : Roles

    content : str

    thread : Thread | None = Relationship(back_populates="messages")