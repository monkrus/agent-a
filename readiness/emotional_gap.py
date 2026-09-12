#!/usr/bin/env python3
"""
emotional_gap.py — Image-to-Text Emotional Gap analysis.

Compares the emotional/sensory impression conveyed by product IMAGES against
what the product TEXT actually says. The gap score measures how much emotional
content is visible to humans (via photos) but invisible to AI shopping agents
(who can only read text).

Steps:
  1. Image emotional extraction (vision API)
  2. Text emotional extraction (text API)
  3. Gap scoring via semantic comparison (text API)

Requires SHOPPER=anthropic and ANTHROPIC_API_KEY. When SHOPPER=mock, callers
should fall back to the keyword-based copy_richness check.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re

# Category emotional dependency scores (1-10).
# Higher = product sells on feeling/experience, images carry more weight.
# Lower = utilitarian product, text specs matter more than mood.
CATEGORY_EMOTIONAL_WEIGHT = {
    "lingerie": 9, "swimwear": 9, "intimates": 9,
    "fashion": 8, "clothing": 8, "apparel": 8, "dresses": 8,
    "jewelry": 8, "accessories": 7, "handbags": 7, "shoes": 7,
    "beauty": 8, "skincare": 7, "fragrance": 9, "cosmetics": 7,
    "home decor": 7, "furniture": 6, "bedding": 7, "candles": 8,
    "food": 6, "beverages": 6, "wine": 7, "spirits": 7,
    "wellness": 7, "fitness": 5, "supplements": 4,
    "electronics": 3, "tech": 3, "gadgets": 3,
    "tools": 2, "hardware": 2, "industrial": 2,
    "toys": 5, "games": 4, "books": 4,
    "pets": 5, "outdoor": 5, "sports": 5,
    "automotive": 3, "office": 2,
}
DEFAULT_EMOTIONAL_WEIGHT = 5

# Per-image result cache (keyed on image URL hash)
_image_cache: dict[str, dict] = {}


def _detect_category(page: dict) -> tuple[str, int]:
    """Detect product category from JSON-LD, meta, or page text.

    Returns (category_name, emotional_weight_1_to_10).
    """
    signals = []

    # JSON-LD category field
    for obj in page.get("jsonld", []):
        if not isinstance(obj, dict):
            continue
        cat = obj.get("category") or obj.get("productType") or ""
        if isinstance(cat, str):
            signals.append(cat.lower())
        elif isinstance(cat, list):
            signals.extend(str(c).lower() for c in cat)

    # og:type / product:category meta
    meta = page.get("meta", {})
    for key in ("product:category", "og:type"):
        v = meta.get(key, "")
        if v:
            signals.append(v.lower())

    # Page text + title (first 500 chars)
    text_blob = ((page.get("title") or "") + " " +
                 (page.get("text") or "")[:500]).lower()

    # Match against known categories
    for signal in signals + [text_blob]:
        for cat, weight in CATEGORY_EMOTIONAL_WEIGHT.items():
            if cat in signal:
                return cat, weight

    return "general", DEFAULT_EMOTIONAL_WEIGHT


def _fetch_image_bytes(url: str, timeout: int = 15) -> bytes | None:
    """Download image bytes. Returns None on failure."""
    try:
        import requests
        r = requests.get(url, timeout=timeout, stream=True,
                         headers={"User-Agent": "agent-a-readiness-scanner/0.1"})
        if r.status_code != 200:
            return None
        # Cap at 5MB
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 5 * 1024 * 1024:
                return None
        return content
    except Exception:
        return None


def _image_media_type(url: str) -> str:
    """Guess media type from URL extension."""
    url_lower = url.lower().split("?")[0]
    if url_lower.endswith(".png"):
        return "image/png"
    if url_lower.endswith(".webp"):
        return "image/webp"
    if url_lower.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def extract_image_emotions(image_urls: list[str], model: str = None) -> dict:
    """Step 1: Extract emotional/sensory tags from product images via vision API.

    Returns:
        {
            "image_emotional_tags": [...],
            "image_emotional_summary": "...",
            "raw_image_refs": [...],
            "images_analyzed": int,
        }
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for emotional gap analysis")

    model = model or os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    # Deduplicate by URL, use cache, limit to 3 images
    urls_to_analyze = []
    cached_tags = []
    for url in image_urls[:3]:
        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in _image_cache:
            cached = _image_cache[cache_key]
            cached_tags.extend(cached.get("tags", []))
        else:
            urls_to_analyze.append(url)

    # Build vision content blocks
    content_blocks = []
    analyzed_refs = []
    for url in urls_to_analyze:
        img_bytes = _fetch_image_bytes(url)
        if not img_bytes:
            continue
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _image_media_type(url),
                "data": b64,
            }
        })
        analyzed_refs.append(url)

    if not content_blocks and not cached_tags:
        return {
            "image_emotional_tags": [],
            "image_emotional_summary": "",
            "raw_image_refs": [],
            "images_analyzed": 0,
        }

    new_tags = []
    new_summary = ""
    if content_blocks:
        content_blocks.append({
            "type": "text",
            "text": (
                "Describe the emotional and sensory impression a human shopper "
                "would get from looking at this product photo. Focus on mood, "
                "feeling, and implied experience (e.g. delicate, intimate, "
                "confident, soft, luxurious, playful, second-skin fit) rather "
                "than literal object description (e.g. 'black lace bra on a "
                "model').\n\n"
                "Return your answer in this exact format:\n"
                "TAGS: tag1, tag2, tag3, tag4, tag5\n"
                "SUMMARY: One to two sentence summary of the overall emotional "
                "impression."
            ),
        })

        msg = client.messages.create(
            model=model, max_tokens=300,
            messages=[{"role": "user", "content": content_blocks}],
        )
        raw = "".join(b.text for b in msg.content
                      if getattr(b, "type", "") == "text").strip()

        # Parse response
        tags_match = re.search(r"TAGS:\s*(.+)", raw, re.I)
        summary_match = re.search(r"SUMMARY:\s*(.+)", raw, re.I | re.DOTALL)
        if tags_match:
            new_tags = [t.strip().lower() for t in tags_match.group(1).split(",")
                        if t.strip()]
        if summary_match:
            new_summary = summary_match.group(1).strip()

        # Cache per image URL
        for url in analyzed_refs:
            cache_key = hashlib.md5(url.encode()).hexdigest()
            _image_cache[cache_key] = {"tags": new_tags}

    all_tags = list(dict.fromkeys(cached_tags + new_tags))  # dedupe, preserve order

    return {
        "image_emotional_tags": all_tags,
        "image_emotional_summary": new_summary,
        "raw_image_refs": analyzed_refs,
        "images_analyzed": len(analyzed_refs) + len(cached_tags) // max(len(new_tags), 1),
    }


