from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import itertools

_id_counter = itertools.count(1)


class DealItem(BaseModel):
    id: int = Field(default_factory=lambda: next(_id_counter))
    title: str
    brand: Optional[str] = None
    discountType: Optional[str] = None          # e.g. "50% minimum", "Flat 40% off"
    discountPercent: Optional[float] = None      # e.g. 57
    price: Optional[float] = None                # selling price in ₹
    originalPrice: Optional[float] = None        # MRP in ₹
    category: Optional[str] = "General"
    images: List[str] = Field(default_factory=list)
    platformName: str                            # "Amazon" | "Flipkart" | "Myntra"
    platformLink: Optional[str] = None           # product page URL
    rating: Optional[float] = None
    ratingCount: Optional[int] = None
    noCostEMI: bool = False
    affiliateUrl: Optional[str] = "#"
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def reset_id_counter():
    """Reset the global ID counter (useful between requests)."""
    global _id_counter
    _id_counter = itertools.count(1)


def parse_price(text: str | None) -> float | None:
    """Extract numeric price from strings like '₹1,299', '1299.00', etc."""
    if not text:
        return None
    import re
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def compute_discount(price: float | None, original: float | None) -> float | None:
    """Compute discount percentage from price and original price."""
    if price and original and original > price > 0:
        return round((1 - price / original) * 100)
    return None


def extract_brand(title: str) -> str | None:
    """Best-effort brand extraction from product title.
    Typically the first word/phrase before a space or product descriptor.
    """
    if not title:
        return None
    # Common pattern: "BrandName ProductDescription..."
    parts = title.strip().split()
    if parts:
        # Take first word as brand; if it's very short (1-2 chars), take first 2 words
        brand = parts[0]
        if len(brand) <= 2 and len(parts) > 1:
            brand = f"{parts[0]} {parts[1]}"
        return brand
    return None
