from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from ..models import ProgramType, FieldInput, Quote
from ..pricing import calculate_quote

router = APIRouter()


class QuoteRequest(BaseModel):
    quote_id: str
    grower_id: str
    program_type: ProgramType
    fields: List[FieldInput]


@router.post("/quote/preview", response_model=Quote)
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
