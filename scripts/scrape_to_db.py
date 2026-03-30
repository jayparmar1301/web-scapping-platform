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

        for fut in [f_amazon, f_flipkart, f_myntra]:
            try:
                result = fut.result(timeout=300)
                all_deals.extend(result)
            except Exception as e:
                print(f"Platform fetch error: {e}")

    print(f"Scraping complete. Found {len(all_deals)} total deals.")

    if not all_deals:
        print("No deals found. Aborting database update to prevent wiping out existing data.")
        return

    db = SessionLocal()
    try:
        # We process this transaction atomically. 
        # Delete old deals and insert new ones. The API will never see an empty state.
        db.query(DBDeal).delete()
        
        db_records = []
        for deal in all_deals:
            db_records.append(DBDeal(
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
        
        db.bulk_save_objects(db_records)
        db.commit()
        print(f"Successfully committed {len(db_records)} deals to the database.")
    except Exception as e:
        db.rollback()
        print(f"Database error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    scrape_and_store()
