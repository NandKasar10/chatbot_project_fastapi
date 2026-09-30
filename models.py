from sqlmodel import SQLModel, Field
from pydantic import BaseModel

class Chat(SQLModel, table = True):

    id : int | None = Field(default=None, primary_key=True)
    question : str
    answer : str | None
    status : str = "pending"

class QueryRequest(BaseModel):
    question : str