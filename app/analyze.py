"""Client for the model's POST /analyze (vision side, port 8001).

Contract (brief v2): multipart `photo` + `comment` ->
{"relevant": "accept|review|reject", "score": 0.92, "hint": "snow|blocked|ice|icicles|unknown", "note": "..."}
No answer within 10 s -> review. While ANALYZE_URL is empty a stub answers accept.
"""
import httpx

HINTS = {"snow", "blocked", "ice", "icicles", "unknown"}
SOURCES = {"photo", "screenshot", "webcam", "stock", "screen"}


def analyze(url: str, timeout: float, photo: bytes, filename: str, content_type: str, comment: str) -> dict:
    if not url:
        return {"relevant": "accept", "score": None, "hint": "unknown", "note": "stub: /analyze not connected"}
    try:
        resp = httpx.post(url, files={"photo": (filename or "photo.jpg", photo, content_type or "image/jpeg")},
                          data={"comment": comment or ""}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"relevant": "review", "score": None, "hint": "unknown",
                "note": f"analyze unavailable ({type(exc).__name__}), sent to inspector"}
    relevant = data.get("relevant")
    if relevant not in ("accept", "review", "reject"):
        relevant = "review"
    hint = data.get("hint") if data.get("hint") in HINTS else "unknown"
    score = data.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    note = str(data.get("note") or "")[:300]
    out = {"relevant": relevant, "score": score, "hint": hint, "note": note}
    if data.get("source") in SOURCES:  # optional: photo | screenshot | webcam | stock | screen
        out["source"] = data["source"]
    return out
