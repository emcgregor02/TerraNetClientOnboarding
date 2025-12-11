from __future__ import annotations

import csv
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import shutil

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

router = APIRouter()

# -------------------------------------------------------------------
# Constants & paths
# -------------------------------------------------------------------

# This file is backend/app/routers/orders.py
# parent = routers, parent.parent = app, parent.parent.parent = backend
ORDERS_ROOT = Path(__file__).resolve().parent.parent.parent / "orders"
STATUS_FILENAME = "status.txt"

ALLOWED_STATUSES = [
    "Quoted",
    "Awaiting Payment",
    "Paid",
    "Onboarding Started",
    "Completed",
]

VALID_EXPORT_FILES = {
    "client_info.csv",
    "fields.csv",
    "fields.geojson",
    "onboarding_packet.zip",
}

# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------


class GrowerInfo(BaseModel):
    name: str
    email: EmailStr
    farmName: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postalCode: Optional[str] = None
    country: Optional[str] = None



class CheckoutStartRequest(BaseModel):
    grower: GrowerInfo
    program_type: str  # "REMOTE_ONLY" / "SPRAYER_PLUS_REMOTE" etc.
    fields: List[dict]


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
    created_at: str
    status: str


class OrderDetail(BaseModel):
    quote_id: str
    grower: GrowerInfo
    program_type: str
    fields: List[dict]
    created_at: str
    exports: dict
    status: str


class StatusUpdate(BaseModel):
    status: str


# -------------------------------------------------------------------
# Helpers: saving checkout + exports
# -------------------------------------------------------------------


def write_client_csv(order_dir: Path, quote_id: str, payload: CheckoutStartRequest) -> None:
    csv_path = order_dir / "client_info.csv"
    g = payload.grower
    fields = payload.fields or []

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
        "address1",
        "address2",
        "city",
        "state",
        "postal_code",
        "country",
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
            "address1": g.address1 or "",
            "address2": g.address2 or "",
            "city": g.city or "",
            "state": g.state or "",
            "postal_code": g.postalCode or "",
            "country": g.country or "",
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


def save_checkout_start(quote_id: str, payload: CheckoutStartRequest) -> None:
    ORDERS_ROOT.mkdir(exist_ok=True)
    order_dir = ORDERS_ROOT / quote_id
    order_dir.mkdir(exist_ok=True)

    # 1) Raw JSON snapshot
    out_path = order_dir / "checkout_start.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload.dict(), f, indent=2)

    # 2–4) Exports
    write_client_csv(order_dir, quote_id, payload)
    write_fields_csv(order_dir, quote_id, payload)
    write_fields_geojson(order_dir, payload)

    # 5) Initialize status if not present
    status_path = order_dir / STATUS_FILENAME
    if not status_path.exists():
        status_path.write_text("Quoted", encoding="utf-8")


# -------------------------------------------------------------------
# Helpers: order listing & detail
# -------------------------------------------------------------------


def read_status(order_dir: Path) -> str:
    status_path = order_dir / STATUS_FILENAME
    if status_path.exists():
        text = status_path.read_text(encoding="utf-8").strip()
        return text or "Quoted"
    return "Quoted"


def write_status(order_dir: Path, status: str) -> None:
    status_path = order_dir / STATUS_FILENAME
    status_path.write_text(status, encoding="utf-8")


def build_order_summaries() -> List[OrderSummary]:
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
        status = read_status(order_dir)

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

    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


def build_order_detail(quote_id: str) -> OrderDetail:
    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

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
        "onboarding_zip": str(order_dir / "onboarding_packet.zip"),
    }

    status = read_status(order_dir)

    return OrderDetail(
        quote_id=quote_id,
        grower=data.get("grower", {}),
        program_type=data.get("program_type", ""),
        fields=data.get("fields", []),
        created_at=created_at,
        exports=exports,
        status=status,
    )


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@router.post("/checkout/start", response_model=CheckoutStartResponse)
def checkout_start(payload: CheckoutStartRequest):
    if not payload.fields:
        raise HTTPException(status_code=400, detail="At least one field is required")

    ts = int(time.time())
    short_name = (payload.grower.name or "grower").strip().replace(" ", "_")[:12]
    quote_id = f"q_{short_name}_{ts}"

    save_checkout_start(quote_id, payload)

    return CheckoutStartResponse(
        quote_id=quote_id,
        message="Checkout draft saved. Next step: start payment session.",
    )


