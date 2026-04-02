import re

# Fallback Hinglish-to-English dictionary since we don't have LLM access yet
FALLBACK_HINGLISH_DICT = {
    "kala but": "black shoes",
    "kale joote": "black shoes",
    "kala joota": "black shoes",
    "sasta phone": "budget smartphone",
    "sasta mobile": "budget smartphone",
    "safed shirt": "white shirt",
    "lal ghadi": "red watch",
    "chasma": "sunglasses",
    "kala chasma": "black sunglasses",
}

def normalize_query(raw_query: str) -> str:
    """
    Simulates an LLM normalizing a search string to standard E-commerce English.
    In the real implementation, this would call OpenAI, Gemini or Groq APIs.
    """
    q_lower = raw_query.lower().strip()
    
    # 1. Exact match Hinglish Fallback test
    if q_lower in FALLBACK_HINGLISH_DICT:
        return FALLBACK_HINGLISH_DICT[q_lower]
        
    # 2. General cleanup (remove conversational filler words)
    fillers = [
        "i want a ", "i want ", "i need a ", "i need ",
        "looking for a ", "looking for ", "search for ",
        "show me ", "cheap ", "best ", "good "
    ]
    for filler in fillers:
        if q_lower.startswith(filler):
            q_lower = q_lower.replace(filler, "", 1).strip()
            
    # For now, return the cleaned raw query if no translation applies
    return q_lower
