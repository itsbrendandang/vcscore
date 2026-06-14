"""Auto-pull layer: research a VC firm with Claude + web search, then extract
structured FINDINGS (claim, source_url, sign, severity) per rubric dimension.

Same two-phase split as dtscore: phase 1 web-searches and writes a cited
briefing; phase 2 maps it onto the finding schema via structured outputs. The
model proposes findings WITH source URLs; verify.py then confirms the sources
actually support them, and scoring.py turns verified findings into numbers.

Requires ANTHROPIC_API_KEY. Degrades with a clear message if absent.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from scoring import load_rubric

MODEL = "claude-opus-4-8"
RESEARCH_MAX_TOKENS = 8000
EXTRACT_MAX_TOKENS = 8000


class GatherError(RuntimeError):
    pass


def _require_sdk():
    try:
        import anthropic  # noqa
    except ImportError as e:
        raise GatherError(
            "The 'anthropic' package isn't installed.\n"
            "  pip install anthropic   and   export ANTHROPIC_API_KEY=sk-ant-..."
        ) from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise GatherError(
            "ANTHROPIC_API_KEY is not set, so auto-pull is unavailable.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Or build a firm profile by hand:  ./vcscore new <slug>"
        )
    return anthropic


def _models():
    from pydantic import BaseModel, Field
    rubric = load_rubric()
    dim_keys = tuple(rubric["dimensions"].keys())

    class Finding(BaseModel):
        dimension: Literal[dim_keys]  # type: ignore
        claim: str = Field(description="One factual sentence about what the firm did. Neutral wording.")
        source_url: str = Field(description="A real, public URL that supports this exact claim.")
        sign: Literal["positive", "negative", "neutral"] = Field(
            description="positive = founder-friendly, negative = founder-unfriendly, neutral = informational.")
        severity: int = Field(description="1 (minor) to 3 (major).")

    class FirmFindings(BaseModel):
        firm: str
        aliases: list[str] = Field(default_factory=list,
                                   description="Other names the firm is known by, for source matching.")
        findings: list[Finding]

    return FirmFindings, dim_keys


def _dim_brief(rubric: dict) -> str:
    lines = []
    for key, d in rubric["dimensions"].items():
        lines.append(f"- {key} ({d['title']}): {d['question']}")
        lines.append(f"    positive = {d['positive']}")
        lines.append(f"    negative = {d['negative']}")
    return "\n".join(lines)


def research(client, firm: str, notes: str = "") -> str:
    rubric = load_rubric()
    sys = (
        "You are a careful diligence researcher helping a founder understand how a VC firm "
        "actually behaves, especially when portfolio companies struggle. You rely ONLY on "
        "public sources (news, podcasts, on-the-record posts) and you cite them. You separate "
        "documented fact from rumor, and you say when the public record is thin. You never "
        "invent sources."
    )
    prompt = (
        f'VC firm: "{firm}".\n\n'
        "Research how this firm behaves with founders, weighted toward ADVERSITY: down rounds, "
        "recaps/washouts, founder removals, board conduct, follow-on support when companies "
        "struggle, transparency, and how consistent the accounts are across sources. Use web "
        "search. For each notable, documented behavior, give a one-line factual summary and the "
        "public URL that documents it. Prefer primary, on-the-record sources. Explicitly note "
        "where the public record is thin or absent. Do not pad with generic firm description.\n"
    )
    if notes:
        prompt += f"\nKnown facts to incorporate:\n{notes}\n"

    messages = [{"role": "user", "content": prompt}]
    last = None
    for _ in range(8):
        last = client.messages.create(
            model=MODEL, max_tokens=RESEARCH_MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=sys,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        )
        if last.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": last.content})
            continue
        break
    return "".join(b.text for b in last.content if b.type == "text").strip()


def extract(client, firm: str, briefing: str) -> dict:
    FirmFindings, dim_keys = _models()
    rubric = load_rubric()
    sys = (
        "You convert a diligence briefing into structured findings. Each finding maps to one "
        "rubric dimension, has a neutral factual claim, a sign (positive = founder-friendly, "
        "negative = founder-unfriendly, neutral = informational), a severity 1-3, and a PUBLIC "
        "source URL that genuinely supports it. Only include findings that the briefing actually "
        "supports with a source. Do not fabricate URLs. If the record is thin, return few "
        "findings, that is correct and expected."
    )
    prompt = (
        f"Firm: {firm}\n\nRubric dimensions:\n{_dim_brief(rubric)}\n\n"
        f"Briefing:\n\"\"\"\n{briefing}\n\"\"\"\n\n"
        "Extract the findings. Include the firm's aliases for source matching."
    )
    resp = client.messages.parse(
        model=MODEL, max_tokens=EXTRACT_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=sys,
        messages=[{"role": "user", "content": prompt}],
        output_format=FirmFindings,
    )
    data = resp.parsed_output.model_dump()
    # group findings by dimension into the profile shape
    grouped: dict[str, list] = {k: [] for k in dim_keys}
    for f in data["findings"]:
        grouped.setdefault(f["dimension"], []).append({
            "claim": f["claim"], "source_url": f["source_url"],
            "sign": f["sign"], "severity": f["severity"], "verified": None,
        })
    return {
        "firm": data.get("firm") or firm,
        "aliases": data.get("aliases", []),
        "as_of": _today(),
        "findings": grouped,
        "overrides": {},
        "notes": "",
        "_briefing": briefing,
    }


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def gather(firm: str, notes: str = "", verbose: bool = True) -> dict:
    anthropic = _require_sdk()
    client = anthropic.Anthropic()
    if verbose:
        print(f"  Researching {firm} (web search)…")
    briefing = research(client, firm, notes)
    if not briefing:
        raise GatherError("Research returned nothing. Try again or build the profile by hand.")
    if verbose:
        n = briefing.count("http")
        print(f"  Briefing: {len(briefing)} chars, ~{n} links. Extracting findings…")
    return extract(client, firm, briefing)
