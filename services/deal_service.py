"""
Deal service: fetches deals from all platforms, normalizes, filters, paginates.
"""
import concurrent.futures
from collections import Counter

import scrapers.amazon as amazon
import scrapers.flipkart as flipkart
import scrapers.myntra as myntra
from models.deal import DealItem, reset_id_counter


# ---------------------------------------------------------------------------
# Core fetcher
# ---------------------------------------------------------------------------

def _fetch_all_deals() -> list[DealItem]:
    """Fetch deals from all 3 platforms concurrently."""
    reset_id_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_amazon = executor.submit(amazon.get_deals)
        f_flipkart = executor.submit(flipkart.get_deals)
        f_myntra = executor.submit(myntra.get_deals)

        all_deals: list[DealItem] = []

        for fut in [f_amazon, f_flipkart, f_myntra]:
            try:
                result = fut.result(timeout=60)
                all_deals.extend(result)
            except Exception as e:
                print(f"Platform fetch error: {e}")

    # Re-assign sequential IDs after merging
    for idx, deal in enumerate(all_deals, start=1):
        deal.id = idx

    return all_deals


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _apply_filters(
    deals: list[DealItem],
    *,
    search: str | None = None,
    platforms: list[str] | None = None,
    categories: list[str] | None = None,
    brands: list[str] | None = None,
    min_discount: float | None = None,
    min_rating: float | None = None,
    no_cost_emi: bool | None = None,
) -> list[DealItem]:
    """Filter deals based on query parameters."""
    filtered = deals

    if search:
        q = search.lower()
        filtered = [d for d in filtered if q in d.title.lower() or (d.brand and q in d.brand.lower())]

    if platforms:
        plats = {p.strip().lower() for p in platforms}
        filtered = [d for d in filtered if d.platformName.lower() in plats]

    if categories:
        cats = {c.strip().lower() for c in categories}
        filtered = [d for d in filtered if d.category and d.category.lower() in cats]

    if brands:
        brnds = {b.strip().lower() for b in brands}
        filtered = [d for d in filtered if d.brand and d.brand.lower() in brnds]

    if min_discount is not None:
        filtered = [d for d in filtered if d.discountPercent and d.discountPercent >= min_discount]

    if min_rating is not None:
        filtered = [d for d in filtered if d.rating and d.rating >= min_rating]

    if no_cost_emi:
        filtered = [d for d in filtered if d.noCostEMI]

    return filtered


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _paginate(items: list, page: int, limit: int) -> tuple[list, int]:
    """Return (page_items, total_count)."""
    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    return items[start:end], total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_best_deals(
    *,
    search: str | None = None,
    platforms: str | None = None,       # comma-separated
    categories: str | None = None,      # comma-separated
    brands: str | None = None,          # comma-separated
    min_discount: float | None = None,
    min_rating: float | None = None,
    no_cost_emi: bool = False,
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Main endpoint logic: fetch → filter → paginate → return."""
    all_deals = _fetch_all_deals()

    # Parse comma-separated params
    plat_list = [p.strip() for p in platforms.split(",") if p.strip()] if platforms else None
    cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
    brand_list = [b.strip() for b in brands.split(",") if b.strip()] if brands else None

    filtered = _apply_filters(
        all_deals,
        search=search,
        platforms=plat_list,
        categories=cat_list,
        brands=brand_list,
        min_discount=min_discount,
        min_rating=min_rating,
        no_cost_emi=no_cost_emi if no_cost_emi else None,
    )

    page_items, total = _paginate(filtered, page, limit)

    return {
        "filters": {
            "platforms": ["Amazon", "Flipkart", "Myntra"],
            "minDiscount": [40, 50, 60, 75, 80],
            "minRating": [2, 3, 4],
            "category": [
                "Electronics", "Fashion", "Home & Kitchen", "Beauty", 
                "Sports", "Books", "Toys", "Footwear"
            ],
            "brand": [
                "Samsung", "Apple", "Nike", "Boat", "Lakme", 
                "Puma", "Philips", "Levi's"
            ],
            "noCostEMI": True,
        },
        "items": [item.model_dump(mode="json") for item in page_items],
        "total": total,
        "page": page,
        "limit": limit,
    }


def get_top_categories(top_n: int = 8) -> dict:
    """Aggregate and return the top N categories from current deals."""
    all_deals = _fetch_all_deals()
    counter = Counter(
        d.category for d in all_deals
        if d.category and d.category != "General"
    )
    # If we don't have enough non-General categories, include General
    if len(counter) < top_n:
        general_count = sum(1 for d in all_deals if d.category == "General")
        if general_count:
            counter["General"] = general_count

    top = [cat for cat, _ in counter.most_common(top_n)]
    return {"categories": top}


def get_top_brands(top_n: int = 8) -> dict:
    """Aggregate and return the top N brands from current deals."""
    all_deals = _fetch_all_deals()
    counter = Counter(
        d.brand for d in all_deals
        if d.brand
    )
    top = [brand for brand, _ in counter.most_common(top_n)]
    return {"brands": top}
