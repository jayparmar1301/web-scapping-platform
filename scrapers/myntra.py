"""
Myntra scraper using Playwright headless browser + internal API interception.
Myntra is a React SPA that requires a real browser session — plain HTTP
requests return 401/500. Playwright loads the pages, executes JS, and we
intercept the XHR responses to get clean product JSON.
"""
from playwright.sync_api import sync_playwright
from core.http_client import get_session
from core.config import PROXY_URL
from models.deal import DealItem, parse_price, compute_discount, extract_brand
import urllib.parse
import json
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
    """Launch a headed Chromium browser with proxy."""
    proxy_config = _get_proxy_config()
    return playwright.chromium.launch(
        headless=False,
        proxy=proxy_config
    )


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
    "Shirts": "Fashion",
    "Tshirts": "Fashion",
    "Jeans": "Fashion",
    "Saree": "Fashion",
    "Kurtas": "Fashion",
    "Flip Flops": "Footwear",
    "Casual Shoes": "Footwear",
    "Sports Sandals": "Footwear",
    "Heels": "Footwear",
    "Backpacks": "Accessories",
    "Sunglasses": "Accessories",
    "Perfume And Body Mist": "Beauty",
    "Lipstick": "Beauty",
    "Foundation And Primer": "Beauty",
    "Bedsheets": "Home & Kitchen",
    "Cushion Covers": "Home & Kitchen",
}


def get_deals() -> list[DealItem]:
    """Dynamically discover and scrape Myntra deals.

    Strategy (fully dynamic):
      1. Discover category paths from Myntra homepage/nav (plain HTTP — works).
      2. Open ONE Playwright browser session.
      3. For each discovered path, load the listing page in the browser,
         intercept XHR product data OR parse the rendered DOM.
      4. If discovery paths yield nothing, try trending search terms.
    """
    deals: list[DealItem] = []

    # Phase 1: Discover category paths dynamically (plain HTTP)
    discovered_paths = _discover_category_paths()
    print(f"[Myntra] Discovered {len(discovered_paths)} category paths")

    # Phase 2 & 3: Use a SINGLE browser session for all fetching
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()

            # Intercept API responses to capture product JSON
            captured_products: list[dict] = []

            def _on_response(response):
                """Intercept XHR responses that contain product data."""
                url = response.url
                try:
                    if response.status == 200 and any(
                        kw in url for kw in (
                            "/gateway/v2/search/",
                            "/gateway/v1/search/",
                            "/api/search/",
                            "searchData",
                        )
                    ):
                        ct = response.headers.get("content-type", "")
                        if "json" in ct or "javascript" in ct:
                            data = response.json()
                            products = data.get("products", [])
                            if products:
                                captured_products.extend(products)
                                print(f"[Myntra] Intercepted {len(products)} products from XHR")
                except Exception:
                    pass  # Ignore non-JSON or failed reads

            page.on("response", _on_response)

            try:
                # --- Phase 2: Fetch from discovered paths ---
                for path in discovered_paths:
                    if len(deals) >= 30:
                        break

                    captured_products.clear()
                    new_deals = _fetch_with_browser(page, path, captured_products)
                    print(f"[Myntra] '{path}' → {len(new_deals)} products")
                    deals.extend(new_deals)

                # --- Phase 3: Trending search fallback ---
                if not deals:
                    print("[Myntra] Discovery yielded 0 deals, trying trending search...")
                    trending = _get_trending_searches(page)
                    for term in trending:
                        if len(deals) >= 20:
                            break

                        captured_products.clear()
                        new_deals = _fetch_with_browser(page, term, captured_products)
                        print(f"[Myntra] Trending '{term}' → {len(new_deals)} products")
                        deals.extend(new_deals)

            except Exception as e:
                print(f"[Myntra] Browser session error: {e}")
            finally:
                browser.close()

    except Exception as e:
        print(f"[Myntra] Playwright launch error: {e}")

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[DealItem] = []
    for d in deals:
        key = d.title.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(d)

    print(f"[Myntra] Total deals scraped: {len(unique)}")
    return unique[:30]


