# TerraNet Client Onboarding MVP

This project contains the early MVP for the TerraNet Client Onboarding system.

It includes:
- A FastAPI backend for pricing and quote generation  
- A static HTML/JS frontend for drawing fields and previewing quotes  
- A simple flow for calculating TerraNet program pricing based on acres
- Backend structure for payment processing and 
Dev Team Instructions

1. Clone the Project

```bash
git clone https://github.com/emcgregor02/TerraNetClientOnboarding.git
cd TerraNetClientOnboarding

🐍 2. Create & Activate a Python Virtual Environment
macOS / Linux:
python3 -m venv venv
source venv/bin/activate

Windows (PowerShell):
python -m venv venv
.\venv\Scripts\activate

📦 3. Install Backend Dependencies
pip install fastapi uvicorn pydantic python-dotenv
Or, if a requirements file exists:
pip install -r requirements.txt

▶️ 4. Run the Backend Server
cd backend
uvicorn app.main:app --reload
You should see:
Uvicorn running on http://127.0.0.1:8000
Test the API:
Health check → http://127.0.0.1:8000/health
API docs → http://127.0.0.1:8000/docs

🌐 5. Open the Frontend

The frontend is a static HTML file. Open it directly in your browser:
TerraNetClientOnboarding/frontend/TCV_V1.html
Just double-click the file or open from within PyCharm.

🔄 6. How the System Works

User draws fields on the map
Frontend stores fields in localStorage
Whenever fields are added, deleted, or loaded, the frontend sends a POST request to: POST /quote/preview

Backend returns TerraNet pricing:
annual_total
sprayer_fee
total_due_first_year
per-field line items
Frontend updates the summary using backend data.

⚠️ 7. CORS Configuration

The backend allows requests from local development environments:

origins = [
    "http://localhost:63342",
    "http://127.0.0.1:63342"
]


If you open the frontend using a different localhost port, add it to origins.

🩺 8. Troubleshooting
❌ “Refused to connect”

Backend is not running. Start it with:

uvicorn app.main:app --reload

❌ “Blocked by CORS policy”

Add your frontend origin to origins in main.py.

❌ “ModuleNotFoundError”

Upgrade tooling:

pip install --upgrade pip setuptools wheel

❌ uvicorn[standard] fails on macOS

Use:

pip install uvicorn

🧱 9. Project Structure
TerraNetClientOnboarding/
│
├── backend/
│   └── app/
│       ├── main.py        # API routes + CORS setup
│       ├── models.py      # Quote + field schemas
│       └── pricing.py     # Pricing engine
│
├── frontend/
│   └── TCV_V1.html        # Client interface (draw fields, preview quotes)
│
└── venv/                  # Python virtual environment

10. MVP Roadmap 
Add program selection UI (REMOTE_ONLY vs SPRAYER_PLUS_REMOTE)
Add grower info form (name, email, farm, address)
Generate & export quote PDFs
Save quotes to local HQ server
Optional: deploy backend to HQ workstation

✔ Ready to Develop

Once the backend is running and the frontend is open in a browser:
Draw a field
Save it

Console will show:
“Sending quote payload”
“Quote received”
The system is fully wired for pricing previews.

Or if you’re ready, we can resume building tomorrow exactly where we left off.
