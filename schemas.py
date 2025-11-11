"""
Database Schemas for BusinessInsight

Each Pydantic model represents a MongoDB collection.
The collection name is the lowercase of the class name.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class Companyquery(BaseModel):
    """
    Stores user search queries so we can analyze usage and cache results.
    Collection: "companyquery"
    """
    company: str = Field(..., description="Company name or ticker")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    locale: Optional[str] = Field(None, description="Locale or region context")

class Insight(BaseModel):
    """
    Stores consolidated business insight snapshot for a company.
    Collection: "insight"
    """
    company: str = Field(..., description="Company name")
    summary: str = Field(..., description="High-level AI-style summary")
    financials: dict = Field(default_factory=dict, description="Revenue, profit, valuation, etc.")
    market_trends: List[str] = Field(default_factory=list, description="Bulleted trend items")
    competitors: List[dict] = Field(default_factory=list, description="List of competitors with key stats")
    pricing: dict = Field(default_factory=dict, description="Pricing/business model overview")
    projections: dict = Field(default_factory=dict, description="Simple forward-looking projections")
    last_refreshed: datetime = Field(default_factory=datetime.utcnow, description="Last refresh timestamp")

class News(BaseModel):
    """
    Stores normalized news items per company for quick retrieval.
    Collection: "news"
    """
    company: str = Field(..., description="Company this news relates to")
    title: str
    url: str
    source: str
    published_at: datetime
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