# ---------------------------------------------------------------------------
# Phase 1: Dynamic discovery
# ---------------------------------------------------------------------------

def _discover_category_paths() -> list[str]:
    """Discover product listing category paths from Myntra's homepage.

    Scrapes the homepage HTML for navigation links, banner links,
    and embedded config to find all active category listing URLs.
    Returns a list of path slugs like ['men-tshirts', 'women-kurtas', ...].
    """
    session = get_session()
    discovered: list[str] = []
    seen_paths: set[str] = set()

    try:
        resp = session.get("https://www.myntra.com", timeout=20)
        resp.encoding = 'utf-8'
        html = resp.text
        print(f"[Myntra] Homepage loaded, length={len(html)}")

        # Extract all internal hrefs from the page
        href_pattern = re.compile(
            r'href=["\'](?:https?://(?:www\.)?myntra\.com)?/([a-z0-9][a-z0-9\-]+(?:/[a-z0-9\-]+)*)["\']',
            re.IGNORECASE,
        )

        for match in href_pattern.finditer(html):
            path = match.group(1).strip("/").lower()

            # Skip non-listing pages
            if _is_listing_path(path) and path not in seen_paths:
                seen_paths.add(path)
                discovered.append(path)

        # Also try to extract from embedded JSON config / navigation data
        nav_patterns = [
            r'"link"\s*:\s*"/?([a-z0-9][a-z0-9\-]+(?:/[a-z0-9\-]+)*)"',
            r'"url"\s*:\s*"/?([a-z0-9][a-z0-9\-]+(?:/[a-z0-9\-]+)*)"',
            r'"href"\s*:\s*"/?([a-z0-9][a-z0-9\-]+(?:/[a-z0-9\-]+)*)"',
        ]
        for pat in nav_patterns:
            for m in re.finditer(pat, html, re.IGNORECASE):
                path = m.group(1).strip("/").lower()
                if _is_listing_path(path) and path not in seen_paths:
                    seen_paths.add(path)
                    discovered.append(path)

    except Exception as e:
        print(f"[Myntra] Homepage discovery error: {e}")

    # If discovery is empty or too few, also try the offers page
    if len(discovered) < 5:
        offers_paths = _discover_from_offers_page()
        for p in offers_paths:
            if p not in seen_paths:
                seen_paths.add(p)
                discovered.append(p)

    # Prioritize: put paths with sale/offer/deal keywords first
    priority_keywords = {"sale", "offer", "deal", "discount", "clearance", "end-of-season"}
    discovered.sort(
        key=lambda p: (0 if any(kw in p for kw in priority_keywords) else 1, p)
    )

    # Cap to avoid too many requests
    return discovered[:15]


def _discover_from_offers_page() -> list[str]:
    """Discover category links from Myntra's offers/deals page."""
    session = get_session()
    paths: list[str] = []

    try:
        resp = session.get("https://www.myntra.com/offers", timeout=20)
        resp.encoding = 'utf-8'
        print(f"[Myntra] Offers page loaded, length={len(resp.text)}")

        href_pattern = re.compile(
            r'href=["\'](?:https?://(?:www\.)?myntra\.com)?/([a-z0-9][a-z0-9\-]+(?:/[a-z0-9\-]+)*)["\']',
            re.IGNORECASE,
        )
        seen: set[str] = set()
        for match in href_pattern.finditer(resp.text):
            path = match.group(1).strip("/").lower()
            if _is_listing_path(path) and path not in seen:
                seen.add(path)
                paths.append(path)

    except Exception as e:
        print(f"[Myntra] Offers page discovery error: {e}")

    return paths


