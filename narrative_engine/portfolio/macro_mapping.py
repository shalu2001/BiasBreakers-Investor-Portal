"""Helpers for LLM-assisted macro-to-stock mapping (vendored unchanged).

The macro-mapping stage takes a macro narrative view, a sector-aware ticker universe, and
optional article/context hints, then asks an LLM to produce a structured basket of tickers
and weights that can be fed into the Black-Litterman override path.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from math import isclose
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickerInfoRecord:
    """Normalized Ticker_Info record used to guide macro mapping."""

    ticker: str
    company: str
    sector: str
    industry: str
    sub_sector: str


def _normalize_whitespace(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_ticker(value: object) -> str:
    """Normalize ticker-like values to a comparable symbol."""

    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _first_non_empty_value(document: Mapping[str, Any], candidates: Sequence[str]) -> str:
    for candidate in candidates:
        value = document.get(candidate)
        if isinstance(value, str) and value.strip():
            return _normalize_whitespace(value)
        if value not in (None, ""):
            return _normalize_whitespace(value)
    return ""


def normalize_ticker_info_documents(documents: Iterable[Mapping[str, Any]]) -> List[TickerInfoRecord]:
    """Convert raw Ticker_Info documents into a normalized in-memory universe."""

    records: List[TickerInfoRecord] = []
    for document in documents:
        ticker = _first_non_empty_value(
            document,
            [
                "ticker",
                "Ticker",
                "symbol",
                "Symbol",
                "CSE Ticker",
                "CSE code",
                "cseCode",
                "cse_symbol",
            ],
        )
        company = _first_non_empty_value(
            document,
            ["company", "Company", "name", "NAME", "matched_company_name"],
        )
        sector = _first_non_empty_value(
            document,
            [
                "GICS Sector",
                "sector",
                "Sector",
                "sector_name",
                "Sector Name",
                "industry_sector",
            ],
        )
        industry = _first_non_empty_value(
            document,
            [
                "GICS Industry",
                "GICS Industry Group",
                "industry",
                "Industry",
                "industry_name",
                "Business Sector",
                "category",
            ],
        )
        sub_sector = _first_non_empty_value(
            document,
            [
                "GICS Sub-Industry",
                "GICS Sub Industry",
                "sub_sector",
                "Sub Sector",
                "Sub-Sector",
                "subsector",
                "segment",
            ],
        )

        if not ticker and not company:
            continue

        records.append(
            TickerInfoRecord(
                ticker=normalize_ticker(ticker),
                company=company,
                sector=sector,
                industry=industry,
                sub_sector=sub_sector,
            )
        )

    return records


def _tokenize(text: object) -> set[str]:
    return {token for token in re.findall(r"[A-Za-z0-9]+", str(text or "").lower()) if token}


def _score_candidate(view_text: str, record: TickerInfoRecord) -> float:
    view_tokens = _tokenize(view_text)
    if not view_tokens:
        return 0.0

    score = 0.0
    ticker = record.ticker.lower()
    if ticker and ticker in view_text.lower():
        score += 5.0
    company_tokens = _tokenize(record.company)
    sector_tokens = _tokenize(record.sector)
    industry_tokens = _tokenize(record.industry)
    sub_sector_tokens = _tokenize(record.sub_sector)

    score += 2.5 * len(view_tokens.intersection(company_tokens))
    score += 2.0 * len(view_tokens.intersection(sector_tokens))
    score += 1.5 * len(view_tokens.intersection(industry_tokens))
    score += 1.0 * len(view_tokens.intersection(sub_sector_tokens))

    return score


def select_candidate_records(
    view_text: str,
    records: Sequence[TickerInfoRecord],
    limit: Optional[int] = None,
) -> List[TickerInfoRecord]:
    """Pick the most relevant ticker records for a macro view prompt."""

    ranked = sorted(records, key=lambda record: (_score_candidate(view_text, record), record.ticker), reverse=True)
    if limit is None or limit <= 0:
        return list(ranked)

    selected = [record for record in ranked if _score_candidate(view_text, record) > 0.0]
    if not selected:
        selected = list(ranked)
    return selected[:limit]


def _format_candidate_table(records: Sequence[TickerInfoRecord]) -> str:
    rows = ["ticker | company | sector | industry | sub_sector", "--- | --- | --- | --- | ---"]
    for record in records:
        rows.append(
            " | ".join(
                [
                    record.ticker or "",
                    record.company or "",
                    record.sector or "",
                    record.industry or "",
                    record.sub_sector or "",
                ]
            )
        )
    return "\n".join(rows)


def build_macro_mapping_prompt(
    view: Mapping[str, Any],
    candidate_records: Sequence[TickerInfoRecord],
    max_allocations: int = 20,
) -> Tuple[str, str]:
    """Build the system and user prompt for a single macro view."""

    system_prompt = (
        "You are a portfolio research assistant. Convert a macro narrative view into a "
        "Black-Litterman stock basket using only the provided ticker universe and sector metadata. "
        "Return valid JSON only. Do not invent tickers."
    )
    user_prompt = (
        "Map the macro narrative below into a structured stock basket for a Black-Litterman P row.\n\n"
        f"Macro view: {json.dumps(dict(view), ensure_ascii=False, default=str)}\n\n"
        "Use the candidate ticker universe and sector metadata below. Identify every ticker whose company, sector, "
        "industry, or sub-sector is materially exposed to or represented by the macro narrative.\n\n"
        f"Candidate universe (top {len(candidate_records)}):\n{_format_candidate_table(candidate_records)}\n\n"
        f"Rules:\n"
        f"- Return at most {max_allocations} allocations.\n"
        "- Include ALL tickers that are reasonably and materially related to the narrative. Do not return only the strongest or most obvious matches.\n"
        "- Evaluate every candidate ticker independently against the narrative before deciding whether to include it.\n"
        "- Omit a ticker only if there is insufficient evidence that its business, sector, industry, or sub-sector is meaningfully connected to the narrative.\n"
        "- First decide view_kind, then apply the matching weight rule below. Do not mix them.\n"
        "  - view_kind=\"absolute\": the narrative describes a single directional outcome (a sector benefiting, or a sector "
        "suffering) with no explicit winner-vs-loser pairing. ALL allocations MUST use weight 1.0. Never use -1.0 in an "
        "absolute view. If a ticker would be expected to suffer or underperform, omit it from the allocations entirely "
        "rather than giving it a negative weight — the system only ever applies absolute-view allocations as a long-only "
        "basket, so any negative weight you return here is discarded and silently drops that ticker's economic signal.\n"
        "  - view_kind=\"relative\": the narrative explicitly contrasts winners against losers (e.g. one sector benefiting "
        "at the expense of another). Use weight 1.0 for tickers expected to benefit and weight -1.0 for tickers expected "
        "to suffer or underperform, and include at least one ticker of each sign.\n"
        "- Do not attempt to distribute fractions such as 0.5 or 0.33. Use strictly 1.0 or -1.0.\n"
        "- The system will market-cap weight the basket automatically.\n"
        "- If multiple companies share exposure to the same narrative, include all of them.\n"
        "- If no confident mapping exists, return an empty allocations list.\n\n"
        "Return JSON with this shape:\n"
        "{\n"
        '  "view_id": "<same view_id>",\n'
        '  "view_kind": "absolute",\n'
        '  "allocations": [\n'
        '    {"ticker": "JKH", "weight": 1.0},\n'
        '    {"ticker": "HNB", "weight": 1.0}\n'
        "  ],\n"
        '  "rationale": "short explanation"\n'
        "}"
    )
    return system_prompt, user_prompt


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_macro_mapping_response(content: str) -> Dict[str, Any]:
    """Parse an LLM response into a validated macro mapping payload."""

    cleaned = _strip_code_fences(content)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Macro mapping response must be a JSON object.")

    view_id = str(payload.get("view_id", "")).strip()
    if not view_id:
        raise ValueError("Macro mapping response missing 'view_id'.")

    raw_view_kind = str(payload.get("view_kind", "absolute")).strip().lower()
    view_kind = raw_view_kind if raw_view_kind in {"absolute", "relative"} else "absolute"

    allocations = payload.get("allocations", [])
    if not isinstance(allocations, list):
        raise ValueError("Macro mapping response field 'allocations' must be a list.")

    normalized_allocations: List[Tuple[str, float]] = []
    seen: set[str] = set()
    for allocation in allocations:
        if not isinstance(allocation, dict):
            continue
        ticker = normalize_ticker(allocation.get("ticker"))
        if not ticker or ticker in seen:
            continue
        try:
            weight = float(allocation.get("weight"))
        except (TypeError, ValueError):
            continue
        if weight == 0.0:
            continue
        normalized_allocations.append((ticker, weight))
        seen.add(ticker)

    rationale = str(payload.get("rationale", "")).strip()
    return {
        "view_id": view_id,
        "view_kind": view_kind,
        "allocations": normalized_allocations,
        "rationale": rationale,
    }


def infer_macro_view_kind(view: Mapping[str, Any]) -> str:
    """Heuristically infer whether a macro view is absolute or relative."""

    text = " ".join(
        [
            str(view.get("topic_name", "")),
            str(view.get("Si", "")),
            str(view.get("Qi", "")),
            str(view.get("description", "")),
        ]
    ).lower()
    relative_markers = [
        "outperform",
        "underperform",
        "versus",
        "vs",
        "relative",
        "compared",
        "compares",
        "beats",
        "lags",
        "better than",
        "worse than",
    ]
    if any(marker in text for marker in relative_markers):
        return "relative"
    return "absolute"


def _equal_weight_allocations(allocations: Sequence[Tuple[str, float]], sign: float = 1.0) -> List[Tuple[str, float]]:
    filtered = [normalize_ticker(ticker) for ticker, weight in allocations if normalize_ticker(ticker) and float(weight) != 0.0]
    if not filtered:
        return []
    weight = sign / len(filtered)
    return [(ticker, weight) for ticker in filtered]


def normalize_macro_allocations_cap_weighted(
    allocations: Sequence[Tuple[str, float]],
    view_kind: str,
    mcap_dict: Mapping[str, float],
) -> List[Tuple[str, float]]:
    """Normalize LLM directional outputs into market-cap weighted BL rows."""

    cleaned = [
        (normalize_ticker(ticker), float(weight))
        for ticker, weight in allocations
        if normalize_ticker(ticker) and float(weight) != 0.0
    ]
    if not cleaned:
        return []

    view_kind = (view_kind or "absolute").strip().lower()

    if view_kind != "relative":
        positives = [ticker for ticker, weight in cleaned if weight > 0.0]
        if not positives:
            return []

        total_mcap = sum(float(mcap_dict.get(ticker, 0.0)) for ticker in positives)
        if total_mcap <= 0.0:
            return _equal_weight_allocations([(ticker, 1.0) for ticker in positives], sign=1.0)

        return [(ticker, float(mcap_dict.get(ticker, 0.0)) / total_mcap) for ticker in positives]

    positives = [ticker for ticker, weight in cleaned if weight > 0.0]
    negatives = [ticker for ticker, weight in cleaned if weight < 0.0]
    if not positives or not negatives:
        return []

    pos_mcap_total = sum(float(mcap_dict.get(ticker, 0.0)) for ticker in positives)
    neg_mcap_total = sum(float(mcap_dict.get(ticker, 0.0)) for ticker in negatives)

    normalized: List[Tuple[str, float]] = []
    if pos_mcap_total > 0.0:
        normalized.extend((ticker, float(mcap_dict.get(ticker, 0.0)) / pos_mcap_total) for ticker in positives)
    else:
        normalized.extend(_equal_weight_allocations([(ticker, 1.0) for ticker in positives], sign=1.0))

    if neg_mcap_total > 0.0:
        normalized.extend((ticker, -(float(mcap_dict.get(ticker, 0.0)) / neg_mcap_total)) for ticker in negatives)
    else:
        normalized.extend(_equal_weight_allocations([(ticker, -1.0) for ticker in negatives], sign=-1.0))

    total = sum(weight for _, weight in normalized)
    if not isclose(total, 0.0, abs_tol=1e-9) and normalized:
        last_ticker, last_weight = normalized[-1]
        normalized[-1] = (last_ticker, last_weight - total)
    return normalized


def normalize_macro_allocations(
    allocations: Sequence[Tuple[str, float]],
    view_kind: str,
    mcap_dict: Optional[Mapping[str, float]] = None,
) -> List[Tuple[str, float]]:
    """Normalize the LLM output to the BL semantics for the given view kind."""

    if mcap_dict is not None:
        return normalize_macro_allocations_cap_weighted(allocations, view_kind, mcap_dict)

    cleaned = [(normalize_ticker(ticker), float(weight)) for ticker, weight in allocations if normalize_ticker(ticker) and float(weight) != 0.0]
    if not cleaned:
        return []

    view_kind = (view_kind or "absolute").strip().lower()
    if view_kind != "relative":
        positive_only = [(ticker, weight) for ticker, weight in cleaned if weight > 0.0]
        total = sum(weight for _, weight in positive_only)
        if total <= 0.0:
            return []
        return [(ticker, weight / total) for ticker, weight in positive_only]

    positives = [(ticker, weight) for ticker, weight in cleaned if weight > 0.0]
    negatives = [(ticker, weight) for ticker, weight in cleaned if weight < 0.0]
    if positives and negatives:
        pos_total = sum(weight for _, weight in positives)
        neg_total = sum(abs(weight) for _, weight in negatives)
        normalized: List[Tuple[str, float]] = []
        if pos_total > 0.0:
            normalized.extend((ticker, weight / pos_total) for ticker, weight in positives)
        if neg_total > 0.0:
            normalized.extend((ticker, -(abs(weight) / neg_total)) for ticker, weight in negatives)
        if isclose(sum(weight for _, weight in normalized), 0.0, abs_tol=1e-9):
            return normalized

    mean_weight = sum(weight for _, weight in cleaned) / len(cleaned)
    centered = [(ticker, weight - mean_weight) for ticker, weight in cleaned]
    if all(isclose(weight, 0.0, abs_tol=1e-9) for _, weight in centered):
        return []
    total = sum(weight for _, weight in centered)
    if not isclose(total, 0.0, abs_tol=1e-9):
        centered[-1] = (centered[-1][0], centered[-1][1] - total)
    return centered


def filter_valid_allocations(
    allocations: Sequence[Tuple[str, float]],
    allowed_tickers: Sequence[str],
    max_allocations: int = 6,
) -> List[Tuple[str, float]]:
    """Keep only allocations that belong to the allowed ticker universe."""

    allowed = {normalize_ticker(ticker) for ticker in allowed_tickers if normalize_ticker(ticker)}
    filtered: List[Tuple[str, float]] = []
    seen: set[str] = set()
    for ticker, weight in allocations:
        normalized_ticker = normalize_ticker(ticker)
        if not normalized_ticker or normalized_ticker not in allowed or normalized_ticker in seen:
            continue
        if weight == 0.0:
            continue
        filtered.append((normalized_ticker, float(weight)))
        seen.add(normalized_ticker)
        if len(filtered) >= max_allocations:
            break
    return filtered


def build_overrides_payload(overrides: Mapping[str, Sequence[Tuple[str, float]]]) -> Dict[str, List[List[Any]]]:
    """Convert in-memory overrides into the JSON-friendly payload used by BL."""

    return {
        str(view_id): [[normalize_ticker(ticker), float(weight)] for ticker, weight in allocations]
        for view_id, allocations in overrides.items()
    }
