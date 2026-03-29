"""
Flipkart scraper using Playwright headless browser.
Flipkart blocks standard HTTP requests with Google reCAPTCHA Enterprise,
but Playwright with a real Chromium browser bypasses it successfully.
"""
from playwright.sync_api import sync_playwright
from core.config import PROXY_URL
from models.deal import DealItem, parse_price, compute_discount, extract_brand
import urllib.parse
import re


def _get_proxy_config():
    """Parse the proxy URL into Playwright's expected format."""
    if not PROXY_URL:
        return None
    parsed = urllib.parse.urlparse(PROXY_URL)
    return {
        "server": f"http://{parsed.hostname}:{parsed.port}",
        "username": parsed.username,
        "password": parsed.password,
    }


def _launch_browser(playwright):
    """Launch a headless Chromium browser with proxy."""
    proxy_config = _get_proxy_config()
    return playwright.chromium.launch(
        headless=True,
        proxy=proxy_config
    )


def search_product(query: str):
    """Search Flipkart for products using Playwright (unchanged)."""
    url = f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(query)}"
    results = []

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            try:
                page.goto(url, timeout=25000)
                page.wait_for_timeout(4000)

                content = page.content()
                if "recaptcha" in content.lower() or "are you a human" in content.lower():
                    print("Flipkart: CAPTCHA detected even with Playwright")
                    browser.close()
                    return []

                product_cards = page.query_selector_all("div[data-id]")

                for card in product_cards[:10]:
                    try:
                        title_el = card.query_selector("a[class*='wjcEIp'], a[class*='IRpwTa'], div[class*='_4rR01T'], a[class*='s1Q9rs']")
                        if not title_el:
                            title_el = card.query_selector("a[title], div[class*='col'] a")
                        title = title_el.get_attribute("title") or title_el.inner_text() if title_el else None

                        if not title or len(title.strip()) < 3:
                            continue

                        price_el = card.query_selector("div.hZ3P6w, div[class*='_30jeq3'], div[class*='Nx9bqj']")
                        price = price_el.inner_text().strip() if price_el else None

                        link_el = card.query_selector("a[href]")
                        link = None
                        if link_el:
                            href = link_el.get_attribute("href")
                            if href and href.startswith("/"):
                                link = "https://www.flipkart.com" + href
                            elif href:
                                link = href

                        img_el = card.query_selector("img[src*='rukminim'], img[src*='flixcart']")
                        image = img_el.get_attribute("src") if img_el else None

                        results.append({
                            "platform": "Flipkart",
                            "title": title.strip(),
                            "price": price,
                            "link": link,
                            "image": image
                        })
                    except Exception:
                        continue

            except Exception as e:
                print(f"Flipkart Playwright navigation error: {e}")
            finally:
                browser.close()

    except Exception as e:
        print(f"Flipkart Playwright launch error: {e}")

    return results


def extract_product_title(url: str):
    """Extract product title from a Flipkart product URL using Playwright."""
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            try:
                page.goto(url, timeout=25000)
                page.wait_for_timeout(3000)

                content = page.content()
                if "recaptcha" in content.lower():
                    browser.close()
                    return _extract_title_from_url(url)

                for selector in ["span.B_NuCI", "h1._9E25nV", "span.VU-ZEz", "h1[class*='yhB1nd']"]:
                    el = page.query_selector(selector)
                    if el:
                        title = el.inner_text().strip()
                        if title:
                            browser.close()
                            return title

                title = page.title()
                if title and "Flipkart" in title:
                    title = title.split("|")[0].strip().rstrip("- ").strip()
                    if title:
                        browser.close()
                        return title

            except Exception as e:
                print(f"Flipkart extract error: {e}")
            finally:
                browser.close()
    except Exception as e:
        print(f"Flipkart Playwright launch error: {e}")

    return _extract_title_from_url(url)


def _extract_title_from_url(url: str):
    """Extract product name from Flipkart URL slug as last resort."""
    try:
        path = urllib.parse.urlparse(url).path
        slug = path.strip("/").split("/")[0]
        title = slug.replace("-", " ").title()
        return title if len(title) > 3 else None
    except:
        return None


# ---------------------------------------------------------------------------
# get_deals() → list[DealItem]
# ---------------------------------------------------------------------------

