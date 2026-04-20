from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from research_mcp.query_expansion import is_sbi_calibration_query


@dataclass(frozen=True)
class DomainProfile:
    id: str
    label: str
    description: str
    scope: str = "general"
    is_example: bool = False
    section_weights: dict[str, float] = field(default_factory=dict)
    evidence_markers: tuple[str, ...] = ()
    unsupported_markers: tuple[str, ...] = ()
    risk_markers: tuple[str, ...] = ()
    recommended_topics: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.id

    def to_public_dict(self) -> dict:
        payload = asdict(self)
        payload["name"] = self.id
        return payload


@dataclass(frozen=True)
class ResolvedDomainProfile:
    requested_profile: str
    resolved_profile: DomainProfile
    profile_source: Literal["explicit", "auto", "fallback"]


GENERAL_PROFILE = DomainProfile(
    id="general",
    label="General",
    description="Default all-domain synthesis profile. It does not assume a specific scientific field.",
    scope="all-domain",
    section_weights={
        "abstract": 0.08,
        "introduction": 0.04,
        "method": 0.08,
        "results": 0.06,
        "conclusion": 0.04,
        "body": 0.02,
    },
    evidence_markers=("method", "experiment", "result", "limitation", "assumption", "conclusion"),
    unsupported_markers=("not explicit", "manual inspection", "manual verification", "not clearly"),
    risk_markers=("limitation", "bias", "failure", "not explicit"),
    recommended_topics=("general literature synthesis", "cross-paper comparison", "method review"),
)

SBI_CALIBRATION_PROFILE = DomainProfile(
    id="sbi_calibration",
    label="SBI calibration example",
    description="Example preset for simulation-based inference calibration evidence extraction. It is not the default Scibudy scope.",
    scope="example:preset",
    is_example=True,
    section_weights={
        "abstract": 0.10,
        "introduction": 0.04,
        "method": 0.14,
        "results": 0.12,
        "conclusion": 0.05,
        "body": 0.04,
    },
    evidence_markers=(
        "calibration",
        "coverage",
        "rank",
        "posterior",
        "simulation",
        "benchmark",
        "misspecification",
        "diagnostic",
        "failure",
        "bias",
    ),
    unsupported_markers=("not explicit", "manual inspection", "manual verification", "not clearly"),
    risk_markers=("misspecification", "bias", "poor coverage", "failure", "mismatch"),
    recommended_topics=(
        "calibration in simulation-based inference",
        "posterior coverage diagnostics",
        "simulation-based calibration",
    ),
)


PROFILES = {
    GENERAL_PROFILE.id: GENERAL_PROFILE,
    SBI_CALIBRATION_PROFILE.id: SBI_CALIBRATION_PROFILE,
}


def profile_choices() -> list[str]:
    return ["auto", *PROFILES.keys()]


def list_domain_profiles() -> list[dict]:
    return [
        {
            "id": "auto",
            "name": "auto",
            "label": "Auto",
            "description": "Automatically selects a synthesis profile from the topic while preserving general all-domain search.",
            "scope": "resolver",
            "is_example": False,
            "recommended_topics": (),
        },
        *[profile.to_public_dict() for profile in PROFILES.values()],
    ]


def resolve_domain_profile(profile: str | None, topic: str | None = None) -> ResolvedDomainProfile:
    requested = (profile or "auto").strip().lower()
    if requested == "auto":
        resolved = SBI_CALIBRATION_PROFILE if topic and is_sbi_calibration_query(topic) else GENERAL_PROFILE
        return ResolvedDomainProfile(requested_profile="auto", resolved_profile=resolved, profile_source="auto")
    if requested in PROFILES:
        return ResolvedDomainProfile(requested_profile=requested, resolved_profile=PROFILES[requested], profile_source="explicit")
    return ResolvedDomainProfile(requested_profile=requested, resolved_profile=GENERAL_PROFILE, profile_source="fallback")
