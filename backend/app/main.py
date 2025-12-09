from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, quotes, orders

app = FastAPI(title="TerraNet Client Onboarding API")

origins = [
    "http://localhost:63342",
    "http://127.0.0.1:63342",
    "http://localhost",
    "http://127.0.0.1",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach routers
app.include_router(health.router)
app.include_router(quotes.router)
app.include_router(orders.router)
