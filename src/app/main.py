from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Enterprise Knowledge AI Agent")

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
async def dashboard_data(
    fiscal_year: str = Query("FY2025", pattern=r"^FY20\d{2}$"),
    source: str = Query("apple-public-corporate-corpus"),
):
    """Mock dashboard contract. Replace this body with service calls later."""
    return {
        "filters": {"fiscalYear": fiscal_year, "source": source},
        "kpis": [
            {"id": "net-sales", "label": "Net Sales (FY2025)", "value": "$416.161B", "detail": "vs. $391.035B in FY2024", "change": "+6.4%", "tone": "positive", "icon": "chart"},
            {"id": "iphone", "label": "iPhone Sales (FY2025)", "value": "$209.586B", "detail": "of total net sales", "change": "50.4%", "tone": "neutral", "icon": "phone"},
            {"id": "services", "label": "Services Sales (FY2025)", "value": "$109.158B", "detail": "of total net sales", "change": "26.2%", "tone": "neutral", "icon": "layers"},
            {"id": "employees", "label": "Full-time Equivalent Employees", "value": "166,000", "detail": "vs. 164,000 in FY2024", "change": "As of FY2025", "tone": "neutral", "icon": "users"},
        ],
        "salesTrend": [
            {"year": "FY2021", "value": 365.817}, {"year": "FY2022", "value": 394.328},
            {"year": "FY2023", "value": 383.285}, {"year": "FY2024", "value": 391.035},
            {"year": "FY2025", "value": 416.161},
        ],
        "products": [
            {"name": "iPhone", "value": 209.586, "share": 50.4, "color": "#2878f4"},
            {"name": "Mac", "value": 33.708, "share": 8.1, "color": "#9b62df"},
            {"name": "iPad", "value": 28.023, "share": 6.7, "color": "#6fc088"},
            {"name": "Wearables, Home & Accessories", "value": 35.686, "share": 8.6, "color": "#ff9638"},
            {"name": "Services", "value": 109.158, "share": 26.2, "color": "#f33f5c"},
        ],
        "regions": [
            {"name": "Americas", "value": 178.353, "share": 42.9, "color": "#3470be"},
            {"name": "Europe", "value": 111.032, "share": 26.7, "color": "#65a9f4"},
            {"name": "Greater China", "value": 64.377, "share": 15.5, "color": "#8c5de0"},
            {"name": "Rest of Asia Pacific", "value": 33.696, "share": 8.1, "color": "#7ab57e"},
            {"name": "Japan", "value": 28.703, "share": 6.9, "color": "#f7a344"},
        ],
        "insights": [
            {"title": "Services grew faster than total sales", "body": "Services revenue increased 13.9% year over year, outpacing total net sales growth of 6.4%, indicating continued diversification and strong growth in the Services business.", "source": "FY2025 10-K"},
            {"title": "Greater China sales declined year over year", "body": "Greater China net sales decreased 2.3% compared to FY2024, primarily due to a challenging macroeconomic environment in the region.", "source": "FY2025 10-K"},
            {"title": "Wearables, Home and Accessories declined year over year", "body": "Wearables, Home and Accessories net sales decreased 6.7% compared to FY2024, reflecting lower sales of Apple Watch, AirPods and related products.", "source": "FY2025 10-K"},
            {"title": "Strong installed base supports long-term opportunities", "body": "With a large and growing installed base across devices, Apple is well positioned to expand Services and drive long-term value.", "source": "FY2025 10-K"},
        ],
        "coverage": {"documents": 30, "chunks": 12846, "categories": [
            {"name": "Finance", "count": 8, "icon": "file", "tone": "blue"},
            {"name": "Compliance", "count": 5, "icon": "shield", "tone": "green"},
            {"name": "Procurement", "count": 6, "icon": "clipboard", "tone": "purple"},
            {"name": "Supply Chain", "count": 5, "icon": "network", "tone": "orange"},
            {"name": "Environment", "count": 6, "icon": "leaf", "tone": "green"}
        ]},
        "recentSources": [
            {"title": "Apple Inc. Form 10-K (FY2025)", "category": "Finance", "date": "Jan 2025"},
            {"title": "Apple Environmental Progress Report 2025", "category": "Environment", "date": "Apr 2025"},
            {"title": "Supplier Code of Conduct and Supplier Responsibility Standards", "category": "Supply Chain", "date": "Jan 2025"},
            {"title": "Business Conduct Policy (2026)", "category": "Compliance", "date": "Jan 2026"},
            {"title": "Apple Purchase Order Terms", "category": "Procurement", "date": "2024"},
        ],
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    # placeholder: save file and enqueue processing
    content = await file.read()
    # TODO: route to DocumentProcessor
    return JSONResponse({"filename": file.filename, "size": len(content)})
