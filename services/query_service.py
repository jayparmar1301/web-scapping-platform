import re
import requests

# Fallback Hinglish-to-English dictionary
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
    Translates a search string to standard E-commerce English using local Llama 3.2.
    Falls back to a dictionary if Ollama is offline or not installed.
    """
    q_lower = raw_query.lower().strip()
    
    # 1. Try local Ollama SLM (llama3.2)
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": f"You are an Indian e-commerce search assistant. Translate this Hinglish/English search query into standard English keywords that Amazon/Flipkart expect. Respond ONLY with the clean keywords. Do not include quotes, periods, or extra conversational words. Query: {q_lower}",
                "stream": False,
                "options": {
                    "temperature": 0.1
                }
            },
            timeout=5
        )
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            # Clean up potential LLM quotes or formatting
            result = result.replace('"', '').replace("'", "").replace(".", "")
            if result:
                print(f"[QueryService] Successfully translated '{q_lower}' to '{result}' using local Llama 3.2")
                return result.lower()
    except requests.exceptions.RequestException:
        print("[QueryService] Local Ollama is offline or not installed. Using fallback.")
    except Exception as e:
        print(f"[QueryService] General Ollama error: {e}")
        
    # 2. Exact match Hinglish Fallback test
    if q_lower in FALLBACK_HINGLISH_DICT:
        return FALLBACK_HINGLISH_DICT[q_lower]
        
    # 3. General cleanup (remove conversational filler words)
    fillers = [
        "i want a ", "i want ", "i need a ", "i need ",
        "looking for a ", "looking for ", "search for ",
        "show me ", "cheap ", "best ", "good ", "buy "
    ]
    for filler in fillers:
        if q_lower.startswith(filler):
            q_lower = q_lower.replace(filler, "", 1).strip()
            
    # For now, return the cleaned raw query if no translation applies
    return q_lower
