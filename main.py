import os
from datetime import datetime
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from xml.etree import ElementTree as ET

from database import create_document, get_documents, db

app = FastAPI(title="BusinessInsight API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    company: str = Field(..., description="Company name to search for")
    ticker: Optional[str] = Field(None, description="Optional stock ticker symbol")
    locale: Optional[str] = Field(None, description="Locale hint, e.g., en-US")


class InsightResponse(BaseModel):
    company: str
    summary: str
    financials: Dict[str, Any]
    market_trends: List[str]
    competitors: List[Dict[str, Any]]
    pricing: Dict[str, Any]
    projections: Dict[str, Any]
    prices: List[Dict[str, Any]]
    last_refreshed: datetime


@app.get("/")
def read_root():
    return {"product": "BusinessInsight API", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "Unknown"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# -------- External data fetch helpers (no API keys required) --------

def fetch_wikipedia_summary(company: str) -> str:
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(company)}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("extract", "")
    except Exception:
        pass
    return ""


def fetch_google_news_rss(company: str, locale: Optional[str] = None, limit: int = 8) -> List[Dict[str, Any]]:
    # Google News RSS endpoint
    q = requests.utils.quote(company)
    hl = (locale or "en-US")
    rss_url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl=US&ceid=US:en"
    items: List[Dict[str, Any]] = []
    try:
        resp = requests.get(rss_url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        # RSS structure: rss > channel > item
        for item in root.findall(".//item")[:limit]:
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            source_el = item.find("source")
            description_el = item.find("description")
            items.append({
                "company": company,
                "title": title_el.text if title_el is not None else "",
                "url": link_el.text if link_el is not None else "",
                "source": source_el.text if source_el is not None else "Google News",
                "published_at": pub_el.text if pub_el is not None else "",
                "summary": description_el.text if description_el is not None else None,
                "tags": [],
            })
    except Exception:
        # Fail silently; return empty news list
        return []
    return items


def fetch_stooq_prices(ticker: Optional[str], limit: int = 60) -> List[Dict[str, Any]]:
    """
    Fetch daily prices using free Stooq CSV endpoint when ticker is provided.
    If ticker is absent or request fails, return an empty list.
    """
    if not ticker:
        return []
    try:
        # Stooq expects lowercase tickers. Example: aapl for Apple
        s = ticker.lower()
        url = f"https://stooq.com/q/d/l/?s={s}&i=d"
        r = requests.get(url, timeout=10)
        if r.status_code != 200 or not r.text or r.text.startswith("<!DOCTYPE"):
            return []
        lines = r.text.strip().splitlines()
        # First line is header: Date,Open,High,Low,Close,Volume
        rows = []
        for row in lines[1:][-limit:]:
            try:
                date, open_, high, low, close, volume = row.split(",")
                rows.append({
                    "date": date,
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": int(float(volume)),
                })
            except Exception:
                continue
        return rows
    except Exception:
        return []


# -------- API routes --------

@app.post("/api/search", response_model=InsightResponse)
def run_search(payload: SearchRequest):
    company = payload.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company is required")

    # Fetch external data
    summary = fetch_wikipedia_summary(company)
    news_items = fetch_google_news_rss(company, locale=payload.locale)
    prices = fetch_stooq_prices(payload.ticker)

    # Very light placeholder analytics
    financials = {
        "revenue": None,
        "profit_margin": None,
        "valuation": None,
        "note": "Financial metrics require premium data sources. Showing available open data only.",
    }

    market_trends = [
        f"Media coverage: {len(news_items)} recent articles discovered",
        "Monitoring public sources for mentions and sentiment",
    ]

    competitors: List[Dict[str, Any]] = []  # Placeholder; could be populated via curated lists

    pricing: Dict[str, Any] = {
        "model": "Unknown",
        "notes": "Pricing analysis requires domain-specific sources."
    }

    projections: Dict[str, Any] = {
        "outlook": "Neutral",
        "assumptions": ["Based on recent public signals only"],
    }

    # Persist snapshot and news to database (best-effort)
    try:
        snapshot = {
            "company": company,
            "summary": summary or f"No summary available for {company}.",
            "financials": financials,
            "market_trends": market_trends,
            "competitors": competitors,
            "pricing": pricing,
            "projections": projections,
            "last_refreshed": datetime.utcnow(),
        }
        create_document("insight", snapshot)
        for n in news_items:
            try:
                create_document("news", n)
            except Exception:
                continue
        # Also store the query itself
        try:
            create_document("companyquery", {"company": company, "locale": payload.locale})
        except Exception:
            pass
    except Exception:
        # Database could be unavailable; continue serving the response
        pass

    return InsightResponse(
        company=company,
        summary=summary or f"No summary available for {company}.",
        financials=financials,
        market_trends=market_trends,
        competitors=competitors,
        pricing=pricing,
        projections=projections,
        prices=prices,
        last_refreshed=datetime.utcnow(),
    )


@app.get("/api/insights", response_model=List[InsightResponse])
def get_insights(company: str = Query(..., description="Company name to filter by")):
    # Pull latest 1-3 insight docs for this company if present
    try:
        docs = get_documents("insight", {"company": company}, limit=3)
    except Exception:
        docs = []
    results: List[InsightResponse] = []
    for d in docs:
        results.append(InsightResponse(
            company=d.get("company", company),
            summary=d.get("summary", ""),
            financials=d.get("financials", {}),
            market_trends=d.get("market_trends", []),
            competitors=d.get("competitors", []),
            pricing=d.get("pricing", {}),
            projections=d.get("projections", {}),
            prices=[],  # historical prices are fetched live in /api/search
            last_refreshed=d.get("last_refreshed", datetime.utcnow()),
        ))
    return results


@app.get("/api/news")
def get_news(company: str = Query(..., description="Company name to filter by"), limit: int = 10):
    # Try database first, otherwise fetch live
    try:
        docs = get_documents("news", {"company": company}, limit=limit)
        if docs:
            for d in docs:
                if isinstance(d.get("published_at"), datetime):
                    d["published_at"] = d["published_at"].isoformat()
            return docs
    except Exception:
        pass
    # Fallback to live RSS
    return fetch_google_news_rss(company, limit=limit)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
