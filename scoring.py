"""Deterministic scoring for VCScore.

The LLM gathers FINDINGS (each: claim, source_url, sign, severity). The verify
step marks which findings have a source that actually supports them. THIS module
turns the verified findings into numbers. It never calls a model, and it never
invents signal: a dimension with zero verified findings is `unknown`, not zero.

If too few dimensions are known, there is no composite at all — the caller
renders an incident timeline instead (mode == "timeline").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).with_name("rubric.yaml")

SIGN_VALUE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


def load_rubric(path: Path = RUBRIC_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@dataclass
class Finding:
    dimension: str
    claim: str
    source_url: str
    sign: str            # positive | negative | neutral (re: founder-friendliness)
    severity: int        # 1-3
    verified: bool | None = None

    @property
    def signed_weight(self) -> float:
        return SIGN_VALUE.get(self.sign, 0.0) * max(1, min(3, int(self.severity or 1)))


@dataclass
class DimResult:
    key: str
    title: str
    weight: float
    known: bool
    score: float | None             # 0-10, None if unknown
    verified_findings: list[Finding] = field(default_factory=list)
    overridden: bool = False


@dataclass
class FirmResult:
    firm: str
    as_of: str
    mode: str                       # "scorecard" | "timeline"
    dims: list[DimResult]
    composite: float | None         # 0-100, None in timeline mode
    band_label: str | None
    band_note: str | None
    known_count: int
    min_known: int
    flags: list[DimResult] = field(default_factory=list)
    unverified: list[Finding] = field(default_factory=list)
    scale_max: int = 10

    def dim(self, key: str) -> DimResult | None:
        return next((d for d in self.dims if d.key == key), None)


def _coerce_override(value, scale_max: int) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(scale_max), float(value)))
    except (TypeError, ValueError):
        return None


def _band(score: float, bands: list[dict]) -> tuple[str, str]:
    for b in sorted(bands, key=lambda x: -x["min"]):
        if score >= b["min"]:
            return b["label"], b["note"]
    return bands[-1]["label"], bands[-1]["note"]


def _parse_findings(profile: dict) -> tuple[dict[str, list[Finding]], list[Finding]]:
    """Return (verified-by-dimension, all-unverified). Accepts findings either
    grouped under `findings: {dim: [...]}` or flat under `findings: [...]`."""
    by_dim: dict[str, list[Finding]] = {}
    unverified: list[Finding] = []
    raw = profile.get("findings") or {}

    def add(dim: str, item: dict):
        f = Finding(
            dimension=dim,
            claim=str(item.get("claim", "")).strip(),
            source_url=str(item.get("source_url", "")).strip(),
            sign=str(item.get("sign", "neutral")).lower(),
            severity=int(item.get("severity", 1) or 1),
            verified=item.get("verified"),
        )
        if f.verified is True:
            by_dim.setdefault(dim, []).append(f)
        else:
            unverified.append(f)

    if isinstance(raw, dict):
        for dim, items in raw.items():
            for item in (items or []):
                add(dim, item)
    elif isinstance(raw, list):
        for item in raw:
            add(str(item.get("dimension", "")), item)
    return by_dim, unverified


def score_firm(profile: dict, rubric: dict | None = None) -> FirmResult:
    rubric = rubric or load_rubric()
    meta = rubric.get("meta", {})
    scale_max = int(meta.get("scale_max", 10))
    baseline = float(meta.get("neutral_baseline", 5.0))
    step = float(meta.get("finding_step", 1.0))
    min_known = int(meta.get("min_known_dimensions", 4))
    dim_defs: dict = rubric["dimensions"]
    overrides: dict = profile.get("overrides") or {}

    verified_by_dim, unverified = _parse_findings(profile)

    dims: list[DimResult] = []
    for key, d in dim_defs.items():
        vf = verified_by_dim.get(key, [])
        ov = _coerce_override(overrides.get(key), scale_max)

        if ov is not None:
            score, known, overridden = ov, True, True
        elif vf:
            raw = baseline + step * sum(f.signed_weight for f in vf)
            score = max(0.0, min(float(scale_max), raw))
            known, overridden = True, False
        else:
            score, known, overridden = None, False, False

        dims.append(DimResult(
            key=key, title=d.get("title", key), weight=float(d.get("weight", 0)),
            known=known, score=score, verified_findings=vf, overridden=overridden,
        ))

    known_dims = [d for d in dims if d.known]
    known_count = len(known_dims)

    if known_count < min_known:
        return FirmResult(
            firm=profile.get("firm", "Unknown"),
            as_of=str(profile.get("as_of", "")),
            mode="timeline",
            dims=dims, composite=None, band_label=None, band_note=None,
            known_count=known_count, min_known=min_known,
            unverified=unverified, scale_max=scale_max,
        )

    tw = sum(d.weight for d in known_dims) or 1.0
    composite = sum(d.score * d.weight for d in known_dims) / (tw * scale_max) * 100.0
    band_label, band_note = _band(composite, rubric["bands"])
    flag_at = float(rubric.get("flag_at", 3))
    flags = [d for d in known_dims if d.score is not None and d.score <= flag_at]

    return FirmResult(
        firm=profile.get("firm", "Unknown"),
        as_of=str(profile.get("as_of", "")),
        mode="scorecard",
        dims=dims, composite=round(composite, 1),
        band_label=band_label, band_note=band_note,
        known_count=known_count, min_known=min_known,
        flags=flags, unverified=unverified, scale_max=scale_max,
    )


def blank_profile(firm: str = "") -> dict:
    rubric = load_rubric()
    return {
        "firm": firm,
        "aliases": [],
        "as_of": "",
        "findings": {key: [] for key in rubric["dimensions"]},
        "overrides": {},
        "notes": "",
    }