def get_deals() -> list[DealItem]:
    """Scrape Flipkart deals pages for individual product cards.

    Strategy:
      1. Try /offers-store and /deals-of-the-day for product grids.
      2. Parse product cards (div[data-id]), deal tiles, or product links.
      3. Fallback: search Flipkart for deal keywords to get real products.
    """
    deals: list[DealItem] = []

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            try:
                # ---------- Phase 1: Deal/Offer pages ----------
                for deals_url in [
                    "https://www.flipkart.com/offers-store",
                    "https://www.flipkart.com/deals-of-the-day",
                ]:
                    if len(deals) >= 20:
                        break

                    try:
                        page.goto(deals_url, timeout=30000)
                        page.wait_for_timeout(5000)

                        content = page.content()
                        if "recaptcha" in content.lower():
                            print(f"[Flipkart] CAPTCHA detected on {deals_url}, skipping")
                            continue

                        print(f"[Flipkart] Loaded {deals_url}, page length={len(content)}")

                        # Strategy 1: Product cards with data-id
                        product_cards = page.query_selector_all("div[data-id]")
                        print(f"[Flipkart] Strategy 1 — div[data-id] cards found: {len(product_cards)}")
                        for card in product_cards[:20]:
                            deal = _parse_flipkart_product_card(card)
                            if deal:
                                deals.append(deal)

                        # Strategy 2: Deal tiles / offer cards
                        if not deals:
                            tiles = page.query_selector_all(
                                "div[class*='_1sdMkc'], "
                                "div[class*='_2kHMtA'], "
                                "a[class*='_2rpwqI'], "
                                "div[class*='_4ddWXP']"
                            )
                            print(f"[Flipkart] Strategy 2 — deal tiles found: {len(tiles)}")
                            for tile in tiles[:20]:
                                deal = _parse_flipkart_tile(tile)
                                if deal:
                                    deals.append(deal)

                        # Strategy 3: Product links (/p/ pattern)
                        if not deals:
                            all_links = page.query_selector_all("a[href*='/p/']")
                            print(f"[Flipkart] Strategy 3 — /p/ links found: {len(all_links)}")
                            for link_el in all_links[:20]:
                                deal = _parse_flipkart_product_link(link_el, page)
                                if deal:
                                    deals.append(deal)

                    except Exception as e:
                        print(f"[Flipkart] Deals page error ({deals_url}): {e}")

                # ---------- Phase 2: Search-based fallback ----------
                if not deals:
                    print("[Flipkart] No deals from offer pages, trying search fallback...")
                    search_queries = [
                        "deals of the day",
                        "best offers today",
                        "top deals",
                    ]
                    for q in search_queries:
                        if len(deals) >= 20:
                            break
                        try:
                            search_url = f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(q)}"
                            page.goto(search_url, timeout=30000)
                            page.wait_for_timeout(5000)

                            content = page.content()
                            if "recaptcha" in content.lower():
                                print(f"[Flipkart] CAPTCHA on search '{q}', skipping")
                                continue

                            product_cards = page.query_selector_all("div[data-id]")
                            print(f"[Flipkart] Search '{q}' — found {len(product_cards)} product cards")
                            for card in product_cards[:10]:
                                deal = _parse_flipkart_product_card(card)
                                if deal:
                                    deals.append(deal)

                        except Exception as e:
                            print(f"[Flipkart] Search fallback error ({q}): {e}")

            except Exception as e:
                print(f"[Flipkart] Navigation error: {e}")
            finally:
                browser.close()

    except Exception as e:
        print(f"[Flipkart] Playwright launch error: {e}")

    print(f"[Flipkart] Total deals scraped: {len(deals)}")
    return deals


