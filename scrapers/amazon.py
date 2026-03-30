from bs4 import BeautifulSoup
from core.http_client import get_session
from models.deal import DealItem, parse_price, compute_discount, extract_brand
import urllib.parse
import re


def search_product(query: str):
    """Search Amazon.in for products (legacy helper, unchanged)."""
    session = get_session()
    url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(query)}"
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        results = []

        items = soup.select("div[data-component-type='s-search-result']")
        for item in items[:10]:
            h2_elem = item.select_one("h2")
            title = h2_elem.get_text(strip=True) if h2_elem else None

            price_whole = item.select_one("span.a-price-whole")
            link_elem = item.select_one("h2 a, a.a-link-normal.s-no-outline")
            img_elem = item.select_one("img.s-image")

            if not title:
                continue

            price = None
            if price_whole:
                price = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
                price = f"₹{price}"

            link = None
            if link_elem and link_elem.get("href"):
                href = link_elem["href"]
                link = ("https://www.amazon.in" + href) if href.startswith("/") else href

            image = img_elem["src"] if img_elem and img_elem.get("src") else None

            results.append({
                "platform": "Amazon",
                "title": title,
                "price": price,
                "link": link,
                "image": image
            })
        return results
    except Exception as e:
        print(f"Amazon search error: {e}")
        return []


def extract_product_title(url: str):
    """Extract product title from an Amazon product URL."""
    session = get_session()
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        title_elem = soup.select_one("#productTitle")
        if title_elem:
            return title_elem.get_text(strip=True)
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"]
        if soup.title:
            t = soup.title.get_text(strip=True)
            t = re.sub(r'^Amazon\.in\s*:\s*', '', t)
            return t
    except Exception as e:
        print(f"Amazon extract error: {e}")
    return None


# ---------------------------------------------------------------------------
# get_deals() → list[DealItem]
# ---------------------------------------------------------------------------

def get_deals() -> list[DealItem]:
    """Scrape actual product-level deals from Amazon.in.

    Strategy:
      1. Try /gp/goldbox (Today's Deals) for structured product cards.
      2. Fall back to search-based deal queries to get real products.
    """
    deals = _scrape_goldbox()
    if not deals:
        deals = _scrape_deals_search()
    return deals


