"""
Myntra scraper using their internal API.
Myntra is a React SPA that doesn't render product HTML server-side,
so we must use their internal API endpoints directly.
"""
from core.http_client import get_session
from models.deal import DealItem, parse_price, compute_discount, extract_brand
import urllib.parse
import json
import re


def _get_myntra_session():
    """Get a session with Myntra-appropriate mobile headers."""
    session = get_session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-IN,en;q=0.5",
        "Referer": "https://www.myntra.com/",
        "X-Requested-With": "browser",
    })
    return session


def search_product(query: str):
    """Search Myntra via their internal search API (unchanged)."""
    session = _get_myntra_session()
    search_query = query.replace(" ", "-").lower()
    api_url = f"https://www.myntra.com/gateway/v2/search/{urllib.parse.quote(search_query)}"

    params = {
        "p": "1",
        "rows": "10",
        "o": "0",
        "platefrom": "desktop",
        "q": search_query,
    }

    try:
        resp = session.get(api_url, params=params, timeout=20)

        if resp.status_code == 200:
            try:
                data = resp.json()
                products = data.get("products", [])
                results = []
                for p in products[:10]:
                    results.append({
                        "platform": "Myntra",
                        "title": f"{p.get('brand', '')} {p.get('product', '')}".strip(),
                        "price": f"₹{p.get('price', p.get('mrp', 'N/A'))}",
                        "link": f"https://www.myntra.com/{p.get('landingPageUrl', '')}",
                        "image": p.get("searchImage") or (
                            p.get("images", [{}])[0].get("src") if p.get("images") else None
                        )
                    })
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass

        return _search_myntra_html(query)

    except Exception as e:
        print(f"Myntra API search error: {e}")
        return _search_myntra_html(query)


def _search_myntra_html(query: str):
    """Fallback: Search Myntra via HTML and extract embedded JSON."""
    session = get_session()
    search_query = query.replace(" ", "-").lower()
    url = f"https://www.myntra.com/{urllib.parse.quote(search_query)}"

    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        results = []

        patterns = [
            r'window\.__myx\s*=\s*(\{.+?\});\s*</',
            r'"searchData"\s*:\s*(\{.+?\})\s*[,}]',
        ]

        for pattern in patterns:
            match = re.search(pattern, resp.text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    products = data.get("searchData", data).get("results", {}).get("products", [])
                    for p in products[:10]:
                        results.append({
                            "platform": "Myntra",
                            "title": f"{p.get('brand', '')} {p.get('product', p.get('productName', ''))}".strip(),
                            "price": f"₹{p.get('price', p.get('mrp', 'N/A'))}",
                            "link": f"https://www.myntra.com/{p.get('landingPageUrl', '')}",
                            "image": p.get("searchImage")
                        })
                    if results:
                        return results
                except (json.JSONDecodeError, KeyError):
                    continue

        return results
    except Exception as e:
        print(f"Myntra HTML search error: {e}")
        return []


def extract_product_title(url: str):
    """Extract a product title from a Myntra URL."""
    session = get_session()
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'lxml')

        title_elem = soup.select_one("h1.pdp-name, h1.pdp-title, .pdp-name")
        if title_elem:
            return title_elem.get_text(strip=True)

        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"]

        return _extract_title_from_url(url)
    except Exception as e:
        print(f"Myntra extract error: {e}")
        return _extract_title_from_url(url)


def _extract_title_from_url(url: str):
    """Extract a product name from Myntra URL slug."""
    try:
        path = urllib.parse.urlparse(url).path
        parts = path.strip("/").split("/")
        if parts:
            slug = parts[0]
            title = slug.replace("-", " ").replace("+", " ").title()
            return title if len(title) > 3 else None
    except:
        pass
    return None


# ---------------------------------------------------------------------------
# get_deals() → list[DealItem]
# ---------------------------------------------------------------------------

# Myntra deal/offer category slugs that usually show discounted products
_MYNTRA_DEAL_SLUGS = [
    "myntra-fashion-store",
    "offers",
    "men-clothing",
    "women-clothing",
    "electronics-accessories",
]

# Category mapping from Myntra's internal types
_MYNTRA_CATEGORY_MAP = {
    "Topwear": "Fashion",
    "Bottomwear": "Fashion",
    "Dress": "Fashion",
    "Footwear": "Footwear",
    "Sports Shoes": "Footwear",
    "Innerwear": "Fashion",
    "Accessories": "Accessories",
    "Jewellery": "Accessories",
    "Watches": "Electronics",
    "Bags": "Accessories",
    "Beauty": "Beauty",
    "Skin Care": "Beauty",
    "Fragrance": "Beauty",
    "Home Furnishing": "Home & Kitchen",
}


