from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import JSONResponse


class SummarizeRequest(BaseModel):
    github_url: str


app = FastAPI(title="GitHub Summarizer API", version="0.1.0")


@app.post("/summarize")
def summarize(payload: SummarizeRequest) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "Not implemented"},
    )