def _is_listing_path(path: str) -> bool:
    """Check if a URL path likely points to a product listing page."""
    # Skip known non-listing pages
    skip_prefixes = (
        "login", "register", "checkout", "cart", "wishlist", "account",
        "help", "faqs", "about", "contact", "privacy", "terms",
        "careers", "sitemap", "gateway", "api", "static", "assets",
        "img", "images", "fonts", "js", "css", "shop",
    )
    skip_exact = {
        "offers", "offer", "myntra-fashion-store", "myntra-insider",
        "gift-card", "gift-cards", "coupons",
    }

    if not path or len(path) < 3:
        return False
    if path in skip_exact:
        return False
    if any(path.startswith(p) for p in skip_prefixes):
        return False
    # Skip product detail pages (contain /p/ or numeric IDs at end)
    if "/p/" in path or re.search(r'/\d{5,}$', path):
        return False
    # Skip paths with too many segments (likely deep pages, not listings)
    if path.count("/") > 2:
        return False
    # Must contain at least one alphabetic character
    if not re.search(r'[a-z]', path):
        return False

    return True


# ---------------------------------------------------------------------------
# Phase 2: Fetch deals using Playwright browser
# ---------------------------------------------------------------------------

def _fetch_with_browser(page, path: str, captured_products: list[dict]) -> list[DealItem]:
    """Load a Myntra listing page in the browser and extract products.

    Three extraction strategies:
      1. Intercept XHR responses (cleanest — gives raw API JSON).
      2. Extract embedded __myx JSON from page source.
      3. Parse the rendered DOM product cards directly.
    """
    url = (
        f"https://www.myntra.com/{urllib.parse.quote(path)}"
        f"?sort=discount"
    )

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        # Wait for products to load (React hydration + API calls)
        page.wait_for_timeout(5000)

        content = page.content()
        print(f"[Myntra] Browser loaded '{path}', page length={len(content)}")

        # Check for captcha / block
        if "robot" in content.lower() or "blocked" in content.lower():
            print(f"[Myntra] Possible block detected on '{path}'")

        # --- Strategy 1: Products captured via XHR interception ---
        if captured_products:
            print(f"[Myntra] Strategy 1 (XHR) — {len(captured_products)} products intercepted")
            results = []
            for p in captured_products[:20]:
                deal = _myntra_product_to_deal(p)
                if deal:
                    results.append(deal)
            if results:
                return results

        # --- Strategy 2: Extract __myx embedded JSON from page source ---
        products = _extract_products_from_page(content)
        if products:
            print(f"[Myntra] Strategy 2 (embedded JSON) — {len(products)} products")
            results = []
            for p in products[:20]:
                deal = _myntra_product_to_deal(p)
                if deal:
                    results.append(deal)
            if results:
                return results

        # --- Strategy 3: Parse rendered DOM product cards ---
        results = _parse_dom_product_cards(page)
        if results:
            print(f"[Myntra] Strategy 3 (DOM) — {len(results)} products")
            return results

    except Exception as e:
        print(f"[Myntra] Browser fetch error ({path}): {e}")

    return []


