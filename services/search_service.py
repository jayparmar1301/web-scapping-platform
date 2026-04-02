import concurrent.futures
from scrapers import amazon, flipkart, myntra
from services.query_service import normalize_query

def search_across_platforms(raw_query: str, limit_per_platform: int = 10):
    """
    Normalizes the query and performs a concurrent live search across
    Amazon, Flipkart, and Myntra.
    """
    query = normalize_query(raw_query)
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_amazon = executor.submit(amazon.search_products, query, limit_per_platform)
        f_flipkart = executor.submit(flipkart.search_products, query, limit_per_platform)
        f_myntra = executor.submit(myntra.search_products, query, limit_per_platform)

        # Retrieve results
        for f in [f_amazon, f_flipkart, f_myntra]:
            try:
                res = f.result()
                if res:
                    # DealItems are Pydantic models, we convert them to dict
                    results.extend([r.model_dump() if hasattr(r, 'model_dump') else r.dict() if hasattr(r, 'dict') else r for r in res])
            except Exception as e:
                print(f"Error in concurrent scraper completion: {e}")

    # Sort results by discount percentage descending
    results.sort(key=lambda x: x.get('discountPercent') or 0, reverse=True)
    return results
