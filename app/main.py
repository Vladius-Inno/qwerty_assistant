from fastapi import FastAPI
from pydantic import BaseModel
import os

app = FastAPI(title="Research Assistant API")

class QueryRequest(BaseModel):
    q: str

@app.get("/")
def root():
    return {"OKAY": True}

@app.post("/query")
def query(req: QueryRequest):
    # Здесь будет вызов NLU -> dispatcher -> pipeline
    return {"query": req.q, "result": "пока заглушка"}
