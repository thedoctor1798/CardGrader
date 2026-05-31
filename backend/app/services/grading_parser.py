import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

GRADE_NUMBER_RE = re.compile(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.[05])?)(?!\d)")
GRADE_RANGE_RE = re.compile(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.[05])?)\s*(?:-|to)\s*(10(?:\.0)?|[0-9](?:\.[05])?)(?!\d)", re.IGNORECASE)

TEXT_GRADE_DEFAULTS = [
    (("gem", "mint"), 10.0),
    (("pristine",), 10.0),
    (("near", "mint"), 9.0),
    (("nm",), 9.0),
    (("mint",), 9.0),
    (("excellent", "mint"), 7.0),
    (("lightly", "played"), 6.0),
    (("excellent",), 6.0),
    (("very", "good"), 4.0),
    (("good",), 3.0),
    (("poor",), 1.0),
]


def _clamp_grade(value: float) -> float | None:
    if value < 0 or value > 10:
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
    for tokens, score in TEXT_GRADE_DEFAULTS:
        if all(token in lowered for token in tokens):
            return score
    return None


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


def normalize_final_grading_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    warnings: list[str] = list(result.get("parsing_warnings") or [])
    subgrades = result.get("subgrades") if isinstance(result.get("subgrades"), dict) else {}
    if not subgrades and isinstance(result.get("subscores"), dict):
        subgrades = result["subscores"]
        normalized["subgrades"] = subgrades

    overall = parse_grade_value(
        result.get("overall_score")
        or result.get("estimated_grade")
        or result.get("grade")
        or result.get("final_grade")
        or result
    )
    if overall is None:
        warnings.append("Could not parse overall score from AI grading result.")
    else:
        normalized["overall_score"] = overall
        normalized.setdefault("estimated_grade", str(overall))

    low, high, range_warnings = parse_grade_range(result.get("grade_range"), overall)
    warnings.extend(range_warnings)
    if low is not None or high is not None:
        normalized["grade_range"] = f"{low or high} - {high or low}"
        normalized["parsed_grade_range"] = {"low": low or high, "high": high or low}

    parsed_subgrades: dict[str, float | None] = {}
    for key in ("centering", "corners", "edges", "surface"):
        parsed = parse_grade_value(subgrades.get(key))
        parsed_subgrades[key] = parsed
        if subgrades.get(key) not in (None, "") and parsed is None:
            warnings.append(f"Could not parse subgrade {key}={_stringify(subgrades.get(key))[:80]}")
    normalized["parsed_subgrades"] = parsed_subgrades
    if warnings:
        normalized["parsing_warnings"] = warnings
        logger.warning("AI grading parse warnings: %s", warnings)
    return normalized
