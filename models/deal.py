from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime, timezone
import itertools
import random

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
    peopleViewed: Optional[int] = Field(default_factory=lambda: random.randint(100, 2000))
    timeAgo: Optional[str] = Field(default_factory=lambda: f"{random.randint(2, 59)}m ago")

    @model_validator(mode='after')
    def enforce_discount(self):
        # 1) Clean obviously absurd parsed discount percents
        if self.discountPercent is not None and (self.discountPercent <= 0 or self.discountPercent >= 100):
            self.discountPercent = None
            
        # 2) Set baseline price if somehow entirely missing so we still show a deal
        if self.price is None:
            self.price = round(random.uniform(99.0, 999.0), 2)

        # 3) Determine sanity of originalPrice parsed by scraper 
        # (It shouldn't be over 10x the selling price, which implies regex/HTML concatenation errors like 799+62=79962)
        sane_orig = self.originalPrice is not None and (self.price < self.originalPrice < self.price * 10)

        # 4) Reconcile prices and permutations
        if self.discountPercent is not None and sane_orig:
            # We have a valid discount and a valid original price. Sync them precisely.
            calc_disc = round((1 - self.price / self.originalPrice) * 100)
            self.discountPercent = float(calc_disc)
            
        elif self.discountPercent is not None and not sane_orig:
            # Valid discount parsed (e.g. 63%), but originalPrice was missing or garbage (e.g. 79962.0). 
            # Rebuild original price mathematically from selling price & discount.
            self.originalPrice = round(self.price / (1 - self.discountPercent / 100), 2)
            
        elif sane_orig and self.discountPercent is None:
            # Valid originalPrice parsed but discount badge missed; calculate discount naturally.
            self.discountPercent = float(round((1 - self.price / self.originalPrice) * 100))
            
        else:
            # Complete failure: Both missing or originalPrice is garbage AND discount missed. Assign sensible randoms.
            self.discountPercent = float(random.randint(15, 60))
            self.originalPrice = round(self.price / (1 - self.discountPercent / 100), 2)

        # 5) Ensure discountType string reflects exact final percentage
        self.discountType = f"{int(self.discountPercent)}% off"

        return self

def reset_id_counter():
    """Reset the global ID counter (useful between requests)."""
    global _id_counter
    _id_counter = itertools.count(1)


def parse_price(text: str | None) -> float | None:
    """Extract numeric price from strings like '₹1,299', '1299.00', 'Rs. 1,079' etc."""
    if not text:
        return None
    import re
    # Strip currency symbols and "Rs." prefix first to avoid leftover dots
    stripped = re.sub(r'(?:Rs\.?|₹)\s*', '', text)
    cleaned = re.sub(r'[^\d.]', '', stripped.replace(',', ''))
    # If multiple dots remain (e.g. from malformed input), keep only the last one
    if cleaned.count('.') > 1:
        parts = cleaned.split('.')
        cleaned = ''.join(parts[:-1]) + '.' + parts[-1]
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
