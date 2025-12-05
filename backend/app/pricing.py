from typing import List
from .models import ProgramType, FieldInput, QuoteLine, Quote


# Pricing constants (easy to tweak later)
REMOTE_ONLY_RATE = 7.0        # $/ac/year
SPRAYER_RATE = 5.0            # $/ac/year
SPRAYER_SETUP_FEE = 2000.0    # one-time


def calculate_quote(
    quote_id: str,
    grower_id: str,
    program_type: ProgramType,
    fields: List[FieldInput],
) -> Quote:
    """
    Core pricing engine for TerraNet onboarding MVP.
    """

    if program_type == "REMOTE_ONLY":
        per_acre_rate = REMOTE_ONLY_RATE
        sprayer_fee = 0.0
    else:
        per_acre_rate = SPRAYER_RATE
        sprayer_fee = SPRAYER_SETUP_FEE

    lines: List[QuoteLine] = []
    annual_total = 0.0

    for f in fields:
        annual_amount = f.acres * per_acre_rate
        annual_total += annual_amount

        lines.append(
            QuoteLine(
                field_id=f.field_id,
                field_name=f.name,
                acres=f.acres,
                annual_amount=annual_amount,
            )
        )

    total_due_first_year = annual_total + sprayer_fee

    return Quote(
        quote_id=quote_id,
        grower_id=grower_id,
        program_type=program_type,
        lines=lines,
        annual_total=annual_total,
        sprayer_fee=sprayer_fee,
        total_due_first_year=total_due_first_year,
    )
