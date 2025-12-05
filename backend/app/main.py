from fastapi import FastAPI
from typing import List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from .models import ProgramType, FieldInput, Quote
from .pricing import calculate_quote

app = FastAPI(title="TerraNet Client Onboarding API")

origins = [
    "http://localhost:63342",
    "http://127.0.0.1:63342",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}


class QuoteRequest(BaseModel):
    quote_id: str
    grower_id: str
    program_type: ProgramType
    fields: List[FieldInput]


@app.post("/quote/preview", response_model=Quote)
def quote_preview(payload: QuoteRequest):
    """
    Takes a list of fields + chosen program, returns pricing breakdown.
    """
    return calculate_quote(
        quote_id=payload.quote_id,
        grower_id=payload.grower_id,
        program_type=payload.program_type,
        fields=payload.fields,
    )