def _parse_flipkart_product_card(card) -> DealItem | None:
    """Parse a Flipkart product card (div[data-id]) into a DealItem.
    
    Uses broad selectors + full text fallback since Flipkart constantly
    changes their CSS class names.
    """
    try:
        # ---------- Title ----------
        # Try known selectors first, then any <a> with a title attr, then first <a>
        title_el = (
            card.query_selector("a[class*='wjcEIp']") or
            card.query_selector("a[class*='IRpwTa']") or
            card.query_selector("div[class*='_4rR01T']") or
            card.query_selector("a[class*='s1Q9rs']") or
            card.query_selector("a[title]") or
            card.query_selector("a[href*='/p/']")
        )
        title = None
        if title_el:
            title = title_el.get_attribute("title") or title_el.inner_text()
        
        # Fallback: grab title from the full text (first meaningful line)
        if not title or len(title.strip()) < 3:
            full_text = card.inner_text()
            lines = [l.strip() for l in full_text.split("\n") if l.strip() and len(l.strip()) > 3]
            # Skip lines that are just prices or discount badges
            for line in lines:
                if not re.match(r'^[₹\d,%\s.off]+$', line, re.IGNORECASE):
                    title = line
                    break

        if not title or len(title.strip()) < 3:
            return None
        title = title.strip()[:200]

        # ---------- Price (selling price — ₹ symbol) ----------
        price_el = (
            card.query_selector("div[class*='Nx9bqj']") or
            card.query_selector("div[class*='_30jeq3']") or
            card.query_selector("div.hZ3P6w")
        )
        price = parse_price(price_el.inner_text() if price_el else None)

        # Fallback: find ₹ in text
        if price is None:
            full_text = card.inner_text()
            price_matches = re.findall(r'₹\s*([\d,]+)', full_text)
            if price_matches:
                # First ₹ value is usually the selling price
                price = parse_price(f"₹{price_matches[0]}")

        # ---------- Original price (strikethrough / MRP) ----------
        orig_el = (
            card.query_selector("div[class*='yRaY8j']") or
            card.query_selector("div[class*='_3I9_wc']") or
            card.query_selector("div[class*='_27UcVY']") or
            card.query_selector("strike") or
            card.query_selector("del")
        )
        original_price = parse_price(orig_el.inner_text() if orig_el else None)

        # Fallback: second ₹ value is often MRP
        if original_price is None and price is not None:
            full_text = card.inner_text()
            price_matches = re.findall(r'₹\s*([\d,]+)', full_text)
            if len(price_matches) >= 2:
                candidate = parse_price(f"₹{price_matches[1]}")
                if candidate and candidate > price:
                    original_price = candidate

        # ---------- Discount ----------
        disc_el = (
            card.query_selector("div[class*='UkUFwK']") or
            card.query_selector("div[class*='_3Ay6Sb']") or
            card.query_selector("span[class*='UkUFwK']")
        )
        disc_text = disc_el.inner_text() if disc_el else None
        discount_percent = _parse_discount_pct(disc_text)

        # Fallback: look for "XX% off" anywhere in card text
        if not discount_percent:
            full_text = card.inner_text()
            m = re.search(r'(\d+)\s*%\s*off', full_text, re.IGNORECASE)
            if m:
                discount_percent = float(m.group(1))

        if not discount_percent:
            discount_percent = compute_discount(price, original_price)

        # ---------- Link ----------
        link_el = card.query_selector("a[href*='/p/']") or card.query_selector("a[href]")
        link = _make_flipkart_link(link_el)

        # ---------- Image ----------
        img_el = (
            card.query_selector("img[src*='rukminim']") or
            card.query_selector("img[src*='flixcart']") or
            card.query_selector("img[src]")
        )
        img_src = img_el.get_attribute("src") if img_el else None
        images = [img_src] if img_src and not img_src.startswith("data:") else []

        # ---------- Rating ----------
        rating, rating_count = _extract_flipkart_rating(card)

        # ---------- No Cost EMI ----------
        no_cost_emi = _flipkart_has_emi(card)

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
            platformName="Flipkart",
            platformLink=link,
            rating=rating,
            ratingCount=rating_count,
            noCostEMI=no_cost_emi,
            affiliateUrl=link or "#",
        )
    except Exception as e:
        print(f"[Flipkart] Card parse error: {e}")
        return None


