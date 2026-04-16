from __future__ import annotations

from research_mcp.utils import tokenize


SBI_DETECTOR_TERMS = {
    "sbi",
    "simulation",
    "based",
    "inference",
    "posterior",
    "calibration",
    "calibrations",
    "coverage",
    "amortized",
    "likelihood",
    "free",
}

SBI_PHRASES = [
    "simulation-based inference",
    "simulation based inference",
    "neural posterior estimation",
    "posterior calibration",
    "simulation-based calibration",
    "coverage calibration",
    "expected coverage",
    "amortized inference",
    "likelihood-free inference",
]


def expand_search_query(query: str) -> str:
    """Return a provider-friendly expanded query for high-value SBI searches."""
    normalized = " ".join(query.split())
    if not normalized or not is_sbi_calibration_query(normalized):
        return normalized
    lower = normalized.lower()
    additions = [phrase for phrase in SBI_PHRASES if phrase not in lower]
    # Keep the expanded query compact; some providers degrade with very long search strings.
    return " ".join([normalized, *additions[:4]])


def is_sbi_calibration_query(query: str) -> bool:
    tokens = set(tokenize(query))
    if not tokens:
        return False
    has_inference = {"sbi", "inference", "posterior", "likelihood"} & tokens
    has_calibration = {"calibration", "calibrations", "coverage", "calibrating", "calibrated"} & tokens
    has_simulation = {"simulation", "simulator", "simulations"} & tokens or "simulation-based" in query.lower()
    return bool(has_calibration and (has_inference or has_simulation))


def domain_phrase_hits(text: str) -> int:
    lower = text.lower()
    return sum(1 for phrase in SBI_PHRASES if phrase in lower)
