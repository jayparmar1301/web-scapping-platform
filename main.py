from fastapi import FastAPI, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional
from services.deal_service import fetch_best_deals, get_top_categories, get_top_brands
from core.database import get_db

app = FastAPI(title="Deal Scraper API", version="2.0.0")


@app.get("/deals/best-deals")
def best_deals(
    search: Optional[str] = Query(None, description="Product name or brand to search"),
    platforms: Optional[str] = Query(None, description="Comma-separated: Amazon,Flipkart,Myntra"),
    categories: Optional[str] = Query(None, description="Comma-separated: Electronics,Fashion"),
    brands: Optional[str] = Query(None, description="Comma-separated: Samsung,Nike"),
    minDiscount: Optional[float] = Query(None, description="Minimum discount percentage"),
    minRating: Optional[float] = Query(None, description="Minimum star rating"),
    noCostEMI: Optional[str] = Query(None, description="'true' to filter for No Cost EMI only"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """Fetch best deals across platforms with filtering and pagination."""
    emi_flag = noCostEMI and noCostEMI.lower() == "true"

    return fetch_best_deals(
        db,
        search=search,
        platforms=platforms,
        categories=categories,
        brands=brands,
        min_discount=minDiscount,
        min_rating=minRating,
        no_cost_emi=emi_flag,
        page=page,
        limit=limit,
    )


@app.get("/deals/top-categories")
def top_categories(db: Session = Depends(get_db)):
    """Return the top 8 categories from current deals."""
    return get_top_categories(db)


@app.get("/deals/top-brands")
def top_brands(db: Session = Depends(get_db)):
    """Return the top 8 brands from current deals."""
    return get_top_brands(db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
