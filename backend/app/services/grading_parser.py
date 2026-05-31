import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

GRADE_NUMBER_RE = re.compile(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.[05])?)(?!\d)")
GRADE_RANGE_RE = re.compile(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.[05])?)\s*(?:-|to)\s*(10(?:\.0)?|[0-9](?:\.[05])?)(?!\d)", re.IGNORECASE)

TEXT_GRADE_DEFAULTS = [
    (("gem", "mint"), 10.0, "Gem Mint"),
    (("pristine",), 10.0, "Gem Mint"),
    (("near", "mint"), 9.0, "Near Mint"),
    (("nm",), 9.0, "Near Mint"),
    (("mint",), 9.5, "Mint"),
    (("excellent", "mint"), 7.0, "Excellent"),
    (("ex",), 7.0, "Excellent"),
    (("excellent",), 7.0, "Excellent"),
    (("lightly", "played"), 6.0, "Lightly Played"),
    (("very", "good"), 5.0, "Very Good"),
    (("vg",), 5.0, "Very Good"),
    (("good",), 3.0, "Good"),
    (("poor",), 1.0, "Poor"),
]

SCORE_LABELS = [
    (10.0, "Gem Mint"),
    (9.5, "Mint"),
    (9.0, "Near Mint"),
    (7.0, "Excellent"),
    (5.0, "Very Good"),
    (3.0, "Good"),
    (1.0, "Poor"),
]


def _clamp_grade(value: float) -> float | None:
    if value < 1 or value > 10:
        return None
    return round(value, 2)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def label_for_score(score: float | None) -> str:
    if score is None:
        return ""
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return "Poor"


def parse_grade_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _clamp_grade(float(value))
    if isinstance(value, dict):
        for key in ("score", "grade", "value", "estimated_grade", "overall_score"):
            parsed = parse_grade_value(value.get(key))
            if parsed is not None:
                return parsed
        return parse_grade_value(_stringify(value))

    text = _stringify(value).strip()
    if not text:
        return None
    match = GRADE_NUMBER_RE.search(text.replace(",", "."))
    if match:
        return _clamp_grade(float(match.group(1)))

    lowered = text.lower()
    for tokens, score, _label in TEXT_GRADE_DEFAULTS:
        if all(token in lowered for token in tokens):
            return score
    return None


def parse_grade_label(value: Any, score: float | None = None) -> str:
    if isinstance(value, dict):
        label = value.get("label") or value.get("condition") or value.get("text")
        if label:
            return str(label)
    text = _stringify(value).strip() if value is not None else ""
    lowered = text.lower()
    for tokens, _score, label in TEXT_GRADE_DEFAULTS:
        if all(token in lowered for token in tokens):
            return label
    return label_for_score(score)


def parse_grade_range(value: Any, fallback_score: float | None = None) -> tuple[str | None, str | None, list[str]]:
    warnings: list[str] = []
    if isinstance(value, dict):
        low = parse_grade_value(value.get("low") or value.get("min") or value.get("estimated_grade_low"))
        high = parse_grade_value(value.get("high") or value.get("max") or value.get("estimated_grade_high"))
        if low is not None or high is not None:
            low = low if low is not None else high
            high = high if high is not None else low
            return str(low), str(high), warnings

    text = _stringify(value).strip() if value is not None else ""
    if text:
        range_text = text.replace(",", ".").replace(chr(8211), "-").replace(chr(8212), "-")
        match = GRADE_RANGE_RE.search(range_text)
        if match:
            return str(_clamp_grade(float(match.group(1)))), str(_clamp_grade(float(match.group(2)))), warnings
        single = parse_grade_value(text)
        if single is not None:
            return str(single), str(single), warnings
        warnings.append(f"Could not parse grade_range={text[:120]}")

    if fallback_score is not None:
        return str(fallback_score), str(fallback_score), warnings
    return None, None, warnings


def normalize_subgrade(key: str, value: Any, warnings: list[str]) -> dict[str, Any]:
    score = parse_grade_value(value)
    label = parse_grade_label(value, score)
    reason = str(value.get("reason") or value.get("notes") or "") if isinstance(value, dict) else ""
    if isinstance(value, str) and score is not None and not GRADE_NUMBER_RE.search(value):
        warnings.append(f"AI returned textual subgrade; normalized {value} -> {score}")
    if score is None and value not in (None, ""):
        warnings.append(f"Could not parse subgrade {key}={_stringify(value)[:80]}")
    return {"score": score, "label": label, "reason": reason}


def normalize_final_grading_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    warnings: list[str] = list(result.get("parsing_warnings") or [])
    raw_subgrades = result.get("subgrades") if isinstance(result.get("subgrades"), dict) else {}
    if not raw_subgrades and isinstance(result.get("subscores"), dict):
        raw_subgrades = result["subscores"]

    overall = parse_grade_value(
        result.get("overall_score")
        or result.get("estimated_grade")
        or result.get("estimated_grade_label")
        or result.get("grade")
        or result.get("final_grade")
        or result
    )
    if overall is None:
        warnings.append("Could not parse overall score from AI grading result.")
    else:
        normalized["overall_score"] = overall
        normalized["estimated_grade"] = str(overall)
        normalized.setdefault("estimated_grade_label", parse_grade_label(result.get("estimated_grade_label") or result.get("estimated_grade"), overall))

    low, high, range_warnings = parse_grade_range(result.get("grade_range"), overall)
    warnings.extend(range_warnings)
    if low is not None or high is not None:
        range_min = float(low or high)
        range_max = float(high or low)
        normalized["grade_range"] = {
            "min": range_min,
            "max": range_max,
            "label": f"{range_min} - {range_max}",
        }
        normalized["parsed_grade_range"] = {"low": str(range_min), "high": str(range_max)}

    normalized_subgrades: dict[str, dict[str, Any]] = {}
    parsed_subgrades: dict[str, float | None] = {}
    for key in ("centering", "corners", "edges", "surface"):
        subgrade = normalize_subgrade(key, raw_subgrades.get(key), warnings)
        normalized_subgrades[key] = subgrade
        parsed_subgrades[key] = subgrade["score"]
    normalized["subgrades"] = normalized_subgrades
    normalized["parsed_subgrades"] = parsed_subgrades
    if warnings:
        normalized["parsing_warnings"] = warnings
        logger.warning("AI grading parse warnings: %s", warnings)
    return normalized
