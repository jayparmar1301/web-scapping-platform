import sys
import os
import concurrent.futures

# Make sure we can import from the root project
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal, engine, Base
from models.db_models import DBDeal
import scrapers.amazon as amazon
import scrapers.flipkart as flipkart
import scrapers.myntra as myntra

# Initialize DB tables if they don't exist
Base.metadata.create_all(bind=engine)

def scrape_and_store():
    print("Starting background deal scraper...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_amazon = executor.submit(amazon.get_deals)
        f_flipkart = executor.submit(flipkart.get_deals)
        f_myntra = executor.submit(myntra.get_deals)

        all_deals = []

        platform_names = ["Amazon", "Flipkart", "Myntra"]
        futures = [f_amazon, f_flipkart, f_myntra]

        for name, fut in zip(platform_names, futures):
            try:
                result = fut.result(timeout=300)
                print(f"[{name}] Returned {len(result)} deals")
                all_deals.extend(result)
            except Exception as e:
                print(f"[{name}] Fetch error: {e}")

    # --- Deduplicate scraped deals in-memory (title + platform) ---
    seen_keys: set[str] = set()
    unique_deals = []
    for deal in all_deals:
        key = _make_dedup_key(deal.title, deal.platformName)
        if key and key not in seen_keys:
            seen_keys.add(key)
            unique_deals.append(deal)

    dupes_in_scrape = len(all_deals) - len(unique_deals)
    print(f"Scraping complete. Found {len(all_deals)} total deals ({dupes_in_scrape} duplicates removed in-memory).")

    if not unique_deals:
        print("No deals found. Aborting database update to prevent wiping out existing data.")
        return

    db = SessionLocal()
    try:
        # Load existing records keyed by (title, platform) for comparison
        existing_rows = db.query(DBDeal).all()
        existing_map: dict[str, DBDeal] = {}
        for row in existing_rows:
            key = _make_dedup_key(row.title, row.platformName)
            if key:
                existing_map[key] = row

        inserted = 0
        updated = 0
        skipped = 0

        for deal in unique_deals:
            key = _make_dedup_key(deal.title, deal.platformName)
            existing = existing_map.get(key)

            if existing is None:
                # New deal — insert
                db.add(DBDeal(
                    title=deal.title,
                    brand=deal.brand,
                    discountType=deal.discountType,
                    discountPercent=deal.discountPercent,
                    price=deal.price,
                    originalPrice=deal.originalPrice,
                    category=deal.category,
                    images=deal.images,
                    platformName=deal.platformName,
                    platformLink=deal.platformLink,
                    rating=deal.rating,
                    ratingCount=deal.ratingCount,
                    noCostEMI=deal.noCostEMI,
                    affiliateUrl=deal.affiliateUrl,
                    peopleViewed=deal.peopleViewed,
                    timeAgo=deal.timeAgo
                ))
                inserted += 1
            elif _has_deal_changed(existing, deal):
                # Same product but price/discount changed — update
                existing.price = deal.price
                existing.originalPrice = deal.originalPrice
                existing.discountPercent = deal.discountPercent
                existing.discountType = deal.discountType
                existing.rating = deal.rating
                existing.ratingCount = deal.ratingCount
                existing.images = deal.images
                existing.platformLink = deal.platformLink
                existing.affiliateUrl = deal.affiliateUrl
                existing.noCostEMI = deal.noCostEMI
                existing.peopleViewed = deal.peopleViewed
                existing.timeAgo = deal.timeAgo
                updated += 1
            else:
                # Identical — skip
                skipped += 1

        db.commit()
        print(f"DB sync complete: {inserted} inserted, {updated} updated, {skipped} unchanged.")
    except Exception as e:
        db.rollback()
        print(f"Database error: {e}")
    finally:
        db.close()


def _has_deal_changed(existing: DBDeal, new_deal) -> bool:
    """Check if price or discount fields differ between DB record and scraped deal."""
    if _float_changed(existing.price, new_deal.price):
        return True
    if _float_changed(existing.originalPrice, new_deal.originalPrice):
        return True
    if _float_changed(existing.discountPercent, new_deal.discountPercent):
        return True
    if (existing.discountType or "") != (new_deal.discountType or ""):
        return True
    return False


def _float_changed(old_val, new_val, tolerance=0.01) -> bool:
    """Compare two float values with tolerance for rounding differences."""
    if old_val is None and new_val is None:
        return False
    if old_val is None or new_val is None:
        return True
    return abs(float(old_val) - float(new_val)) > tolerance


def _make_dedup_key(title: str | None, platform: str | None) -> str | None:
    """Create a normalized dedup key from title + platform."""
    if not title:
        return None
    normalized_title = title.strip().lower()
    normalized_platform = (platform or "").strip().lower()
    return f"{normalized_platform}::{normalized_title}"

if __name__ == "__main__":
    scrape_and_store()
