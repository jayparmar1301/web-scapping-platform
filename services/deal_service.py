from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
from models.db_models import DBDeal

def fetch_best_deals(
    db: Session,
    *,
    search: str | None = None,
    platforms: str | None = None,
    categories: str | None = None,
    brands: str | None = None,
    min_discount: float | None = None,
    min_rating: float | None = None,
    no_cost_emi: bool = False,
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Fetch best deals across platforms from database with filtering and pagination."""
    query = db.query(DBDeal)

    if search:
        q = f"%{search.lower()}%"
        query = query.filter(or_(
            func.lower(DBDeal.title).like(q),
            func.lower(DBDeal.brand).like(q)
        ))

    if platforms:
        plats = [p.strip().lower() for p in platforms.split(",") if p.strip()]
        if plats:
            query = query.filter(func.lower(DBDeal.platformName).in_(plats))

    if categories:
        cats = [c.strip().lower() for c in categories.split(",") if c.strip()]
        if cats:
            query = query.filter(func.lower(DBDeal.category).in_(cats))

    if brands:
        brnds = [b.strip().lower() for b in brands.split(",") if b.strip()]
        if brnds:
            query = query.filter(func.lower(DBDeal.brand).in_(brnds))

    if min_discount is not None:
        query = query.filter(DBDeal.discountPercent >= min_discount)

    if min_rating is not None:
        query = query.filter(DBDeal.rating >= min_rating)

    if no_cost_emi:
        query = query.filter(DBDeal.noCostEMI == True)

    total = query.count()
    
    # Sort deals by discount percent (best deals first)
    query = query.order_by(desc(DBDeal.discountPercent), DBDeal.id)
    
    offset = (page - 1) * limit
    page_items = query.offset(offset).limit(limit).all()

    items_json = []
    for item in page_items:
        items_json.append({
            "id": item.id,
            "title": item.title,
            "brand": item.brand,
            "discountType": item.discountType,
            "discountPercent": item.discountPercent,
            "price": item.price,
            "originalPrice": item.originalPrice,
            "category": item.category,
            "images": item.images,
            "platformName": item.platformName,
            "platformLink": item.platformLink,
            "rating": item.rating,
            "ratingCount": item.ratingCount,
            "noCostEMI": item.noCostEMI,
            "affiliateUrl": item.affiliateUrl,
            "peopleViewed": item.peopleViewed,
            "timeAgo": item.timeAgo,
            "createdAt": item.createdAt.isoformat() if item.createdAt else None,
            "updatedAt": item.updatedAt.isoformat() if item.updatedAt else None
        })

    # Fetch dynamic filter metadata from the DB
    distinct_platforms = [p[0] for p in db.query(DBDeal.platformName).distinct().filter(DBDeal.platformName != None).all()]
    
    distinct_categories = [c[0] for c in db.query(DBDeal.category).distinct().filter(DBDeal.category != None).all()]
    if "General" in distinct_categories:
        # Move 'General' to the end or keep it native, UI preference
        distinct_categories.remove("General")
        distinct_categories.append("General")
    
    # Fetch top 15 brands by deal volume so the filter checklist is robust but not overwhelmingly bloated
    top_brands_query = db.query(DBDeal.brand, func.count(DBDeal.id).label('total')) \
                         .filter(DBDeal.brand != None) \
                         .group_by(DBDeal.brand) \
                         .order_by(desc('total')) \
                         .limit(15).all()
    distinct_brands = [b[0] for b in top_brands_query]

    return {
        "filters": {
            "platforms": distinct_platforms,
            "minDiscount": [40, 50, 60, 75, 80],
            "minRating": [2, 3, 4],
            "category": distinct_categories,
            "brand": distinct_brands,
            "noCostEMI": True,
        },
        "items": items_json,
        "total": total,
        "page": page,
        "limit": limit,
    }

def get_top_categories(db: Session, top_n: int = 8) -> dict:
    """Aggregate and return the top N categories from database."""
    results = db.query(DBDeal.category, func.count(DBDeal.id).label('total')) \
                .filter(DBDeal.category != None) \
                .filter(DBDeal.category != 'General') \
                .group_by(DBDeal.category) \
                .order_by(desc('total')) \
                .limit(top_n).all()
    
    cats = [cat for cat, _ in results]
    
    if len(cats) < top_n:
        gen_count = db.query(func.count(DBDeal.id)).filter(DBDeal.category == 'General').scalar()
        if gen_count and gen_count > 0:
            cats.append('General')
            
    return {"categories": cats}

def get_top_brands(db: Session, top_n: int = 8) -> dict:
    """Aggregate and return the top N brands from database."""
    results = db.query(DBDeal.brand, func.count(DBDeal.id).label('total')) \
                .filter(DBDeal.brand != None) \
                .group_by(DBDeal.brand) \
                .order_by(desc('total')) \
                .limit(top_n).all()
    
    brands = [brand for brand, _ in results]
    return {"brands": brands}
