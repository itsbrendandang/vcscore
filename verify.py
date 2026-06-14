"""Citation verification.

The gather step can hallucinate plausible-looking source URLs, or cite a real
page that does not actually support the claim. A "citation required" rule alone
does not catch that. This step fetches each source and keeps a finding only if
the page actually loads and mentions the firm (by name or alias).

It is deliberately conservative: a finding it cannot confirm is marked
verified=False, NOT dropped from the profile. The score uses only verified
findings; the report still lists the unverified ones under "check these
yourself" so you do not silently lose leads.
"""
from __future__ import annotations

import re
import html as _html

from http_util import fetch_text


def _page_text(raw_html: str) -> str:
    # strip scripts/styles, then tags, then collapse whitespace — good enough
    # to test for a name mention without a full HTML parser dependency.
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw_html)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).lower()


def _name_tokens(firm: str, aliases: list[str]) -> list[str]:
    names = [firm] + list(aliases or [])
    toks = []
    for n in names:
        n = (n or "").strip()
        if len(n) >= 3:
            toks.append(n.lower())
    return toks


def verify_finding(firm: str, aliases: list[str], finding: dict,
                   fetcher=fetch_text) -> tuple[bool, str]:
    """Return (verified, reason). fetcher is injectable for testing."""
    url = str(finding.get("source_url", "")).strip()
    if not url:
        return False, "no source url"
    ok, raw = fetcher(url)
    if not ok:
        return False, "source did not load (dead link, paywall, or blocked)"
    text = _page_text(raw)
    toks = _name_tokens(firm, aliases)
    if not toks:
        return False, "no firm name to match"
    if any(tok in text for tok in toks):
        return True, "source loads and mentions the firm"
    return False, "source loaded but does not mention the firm"


def verify_profile(profile: dict, fetcher=fetch_text, verbose: bool = False) -> dict:
    """Set `verified` and `verify_reason` on every finding in place. Returns the
    profile and a small summary dict."""
    firm = profile.get("firm", "")
    aliases = profile.get("aliases") or []
    findings = profile.get("findings") or {}
    checked = passed = 0

    def run(dim: str, item: dict):
        nonlocal checked, passed
        v, reason = verify_finding(firm, aliases, item, fetcher)
        item["verified"] = v
        item["verify_reason"] = reason
        checked += 1
        if v:
            passed += 1
        if verbose:
            mark = "ok " if v else "no "
            print(f"    [{mark}] {dim}: {reason} ({item.get('source_url','')[:60]})")

    if isinstance(findings, dict):
        for dim, items in findings.items():
            for item in (items or []):
                run(dim, item)
    elif isinstance(findings, list):
        for item in findings:
            run(str(item.get("dimension", "")), item)

    return {"checked": checked, "verified": passed, "dropped": checked - passed}
