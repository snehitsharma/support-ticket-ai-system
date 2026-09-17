from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from anomalies import detect_anomalies
from ingestion.ingest import run_ingestion
from query import answer_query

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_ingestion()
    yield

app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    answer: str


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        result = answer_query(req.question)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Query failed: {exc}")
    return result


@app.get("/anomalies")
def anomalies():
    try:
        return detect_anomalies()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anomaly detection failed: {exc}")


@app.get("/health")
def health():
    return {"status": "ok"}