@router.get("/orders", response_model=List[OrderSummary])
def list_orders():
    return build_order_summaries()


@router.get("/orders/{quote_id}", response_model=OrderDetail)
def get_order_detail(quote_id: str):
    return build_order_detail(quote_id)

@router.delete("/orders/{quote_id}")
def delete_order(quote_id: str):
    """
    Permanently delete an order folder and all its exports.
    """
    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        shutil.rmtree(order_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete order: {e}")

    return {"quote_id": quote_id, "deleted": True}


@router.get("/orders/{quote_id}/status")
def get_order_status(quote_id: str):
    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists():
        raise HTTPException(status_code=404, detail="Order not found")
    return {"quote_id": quote_id, "status": read_status(order_dir)}


@router.post("/orders/{quote_id}/status")
def update_order_status(quote_id: str, payload: StatusUpdate):
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists():
        raise HTTPException(status_code=404, detail="Order not found")

    write_status(order_dir, payload.status)
    return {"quote_id": quote_id, "status": payload.status}


@router.get("/orders/{quote_id}/download/{filename}")
def download_export(quote_id: str, filename: str):
    if filename not in VALID_EXPORT_FILES:
        raise HTTPException(status_code=400, detail="Invalid export filename")

    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

    file_path = order_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/orders/{quote_id}/onboarding")
def generate_onboarding_packet(quote_id: str):
    """
    Build an onboarding packet ZIP for this order.
    """
    order_dir = ORDERS_ROOT / quote_id
    if not order_dir.exists() or not order_dir.is_dir():
        raise HTTPException(status_code=404, detail="Order not found")

    checkout_path = order_dir / "checkout_start.json"
    if not checkout_path.exists():
        raise HTTPException(status_code=500, detail="Order missing checkout_start.json")

    # Load base data
    try:
        with checkout_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read checkout_start.json")

    grower = data.get("grower", {})
    program_type = data.get("program_type", "")
    fields = data.get("fields", [])

    total_acres = 0.0
    total_annual = 0.0
    for fld in fields:
        try:
            total_acres += float(fld.get("acres", 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            total_annual += float(fld.get("annualCost", 0) or 0)
        except (TypeError, ValueError):
            pass

    # Simple text summary file
    summary_lines = [
        f"Quote ID: {quote_id}",
        f"Grower: {grower.get('name','')} ({grower.get('email','')})",
        f"Farm: {grower.get('farmName','')}",
        f"Program: {program_type}",
        f"Fields: {len(fields)}",
        f"Total Acres: {round(total_acres, 2)}",
        f"Total Annual Cost: {round(total_annual, 2)}",
        "",
        "Notes:",
        grower.get("notes", "") or "",
        "",
        "Included files:",
        "- checkout_start.json",
        "- client_info.csv",
        "- fields.csv",
        "- fields.geojson",
        "- fields_geojson/*.geojson",
        "- summary.txt",
    ]

    summary_path = order_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    # Create ZIP
    zip_path = order_dir / "onboarding_packet.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Core files
        for fname in ["checkout_start.json", "client_info.csv", "fields.csv", "fields.geojson", "summary.txt"]:
            fp = order_dir / fname
            if fp.exists():
                zf.write(fp, arcname=fname)

        # Per-field GeoJSONs
        fg_dir = order_dir / "fields_geojson"
        if fg_dir.exists() and fg_dir.is_dir():
            for child in fg_dir.iterdir():
                if child.is_file():
                    zf.write(child, arcname=f"fields_geojson/{child.name}")

    return {
        "quote_id": quote_id,
        "packet": "onboarding_packet.zip",
    }
