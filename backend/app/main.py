from typing import List, Optional
from pathlib import Path
import csv
import json
import time
import shutil

from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from .models import ProgramType, FieldInput, Quote
from .pricing import calculate_quote

# -------------------------------------------------------------------
# App + CORS
# -------------------------------------------------------------------

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

@app.delete("/orders/{quote_id}")
def delete_order(quote_id: str):
    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

    shutil.rmtree(order_dir)
    return {"quote_id": quote_id, "deleted": True}

# -------------------------------------------------------------------
# Quote preview models + endpoint
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# Checkout models + storage helpers
# -------------------------------------------------------------------

class GrowerInfo(BaseModel):
    name: str
    email: EmailStr
    farmName: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class CheckoutStartRequest(BaseModel):
    grower: GrowerInfo
    program_type: str            # keep as raw string for now
    fields: List[dict]           # accept whatever the frontend sends for now


class CheckoutStartResponse(BaseModel):
    quote_id: str
    message: str

class OrderSummary(BaseModel):
    quote_id: str
    grower_name: str
    program_type: str
    field_count: int
    total_acres: float
    total_annual_cost: float
    created_at: str  # ISO string for now

class OrderDetail(BaseModel):
    quote_id: str
    grower: GrowerInfo
    program_type: str
    fields: List[dict]
    created_at: str
    exports: dict  # file paths to CSV/GeoJSON/etc.
    status: str

ALLOWED_STATUSES = [
    "Quoted",
    "Awaiting Payment",
    "Paid",
    "Onboarding Started",
    "Completed",
]


class OrderSummary(BaseModel):
    quote_id: str
    grower_name: str
    program_type: str
    field_count: int
    total_acres: float
    total_annual_cost: float
    created_at: str
    status: str  # ⬅ NEW

class StatusUpdate(BaseModel):
    status: str


ORDERS_ROOT = Path(__file__).resolve().parent.parent / "orders"
STATUS_FILENAME = "status.txt"


def save_checkout_start(quote_id: str, payload: CheckoutStartRequest) -> None:
    ORDERS_ROOT.mkdir(exist_ok=True)
    order_dir = ORDERS_ROOT / quote_id
    order_dir.mkdir(exist_ok=True)

    # 1) Raw JSON snapshot
    out_path = order_dir / "checkout_start.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload.dict(), f, indent=2)

    # 2) Client info CSV
    write_client_csv(order_dir, quote_id, payload)

    # 3) Field summary CSV
    write_fields_csv(order_dir, quote_id, payload)

    # 4) Field geometries GeoJSON
    write_fields_geojson(order_dir, payload)
    # ... existing JSON/CSV/GeoJSON writing ...

    # 5) Initialize status if not present
    status_path = order_dir / STATUS_FILENAME
    if not status_path.exists():
        status_path.write_text("Quoted", encoding="utf-8")