def _parse_flipkart_tile(tile) -> DealItem | None:
    """Parse a deal tile/offer card."""
    try:
        # Get any text content
        text = tile.inner_text()
        if not text or len(text.strip()) < 5:
            return None

        # Try to find title
        title_el = tile.query_selector("a, span, div")
        title = title_el.inner_text().strip() if title_el else text.strip()
        if len(title) < 5:
            return None

        # Price
        price_match = re.search(r'₹\s*[\d,]+', text)
        price = parse_price(price_match.group(0)) if price_match else None

        # Discount
        disc_match = re.search(r'(\d+)\s*%\s*off', text, re.IGNORECASE)
        discount_percent = float(disc_match.group(1)) if disc_match else None

        # Link
        link_el = tile.query_selector("a[href]")
        link = _make_flipkart_link(link_el)

        # Image
        img_el = tile.query_selector("img[src]")
        images = [img_el.get_attribute("src")] if img_el else []

        brand = extract_brand(title)
        discount_type = f"{int(discount_percent)}% off" if discount_percent else None

        return DealItem(
            title=title[:200],
            brand=brand,
            discountType=discount_type,
            discountPercent=discount_percent,
            price=price,
            originalPrice=None,
            category="General",
            images=images,
            platformName="Flipkart",
            platformLink=link,
            rating=None,
            ratingCount=None,
            noCostEMI=False,
            affiliateUrl=link or "#",
        )
    except Exception:
        return None


def _parse_flipkart_product_link(link_el, page) -> DealItem | None:
    """Parse a product link element (/p/ URL pattern)."""
    try:
        href = link_el.get_attribute("href")
        if not href:
            return None

        # Get parent container for context
        parent = link_el.query_selector("xpath=..")
        if not parent:
            return None

        text = parent.inner_text()
        if not text or len(text.strip()) < 5:
            return None

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = lines[0] if lines else None
        if not title or len(title) < 5:
            return None

        price_match = re.search(r'₹\s*[\d,]+', text)
        price = parse_price(price_match.group(0)) if price_match else None

        disc_match = re.search(r'(\d+)\s*%\s*off', text, re.IGNORECASE)
        discount_percent = float(disc_match.group(1)) if disc_match else None

        link = _make_flipkart_link_from_href(href)

        img_el = parent.query_selector("img[src]")
        images = [img_el.get_attribute("src")] if img_el else []

        brand = extract_brand(title)
        discount_type = f"{int(discount_percent)}% off" if discount_percent else None

        return DealItem(
            title=title[:200],
            brand=brand,
            discountType=discount_type,
            discountPercent=discount_percent,
            price=price,
            originalPrice=None,
            category="General",
            images=images,
            platformName="Flipkart",
            platformLink=link,
            rating=None,
            ratingCount=None,
            noCostEMI=False,
            affiliateUrl=link or "#",
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flipkart_link(el) -> str | None:
    if not el:
        return None
    href = el.get_attribute("href")
    return _make_flipkart_link_from_href(href)


def _make_flipkart_link_from_href(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("/"):
        return "https://www.flipkart.com" + href
    return href


def _parse_discount_pct(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r'(\d+)\s*%', text)
    return float(m.group(1)) if m else None


def _extract_flipkart_rating(container) -> tuple[float | None, int | None]:
    rating = None
    count = None

    # Rating badge: "4.2 ★" or "4.2" inside a green/colored badge
    rating_el = (
        container.query_selector("div[class*='XQDdHH']") or
        container.query_selector("div[class*='_3LWZlK']") or
        container.query_selector("span[class*='_1lRcqv']") or
        container.query_selector("div[class*='hGSR34']") or
        container.query_selector("span[class*='Y1HWO0']")
    )
    if rating_el:
        text = rating_el.inner_text().strip()
        m = re.search(r'([\d.]+)', text)
        if m:
            val = float(m.group(1))
            if 0 < val <= 5:
                rating = val

    # Rating count: "(12,450)" or "12,450 Ratings"
    count_el = (
        container.query_selector("span[class*='Wphh3N']") or
        container.query_selector("span[class*='_2_R_DZ']") or
        container.query_selector("span[class*='_13vcmD']")
    )
    if count_el:
        text = count_el.inner_text().strip().replace(",", "")
        m = re.search(r'(\d+)', text)
        if m:
            count = int(m.group(1))

    # Fallback: search full text for rating pattern
    if rating is None:
        try:
            full_text = container.inner_text()
            m = re.search(r'([\d.]+)\s*[★⭐]', full_text)
            if m:
                val = float(m.group(1))
                if 0 < val <= 5:
                    rating = val
        except:
            pass

    return rating, count


def _flipkart_has_emi(container) -> bool:
    try:
        text = container.inner_text().lower()
        return "no cost emi" in text
    except:
        return False