def get_deals() -> list[DealItem]:
    """Fetch product-level deals from Myntra via their internal API.

    Strategy:
      1. Hit the gateway search API with deal/offer slugs.
      2. Parse structured JSON product data into DealItems.
      3. Fall back to HTML extraction if API fails.
    """
    deals: list[DealItem] = []

    for slug in _MYNTRA_DEAL_SLUGS:
        if len(deals) >= 20:
            break

        new_deals = _fetch_myntra_slug(slug)
        deals.extend(new_deals)

    # Deduplicate by title
    seen_titles: set[str] = set()
    unique: list[DealItem] = []
    for d in deals:
        key = d.title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(d)

    return unique[:30]


def _fetch_myntra_slug(slug: str) -> list[DealItem]:
    """Fetch products from a Myntra slug via their gateway API."""
    session = _get_myntra_session()
    api_url = f"https://www.myntra.com/gateway/v2/search/{urllib.parse.quote(slug)}"

    params = {
        "p": "1",
        "rows": "20",
        "o": "0",
        "platefrom": "desktop",
        "q": slug,
    }

    try:
        resp = session.get(api_url, params=params, timeout=20)

        if resp.status_code == 200:
            try:
                data = resp.json()
                products = data.get("products", [])
                return [_myntra_product_to_deal(p) for p in products[:15]
                        if _myntra_product_to_deal(p) is not None]
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: HTML extraction
        return _fetch_myntra_slug_html(slug)

    except Exception as e:
        print(f"Myntra API deals error ({slug}): {e}")
        return _fetch_myntra_slug_html(slug)


def _fetch_myntra_slug_html(slug: str) -> list[DealItem]:
    """Fallback: extract deal products from Myntra HTML page."""
    session = get_session()
    url = f"https://www.myntra.com/{urllib.parse.quote(slug)}"

    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'

        patterns = [
            r'window\.__myx\s*=\s*(\{.+?\});\s*</',
            r'"searchData"\s*:\s*(\{.+?\})\s*[,}]',
        ]

        for pattern in patterns:
            match = re.search(pattern, resp.text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    products = data.get("searchData", data).get("results", {}).get("products", [])
                    return [_myntra_product_to_deal(p) for p in products[:15]
                            if _myntra_product_to_deal(p) is not None]
                except (json.JSONDecodeError, KeyError):
                    continue

    except Exception as e:
        print(f"Myntra HTML deals error ({slug}): {e}")

    return []


def _myntra_product_to_deal(p: dict) -> DealItem | None:
    """Convert a Myntra API product dict into a DealItem."""
    try:
        brand = p.get("brand", "")
        product_name = p.get("product", p.get("productName", ""))
        title = f"{brand} {product_name}".strip()
        if not title or len(title) < 3:
            return None

        price = p.get("price")
        mrp = p.get("mrp")

        # Myntra sometimes gives price as int or float
        sell_price = float(price) if price else None
        original_price = float(mrp) if mrp else None

        # Discount from API or computed
        disc = p.get("discount") or p.get("discountDisplayLabel", "")
        discount_percent = None
        if disc:
            m = re.search(r'(\d+)\s*%', str(disc))
            if m:
                discount_percent = float(m.group(1))
        if not discount_percent:
            discount_percent = compute_discount(sell_price, original_price)

        # Images
        search_img = p.get("searchImage")
        images = [search_img] if search_img else []
        # Some products have an images array
        if p.get("images"):
            for img_obj in p["images"][:3]:
                src = img_obj.get("src") if isinstance(img_obj, dict) else str(img_obj)
                if src and src not in images:
                    images.append(src)

        # Link
        landing = p.get("landingPageUrl", "")
        link = f"https://www.myntra.com/{landing}" if landing else None

        # Rating
        rating_obj = p.get("rating") or p.get("ratings")
        rating = None
        rating_count = None
        if isinstance(rating_obj, dict):
            rating = rating_obj.get("averageRating")
            rating_count = rating_obj.get("totalCount") or rating_obj.get("ratingCount")
        elif isinstance(rating_obj, (int, float)):
            rating = float(rating_obj)
            rating_count = p.get("ratingCount")

        # Category mapping
        raw_cat = (
            p.get("masterCategory", {}).get("typeName", "") if isinstance(p.get("masterCategory"), dict)
            else p.get("articleType", {}).get("typeName", "") if isinstance(p.get("articleType"), dict)
            else p.get("subCategory", {}).get("typeName", "") if isinstance(p.get("subCategory"), dict)
            else ""
        )
        category = _MYNTRA_CATEGORY_MAP.get(raw_cat, "Fashion")

        discount_type = f"{int(discount_percent)}% off" if discount_percent else None

        return DealItem(
            title=title,
            brand=brand or extract_brand(title),
            discountType=discount_type,
            discountPercent=discount_percent,
            price=sell_price,
            originalPrice=original_price,
            category=category,
            images=images,
            platformName="Myntra",
            platformLink=link,
            rating=float(rating) if rating else None,
            ratingCount=int(rating_count) if rating_count else None,
            noCostEMI=False,  # Myntra doesn't typically offer EMI
            affiliateUrl=link or "#",
        )
    except Exception as e:
        print(f"Myntra product parse error: {e}")
        return None
