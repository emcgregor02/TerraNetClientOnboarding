from typing import List, Literal, Optional
from pydantic import BaseModel


# The two program types we talked about
ProgramType = Literal["REMOTE_ONLY", "SPRAYER_PLUS_REMOTE"]


class FieldInput(BaseModel):
    """
    Minimal info the front-end sends when it wants a quote line
    for a field.
    """
    field_id: str
    name: str
    acres: float


class QuoteLine(BaseModel):
    field_id: str
    field_name: str
    acres: float
    annual_amount: float  # $/year for this field


class Quote(BaseModel):
    quote_id: str
    grower_id: str
    program_type: ProgramType
    lines: List[QuoteLine]
    annual_total: float      # sum of all fields per year
    sprayer_fee: float       # 0 or 2000
    total_due_first_year: float  # annual_total + sprayer_fee