def _scrape_goldbox() -> list[DealItem]:
    """Scrape Amazon.in/gp/goldbox (Today's Deals) for product cards."""
    session = get_session()
    deals: list[DealItem] = []
    try:
        resp = session.get("https://www.amazon.in/gp/goldbox", timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        # Deal cards on goldbox page
        cards = soup.select(
            "div[data-testid='deal-card'], "
            "div.DealCard-module__dealCard, "
            "div[class*='DealCard'], "
            "div.a-section.dealContainer"
        )

        for card in cards[:100]:
            deal = _parse_amazon_deal_card(card)
            if deal:
                deals.append(deal)

        if not deals:
            items = soup.select("div[data-component-type='s-search-result'], li.a-spacing-none")
            for item in items[:100]:
                deal = _parse_amazon_search_item(item)
                if deal:
                    deals.append(deal)

    except Exception as e:
        print(f"Amazon goldbox scrape error: {e}")

    return deals


def _scrape_deals_search() -> list[DealItem]:
    """Fallback: search Amazon for deal/offer keywords to get real products."""
    session = get_session()
    deals: list[DealItem] = []

    queries = [
        "todays deals",
        "lightning deals",
        "deals of the day",
    ]

    for q in queries:
        if len(deals) >= 150:
            break
        try:
            url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(q)}&deals=1"
            resp = session.get(url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')

            items = soup.select("div[data-component-type='s-search-result']")
            for item in items[:50]:
                deal = _parse_amazon_search_item(item)
                if deal:
                    deals.append(deal)
        except Exception as e:
            print(f"Amazon deals search error ({q}): {e}")

    return deals


def _parse_amazon_deal_card(card) -> DealItem | None:
    """Parse a deal card element from the goldbox/deals page."""
    try:
        title_el = card.select_one(
            "a[class*='DealLink'] span, "
            "span[class*='DealContent'], "
            "a.a-link-normal span.a-truncate-full, "
            "span.a-size-base"
        )
        title = title_el.get_text(strip=True) if title_el else None
        if not title or len(title) < 5:
            return None

        price_el = card.select_one("span.a-price span.a-offscreen, span.a-price-whole")
        price = parse_price(price_el.get_text(strip=True) if price_el else None)

        orig_el = card.select_one(
            "span.a-price[data-a-strike='true'] span.a-offscreen, "
            "span.a-text-price span.a-offscreen"
        )
        original_price = parse_price(orig_el.get_text(strip=True) if orig_el else None)

        disc_el = card.select_one(
            "span[class*='savingsPercentage'], "
            "span.a-badge-text, "
            "span[data-a-badge-color]"
        )
        disc_text = disc_el.get_text(strip=True) if disc_el else None
        discount_percent = _parse_discount_percent(disc_text)

        if not discount_percent:
            discount_percent = compute_discount(price, original_price)

        link_el = card.select_one("a[href]")
        link = _make_amazon_link(link_el)

        img_el = card.select_one("img[src]")
        images = [img_el["src"]] if img_el and img_el.get("src") else []

        rating, rating_count = _extract_rating(card)
        no_cost_emi = _has_no_cost_emi(card)
        brand = extract_brand(title)
        discount_type = f"{int(discount_percent)}% off" if discount_percent else None

        return DealItem(
            title=title,
            brand=brand,
            discountType=discount_type,
            discountPercent=discount_percent,
            price=price,
            originalPrice=original_price,
            category="General",
            images=images,
            platformName="Amazon",
            platformLink=link,
            rating=rating,
            ratingCount=rating_count,
            noCostEMI=no_cost_emi,
            affiliateUrl=link or "#",
        )
    except Exception as e:
        print(f"Amazon deal card parse error: {e}")
        return None


def _parse_amazon_search_item(item) -> DealItem | None:
    """Parse a search result item into a DealItem."""
    try:
        h2_elem = item.select_one("h2")
        title = h2_elem.get_text(strip=True) if h2_elem else None
        if not title or len(title) < 5:
            return None

        # Selling price
        price_el = item.select_one("span.a-price:not([data-a-strike]) span.a-offscreen")
        if not price_el:
            price_el = item.select_one("span.a-price-whole")
        price = parse_price(price_el.get_text(strip=True) if price_el else None)

        # Original price (strikethrough)
        orig_el = item.select_one(
            "span.a-price[data-a-strike='true'] span.a-offscreen, "
            "span.a-text-price span.a-offscreen"
        )
        original_price = parse_price(orig_el.get_text(strip=True) if orig_el else None)

        discount_percent = compute_discount(price, original_price)

        link_el = item.select_one("h2 a, a.a-link-normal.s-no-outline")
        link = _make_amazon_link(link_el)

        img_el = item.select_one("img.s-image")
        images = [img_el["src"]] if img_el and img_el.get("src") else []

        rating, rating_count = _extract_rating(item)
        no_cost_emi = _has_no_cost_emi(item)
        category = _extract_category(item)
        brand = extract_brand(title)
        discount_type = f"{int(discount_percent)}% off" if discount_percent else None

        return DealItem(
            title=title,
            brand=brand,
            discountType=discount_type,
            discountPercent=discount_percent,
            price=price,
            originalPrice=original_price,
            category=category,
            images=images,
            platformName="Amazon",
            platformLink=link,
            rating=rating,
            ratingCount=rating_count,
            noCostEMI=no_cost_emi,
            affiliateUrl=link or "#",
        )
    except Exception as e:
        print(f"Amazon search item parse error: {e}")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_amazon_link(el) -> str | None:
    if not el or not el.get("href"):
        return None
    href = el["href"]
    return ("https://www.amazon.in" + href) if href.startswith("/") else href


def _parse_discount_percent(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r'(\d+)\s*%', text)
    return float(m.group(1)) if m else None


def _extract_rating(container) -> tuple[float | None, int | None]:
    rating = None
    count = None

    star_el = container.select_one("span.a-icon-alt, i[class*='a-star'] span.a-icon-alt")
    if star_el:
        m = re.search(r'([\d.]+)\s*out of', star_el.get_text(strip=True))
        if m:
            rating = float(m.group(1))

    count_el = container.select_one(
        "span.a-size-base.s-underline-text, "
        "span[aria-label*='ratings'], "
        "a[href*='customerReviews'] span"
    )
    if count_el:
        text = count_el.get_text(strip=True).replace(",", "")
        m = re.search(r'(\d+)', text)
        if m:
            count = int(m.group(1))

    return rating, count


def _has_no_cost_emi(container) -> bool:
    text = container.get_text(separator=" ", strip=True).lower()
    return "no cost emi" in text or "no-cost emi" in text


def _extract_category(container) -> str:
    badge = container.select_one("span.a-badge-text")
    if badge:
        text = badge.get_text(strip=True)
        if text and "%" not in text and len(text) < 30:
            return text
    return "General"