def write_client_csv(order_dir: Path, quote_id: str, payload: CheckoutStartRequest) -> None:
    csv_path = order_dir / "client_info.csv"
    g = payload.grower

    fields = payload.fields or []

    # compute totals from fields
    total_acres = 0.0
    total_annual = 0.0
    for f in fields:
        try:
            acres = float(f.get("acres", 0) or 0)
        except (TypeError, ValueError):
            acres = 0.0
        total_acres += acres

        try:
            annual = float(f.get("annualCost", 0) or 0)
        except (TypeError, ValueError):
            annual = 0.0
        total_annual += annual

    headers = [
        "quote_id",
        "grower_name",
        "grower_email",
        "farm_name",
        "phone",
        "notes",
        "program_type",
        "field_count",
        "total_acres",
        "total_annual_cost",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerow({
            "quote_id": quote_id,
            "grower_name": g.name,
            "grower_email": g.email,
            "farm_name": g.farmName or "",
            "phone": g.phone or "",
            "notes": g.notes or "",
            "program_type": payload.program_type,
            "field_count": len(fields),
            "total_acres": round(total_acres, 2),
            "total_annual_cost": round(total_annual, 2),
        })


def write_fields_csv(order_dir: Path, quote_id: str, payload: CheckoutStartRequest) -> None:
    csv_path = order_dir / "fields.csv"
    g = payload.grower

    headers = [
        "quote_id",
        "field_id",
        "name",
        "acres",
        "crop_program",
        "notes",
        "annual_cost",
        "program_type",
        "grower_name",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for field in payload.fields or []:
            writer.writerow({
                "quote_id": quote_id,
                "field_id": field.get("id", ""),
                "name": field.get("name", ""),
                "acres": field.get("acres", ""),
                "crop_program": field.get("cropProgram", ""),
                "notes": field.get("notes", ""),
                "annual_cost": field.get("annualCost", ""),
                "program_type": payload.program_type,
                "grower_name": g.name,
            })



def write_fields_geojson(order_dir: Path, payload: CheckoutStartRequest) -> None:
    """
    Geometry-focused export.
    - Writes a combined fields.geojson (all fields)
    - Writes one GeoJSON per field under fields_geojson/
    """
    fields = payload.fields or []
    if not fields:
        return

    fields_dir = order_dir / "fields_geojson"
    fields_dir.mkdir(exist_ok=True)

    all_features = []

    for field in fields:
        geom_feature = field.get("geometry")
        if not geom_feature:
            continue

        # If geometry is already a Feature (as in Leaflet export), use it directly
        if geom_feature.get("type") == "Feature":
            feature = geom_feature
        else:
            # Otherwise, wrap raw geometry into a Feature
            feature = {
                "type": "Feature",
                "properties": {},
                "geometry": geom_feature,
            }

        # Attach / update properties
        props = feature.setdefault("properties", {})
        props.update({
            "field_id": field.get("id", ""),
            "name": field.get("name", ""),
            "acres": field.get("acres", None),
            "crop_program": field.get("cropProgram", ""),
        })

        all_features.append(feature)

        # Write single-field GeoJSON
        single_fc = {
            "type": "FeatureCollection",
            "features": [feature],
        }
        field_id = field.get("id") or "field"
        per_path = fields_dir / f"{field_id}.geojson"
        with per_path.open("w", encoding="utf-8") as f:
            json.dump(single_fc, f, indent=2)

    # Write combined GeoJSON (all fields)
    if all_features:
        geojson_obj = {
            "type": "FeatureCollection",
            "features": all_features,
        }
        geojson_path = order_dir / "fields.geojson"
        with geojson_path.open("w", encoding="utf-8") as f:
            json.dump(geojson_obj, f, indent=2)

@app.get("/orders", response_model=List[OrderSummary])
def list_orders():
    """
    Lists existing orders by reading the orders/ directory and client_info.csv files.
    """
    summaries: List[OrderSummary] = []

    if not ORDERS_ROOT.exists():
        return summaries

    for order_dir in ORDERS_ROOT.iterdir():
        if not order_dir.is_dir():
            continue

        client_csv = order_dir / "client_info.csv"
        if not client_csv.exists():
            continue

        try:
            with client_csv.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
        except Exception:
            continue

        if not row:
            continue

        quote_id = row.get("quote_id") or order_dir.name
        grower_name = row.get("grower_name") or ""
        program_type = row.get("program_type") or ""

        try:
            field_count = int(row.get("field_count") or 0)
        except ValueError:
            field_count = 0

        try:
            total_acres = float(row.get("total_acres") or 0)
        except ValueError:
            total_acres = 0.0

        try:
            total_annual_cost = float(row.get("total_annual_cost") or 0)
        except ValueError:
            total_annual_cost = 0.0

        created_at = datetime.fromtimestamp(order_dir.stat().st_mtime).isoformat()

        status_path = order_dir / STATUS_FILENAME
        if status_path.exists():
            status = status_path.read_text(encoding="utf-8").strip() or "Quoted"
        else:
            status = "Quoted"

        summaries.append(
            OrderSummary(
                quote_id=quote_id,
                grower_name=grower_name,
                program_type=program_type,
                field_count=field_count,
                total_acres=total_acres,
                total_annual_cost=total_annual_cost,
                created_at=created_at,
                status=status,
            )
        )

    # newest first
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries

@app.get("/orders/{quote_id}", response_model=OrderDetail)
def get_order_detail(quote_id: str):
    order_dir = ORDERS_ROOT / quote_id

    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

    # Read checkout_start.json
    checkout_path = order_dir / "checkout_start.json"
    if not checkout_path.exists():
        raise HTTPException(status_code=500, detail="Order missing checkout_start.json")

    with checkout_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    created_at = datetime.fromtimestamp(order_dir.stat().st_mtime).isoformat()

    exports = {
        "client_info_csv": str(order_dir / "client_info.csv"),
        "fields_csv": str(order_dir / "fields.csv"),
        "fields_geojson": str(order_dir / "fields.geojson"),
        "fields_geojson_dir": str(order_dir / "fields_geojson"),
    }

    @app.get("/orders/{quote_id}/status")
    def get_order_status(quote_id: str):
        order_dir = ORDERS_ROOT / quote_id
        if not order_dir.exists():
            raise HTTPException(status_code=404, detail="Order not found")

        status_path = order_dir / STATUS_FILENAME
        if status_path.exists():
            status = status_path.read_text(encoding="utf-8").strip() or "Quoted"
        else:
            status = "Quoted"

        return {"quote_id": quote_id, "status": status}

    @app.post("/orders/{quote_id}/status")
    def update_order_status(quote_id: str, payload: StatusUpdate):
        if payload.status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")

        order_dir = ORDERS_ROOT / quote_id
        if not order_dir.exists():
            raise HTTPException(status_code=404, detail="Order not found")

        status_path = order_dir / STATUS_FILENAME
        status_path.write_text(payload.status, encoding="utf-8")

        return {"quote_id": quote_id, "status": payload.status}

    status_path = order_dir / STATUS_FILENAME
    if status_path.exists():
        status = status_path.read_text(encoding="utf-8").strip() or "Quoted"
    else:
        status = "Quoted"

    return OrderDetail(
        quote_id=quote_id,
        grower=data.get("grower", {}),
        program_type=data.get("program_type"),
        fields=data.get("fields", []),
        created_at=created_at,
        exports=exports,
        status=status,
    )

# -------------------------------------------------------------------
# Checkout start endpoint
# -------------------------------------------------------------------

@app.post("/checkout/start", response_model=CheckoutStartResponse)
def checkout_start(payload: CheckoutStartRequest):
    if not payload.fields:
        raise HTTPException(status_code=400, detail="At least one field is required")

    # simple quote_id for now
    ts = int(time.time())
    short_name = (payload.grower.name or "grower").strip().replace(" ", "_")[:12]
    quote_id = f"q_{short_name}_{ts}"

    save_checkout_start(quote_id, payload)

    return CheckoutStartResponse(
        quote_id=quote_id,
        message="Checkout draft saved. Next step: start payment session.",
    )
