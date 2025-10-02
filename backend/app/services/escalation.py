def detect_emergency_keywords(text: str) -> bool:
    t = text.lower()
    keywords = [
        "blowout",
        "accident",
        "crash",
        "hit",
        "medical",
        "chest pain",
        "ambulance",
        "bleeding",
        "i need help",
        "pulling over",
        "smoke",
    ]
    return any(k in t for k in keywords)