def _extract_products_from_page(html: str) -> list[dict]:
    """Extract product dicts from Myntra's embedded JSON in page source."""
    patterns = [
        r'window\.__myx\s*=\s*(\{.+?\});\s*</script',
        r'"searchData"\s*:\s*(\{.+?\})\s*,\s*"',
        r'"products"\s*:\s*(\[(?:\{.+?\}(?:\s*,\s*\{.+?\})*)\])',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                raw = match.group(1)
                data = json.loads(raw)

                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    products = (
                        data.get("products")
                        or data.get("results", {}).get("products")
                        or data.get("searchData", {}).get("results", {}).get("products")
                    )
                    if products and isinstance(products, list):
                        return products
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[Myntra] Embedded JSON parse error: {e}")
                continue

    return []


def _parse_dom_product_cards(page) -> list[DealItem]:
    """Parse product cards directly from the rendered Myntra DOM."""
    deals: list[DealItem] = []

    # Myntra product cards are typically in <li> with class containing "product-base"
    # or <div> elements inside the search results grid
    card_selectors = [
        "li.product-base",
        "li[class*='product']",
        "div[class*='product-productMetaInfo']",
        "div[data-testid='product-card']",
    ]

    cards = []
    for sel in card_selectors:
        cards = page.query_selector_all(sel)
        if cards:
            print(f"[Myntra] DOM selector '{sel}' matched {len(cards)} cards")
            break

    if not cards:
        # Broad fallback: any element with product-like structure
        cards = page.query_selector_all("li[class]")
        # Filter to only those containing price-like text
        filtered = []
        for card in cards[:50]:
            text = card.inner_text()
            if re.search(r'Rs\.?\s*\d+|₹\s*\d+', text):
                filtered.append(card)
        cards = filtered
        if cards:
            print(f"[Myntra] DOM broad fallback matched {len(cards)} cards")

    for card in cards[:20]:
        try:
            text = card.inner_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            # Myntra explicitly structures the Brand and Title
            b_el = card.query_selector("h3[class*='brand']")
            brand = b_el.inner_text().strip() if b_el else None

            pn_el = card.query_selector("h4[class*='product']")
            product_name = pn_el.inner_text().strip() if pn_el else None
            
            # If explicit selectors fail, fallback to heuristics over lines, ignoring rating strings
            if not brand or not product_name:
                for line in lines:
                    if re.match(r'^[\d.]+\s*\|', line) or line.strip() == '':
                        continue
                    if not brand:
                        brand = line
                    elif not product_name:
                        product_name = line
                        break

            title = f"{brand} {product_name}".strip() if brand and product_name else None

            price = None
            original_price = None
            discount_percent = None

            for line in lines:
                # Current price: "Rs. 499" or "₹499"
                price_match = re.search(r'(?:Rs\.?|₹)\s*([\d,]+)', line)
                if price_match and price is None:
                    price = parse_price(price_match.group(0))
                elif price_match and original_price is None and price is not None:
                    candidate = parse_price(price_match.group(0))
                    if candidate and candidate > price:
                        original_price = candidate

                # Discount: "(55% OFF)" or "55% off"
                disc_match = re.search(r'\(?\s*(\d+)\s*%\s*(?:OFF|off)\s*\)?', line)
                if disc_match:
                    discount_percent = float(disc_match.group(1))

            if not discount_percent:
                discount_percent = compute_discount(price, original_price)

            # Image
            img_el = card.query_selector("img[src], img[data-src]")
            img_src = None
            if img_el:
                img_src = img_el.get_attribute("src") or img_el.get_attribute("data-src")
            images = [img_src] if img_src and not img_src.startswith("data:") else []

            # Link
            link = None
            try:
                href = card.evaluate("el => { let a = el.closest('a') || el.querySelector('a'); return a ? a.getAttribute('href') : null; }")
                if href:
                    if href.startswith("http"):
                        link = href
                    else:
                        if not href.startswith("/"):
                            href = "/" + href
                        link = f"https://www.myntra.com{href}"
            except Exception:
                pass

            # Rating from DOM
            rating = None
            rating_count = None
            rating_el = card.query_selector("span[class*='rating'], div[class*='rating']")
            if rating_el:
                rt = rating_el.inner_text().strip()
                m = re.search(r'([\d.]+)', rt)
                if m:
                    val = float(m.group(1))
                    if 0 < val <= 5:
                        rating = val

            count_el = card.query_selector("span[class*='count'], span[class*='Count']")
            if count_el:
                ct = count_el.inner_text().strip().replace(",", "")
                m = re.search(r'(\d+)', ct)
                if m:
                    rating_count = int(m.group(1))

            discount_type = f"{int(discount_percent)}% off" if discount_percent else None

            deals.append(DealItem(
                title=title,
                brand=brand or extract_brand(title),
                discountType=discount_type,
                discountPercent=discount_percent,
                price=price,
                originalPrice=original_price,
                category="Fashion",
                images=images,
                platformName="Myntra",
                platformLink=link,
                rating=rating,
                ratingCount=rating_count,
                noCostEMI=False,
                affiliateUrl=link or "#",
            ))
        except Exception as e:
            print(f"[Myntra] DOM card parse error: {e}")
            continue

    return deals


# ---------------------------------------------------------------------------
# Phase 3: Trending searches fallback
# ---------------------------------------------------------------------------

def _get_trending_searches(page) -> list[str]:
    """Discover trending search terms from Myntra using the browser session.

    Uses the already-authenticated browser to access trending APIs
    and extract search suggestions.
    """
    terms: list[str] = []

    # Strategy 1: Navigate to homepage and extract trending from DOM/JS
    try:
        page.goto("https://www.myntra.com", timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        content = page.content()

        # Extract trending terms from embedded JSON in the page
        trending_patterns = [
            r'"trendingSearches"\s*:\s*(\[.+?\])',
            r'"popularSearches"\s*:\s*(\[.+?\])',
            r'"topSearches"\s*:\s*(\[.+?\])',
            r'"recentSearches"\s*:\s*(\[.+?\])',
        ]
        for pat in trending_patterns:
            m = re.search(pat, content, re.DOTALL)
            if m:
                try:
                    items = json.loads(m.group(1))
                    for item in items[:10]:
                        if isinstance(item, str) and len(item) > 2:
                            terms.append(item)
                        elif isinstance(item, dict):
                            term = (
                                item.get("query")
                                or item.get("name")
                                or item.get("keyword")
                                or item.get("title", "")
                            )
                            if term and len(term) > 2:
                                terms.append(term)
                    if terms:
                        print(f"[Myntra] Extracted {len(terms)} trending terms from homepage")
                        break
                except json.JSONDecodeError:
                    continue

        # Strategy 2: Click on search bar to trigger suggestions dropdown
        if not terms:
            try:
                search_input = (
                    page.query_selector("input[class*='search']")
                    or page.query_selector("input[placeholder*='search' i]")
                    or page.query_selector("input[type='search']")
                    or page.query_selector("input[name='q']")
                )
                if search_input:
                    search_input.click()
                    page.wait_for_timeout(2000)

                    # Look for suggestion elements
                    suggestions = page.query_selector_all(
                        "a[class*='suggest'], "
                        "li[class*='suggest'], "
                        "div[class*='suggest'] a, "
                        "div[class*='trending'] a, "
                        "ul[class*='suggest'] li"
                    )
                    for sug in suggestions[:10]:
                        text = sug.inner_text().strip()
                        if text and len(text) > 2:
                            terms.append(text)

                    if terms:
                        print(f"[Myntra] Extracted {len(terms)} terms from search suggestions")

            except Exception as e:
                print(f"[Myntra] Search suggestion extraction error: {e}")

        # Strategy 3: Extract category names from nav menu
        if not terms:
            try:
                nav_links = page.query_selector_all(
                    "a[class*='desktop-categoryName'], "
                    "a[data-reactid] span, "
                    "nav a[href*='/']"
                )
                for link in nav_links[:20]:
                    href = link.get_attribute("href")
                    if href:
                        # Extract the path slug
                        path = href.split("myntra.com/")[-1].split("?")[0].strip("/")
                        if path and _is_listing_path(path) and len(path) > 3:
                            # Convert slug to search term
                            term = path.replace("-", " ")
                            if term not in terms:
                                terms.append(term)

                if terms:
                    print(f"[Myntra] Extracted {len(terms)} terms from nav menu")

            except Exception as e:
                print(f"[Myntra] Nav extraction error: {e}")

    except Exception as e:
        print(f"[Myntra] Trending search discovery error: {e}")

    # Last resort fallback
    if not terms:
        print("[Myntra] No trending terms found, using broad fallback")
        terms = ["tshirts", "shoes", "dresses", "kurtas", "watches",
                 "jeans", "sarees", "sneakers", "bags", "sunglasses"]

    return terms[:10]


# ---------------------------------------------------------------------------
# Product parser
# ---------------------------------------------------------------------------

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

        # Category — try multiple API fields, then map
        raw_cat = ""
        for field in ("masterCategory", "articleType", "subCategory", "category"):
            val = p.get(field)
            if isinstance(val, dict):
                raw_cat = val.get("typeName", "") or val.get("name", "")
            elif isinstance(val, str):
                raw_cat = val
            if raw_cat:
                break
        category = _MYNTRA_CATEGORY_MAP.get(raw_cat, raw_cat or "Fashion")

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
            noCostEMI=False,
            affiliateUrl=link or "#",
        )
    except Exception as e:
        print(f"[Myntra] Product parse error: {e}")
        return None