def extract_text_emotions(page: dict, model: str = None) -> dict:
    """Step 2: Extract emotional/sensory tags from page text.

    Returns:
        {
            "text_emotional_tags": [...],
            "text_emotional_summary": "...",
        }
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for emotional gap analysis")

    model = model or os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    title = page.get("title", "")
    text = (page.get("text") or "")[:3000]
    description = ""
    for obj in page.get("jsonld", []):
        if isinstance(obj, dict) and obj.get("description"):
            description = str(obj["description"])[:500]
            break

    copy = f"TITLE: {title}\nDESCRIPTION: {description}\nPAGE TEXT:\n{text}"

    msg = client.messages.create(
        model=model, max_tokens=300,
        messages=[{"role": "user", "content": (
            "Extract the emotional and sensory impression conveyed by this "
            "product page TEXT. Focus on mood, feeling, and implied experience "
            "(e.g. delicate, intimate, confident, soft, luxurious, playful) "
            "rather than factual product attributes.\n\n"
            f"{copy}\n\n"
            "Return your answer in this exact format:\n"
            "TAGS: tag1, tag2, tag3, tag4, tag5\n"
            "SUMMARY: One to two sentence summary of emotional content in "
            "the text."
        )}],
    )
    raw = "".join(b.text for b in msg.content
                  if getattr(b, "type", "") == "text").strip()

    tags = []
    summary = ""
    tags_match = re.search(r"TAGS:\s*(.+)", raw, re.I)
    summary_match = re.search(r"SUMMARY:\s*(.+)", raw, re.I | re.DOTALL)
    if tags_match:
        tags = [t.strip().lower() for t in tags_match.group(1).split(",")
                if t.strip()]
    if summary_match:
        summary = summary_match.group(1).strip()

    return {
        "text_emotional_tags": tags,
        "text_emotional_summary": summary,
    }


def compute_gap(image_result: dict, text_result: dict,
                model: str = None) -> dict:
    """Step 4: Compare image emotions vs text emotions, produce gap score.

    Uses an LLM judge call for semantic comparison (not exact string match).

    Returns:
        {
            "gap_score": float (0-1),
            "missing_emotional_concepts": [...],
            "covered_emotional_concepts": [...],
        }
    """
    image_tags = image_result.get("image_emotional_tags", [])
    text_tags = text_result.get("text_emotional_tags", [])

    if not image_tags:
        return {
            "gap_score": 0.0,
            "missing_emotional_concepts": [],
            "covered_emotional_concepts": [],
        }

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for emotional gap analysis")

    model = model or os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    msg = client.messages.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": (
            "Compare these two sets of emotional/sensory tags from the same "
            "product. The IMAGE tags are what a human sees in the photos. "
            "The TEXT tags are what the product copy conveys.\n\n"
            f"IMAGE TAGS: {', '.join(image_tags)}\n"
            f"IMAGE SUMMARY: {image_result.get('image_emotional_summary', '')}\n\n"
            f"TEXT TAGS: {', '.join(text_tags)}\n"
            f"TEXT SUMMARY: {text_result.get('text_emotional_summary', '')}\n\n"
            "For each image tag, determine if the text SEMANTICALLY covers "
            "that concept (exact words not required — 'soft' and 'gentle' "
            "are a match, 'luxurious' and 'premium quality' are a match).\n\n"
            "Return your answer in this exact format:\n"
            "COVERED: tag1, tag2\n"
            "MISSING: tag3, tag4\n"
            "GAP_SCORE: 0.X\n\n"
            "GAP_SCORE is 0.0 if text fully represents image emotions, "
            "1.0 if text conveys none of them."
        )}],
    )
    raw = "".join(b.text for b in msg.content
                  if getattr(b, "type", "") == "text").strip()

    covered = []
    missing = []
    gap_score = 0.5  # default if parsing fails

    covered_match = re.search(r"COVERED:\s*(.+)", raw, re.I)
    missing_match = re.search(r"MISSING:\s*(.+)", raw, re.I)
    gap_match = re.search(r"GAP_SCORE:\s*([\d.]+)", raw, re.I)

    if covered_match:
        val = covered_match.group(1).strip()
        if val.lower() not in ("none", "n/a", ""):
            covered = [t.strip().lower() for t in val.split(",") if t.strip()]
    if missing_match:
        val = missing_match.group(1).strip()
        if val.lower() not in ("none", "n/a", ""):
            missing = [t.strip().lower() for t in val.split(",") if t.strip()]
    if gap_match:
        try:
            gap_score = max(0.0, min(1.0, float(gap_match.group(1))))
        except ValueError:
            pass

    return {
        "gap_score": gap_score,
        "missing_emotional_concepts": missing,
        "covered_emotional_concepts": covered,
    }


def analyze_emotional_gap(page: dict) -> dict:
    """Run the full emotional gap analysis pipeline (Steps 1-5).

    Returns the complete result dict with gap_score, weighted_gap_score,
    category info, and all intermediate results.
    """
    images = page.get("images", [])
    if not images:
        return {
            "gap_score": None,
            "weighted_gap_score": None,
            "detail": "No product images found on page.",
            "category": None,
            "category_weight": None,
        }

    category, cat_weight = _detect_category(page)
    image_result = extract_image_emotions(images)
    text_result = extract_text_emotions(page)
    gap_result = compute_gap(image_result, text_result)

    gap_score = gap_result["gap_score"]
    weighted_gap_score = gap_score * (cat_weight / 10)

    return {
        "gap_score": gap_score,
        "weighted_gap_score": weighted_gap_score,
        "category": category,
        "category_weight": cat_weight,
        "missing_emotional_concepts": gap_result["missing_emotional_concepts"],
        "covered_emotional_concepts": gap_result["covered_emotional_concepts"],
        "image_emotional_tags": image_result["image_emotional_tags"],
        "image_emotional_summary": image_result.get("image_emotional_summary", ""),
        "text_emotional_tags": text_result["text_emotional_tags"],
        "text_emotional_summary": text_result.get("text_emotional_summary", ""),
        "images_analyzed": image_result.get("images_analyzed", 0),
        "raw_image_refs": image_result.get("raw_image_refs", []),
    }
