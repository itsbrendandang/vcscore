"""Offline tests for the deterministic scoring, the unknown/timeline fallback,
and the citation-verification logic. No network. Run: python tests/test_scoring.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring import score_firm, load_rubric, blank_profile  # noqa: E402
from verify import verify_finding, verify_profile, _page_text  # noqa: E402


def _finding(sign, severity, verified=True, url="https://example.com/x", claim="c"):
    return {"claim": claim, "source_url": url, "sign": sign, "severity": severity, "verified": verified}


def _full_profile():
    """A profile with verified findings in >= min_known dimensions."""
    rubric = load_rubric()
    keys = list(rubric["dimensions"])
    p = blank_profile("Test Capital")
    # give the first 5 dimensions one verified finding each
    p["findings"][keys[0]] = [_finding("negative", 3)]   # down_round_conduct -> 5 - 3 = 2
    p["findings"][keys[1]] = [_finding("negative", 2)]   # -> 3
    p["findings"][keys[2]] = [_finding("positive", 1)]   # -> 6
    p["findings"][keys[3]] = [_finding("positive", 3)]   # -> 8
    p["findings"][keys[4]] = [_finding("neutral", 2)]    # -> 5
    return p, keys


def test_dimension_scoring_from_findings():
    p, keys = _full_profile()
    r = score_firm(p)
    assert r.mode == "scorecard"
    assert r.dim(keys[0]).score == 2.0
    assert r.dim(keys[1]).score == 3.0
    assert r.dim(keys[2]).score == 6.0
    assert r.dim(keys[3]).score == 8.0
    assert r.dim(keys[4]).score == 5.0


def test_unknown_dimensions_excluded():
    p, keys = _full_profile()
    r = score_firm(p)
    # dimensions 6,7 (indices 5,6) have no findings -> unknown
    assert r.dim(keys[5]).known is False and r.dim(keys[5]).score is None
    assert r.known_count == 5


def test_timeline_fallback_when_too_thin():
    p = blank_profile("Thin Capital")
    keys = list(load_rubric()["dimensions"])
    p["findings"][keys[0]] = [_finding("negative", 3)]   # only 1 known dimension
    r = score_firm(p)
    assert r.mode == "timeline"
    assert r.composite is None
    assert r.known_count == 1


def test_unverified_findings_do_not_score_but_are_surfaced():
    p, keys = _full_profile()
    # add an UNverified negative finding to a known dimension; must not change score
    p["findings"][keys[2]].append(_finding("negative", 3, verified=False))
    r = score_firm(p)
    assert r.dim(keys[2]).score == 6.0          # unchanged
    assert any(f.sign == "negative" for f in r.unverified)


def test_override_pins_dimension():
    p, keys = _full_profile()
    p["overrides"] = {keys[0]: 9}
    r = score_firm(p)
    d = r.dim(keys[0])
    assert d.score == 9.0 and d.overridden is True


def test_flags_low_dimensions():
    p, keys = _full_profile()
    r = score_firm(p)
    flagged = {d.key for d in r.flags}
    assert keys[0] in flagged   # score 2 <= flag_at 3
    assert keys[1] in flagged   # score 3 <= flag_at 3
    assert keys[2] not in flagged


def test_composite_is_weighted_over_known_only():
    p, keys = _full_profile()
    r = score_firm(p)
    # recompute by hand over the 5 known dims
    rubric = load_rubric()
    w = [rubric["dimensions"][keys[i]]["weight"] for i in range(5)]
    sc = [2, 3, 6, 8, 5]
    expected = sum(s * wi for s, wi in zip(sc, w)) / (sum(w) * 10) * 100
    assert abs(r.composite - round(expected, 1)) < 0.05


def test_verify_matches_firm_name_in_page():
    page = "<html><body><h1>Test Capital led the down round</h1></body></html>"
    ok, reason = verify_finding("Test Capital", [], {"source_url": "https://x.com"},
                                fetcher=lambda u: (True, page))
    assert ok is True


def test_verify_rejects_when_firm_absent():
    page = "<html><body>some unrelated article about widgets</body></html>"
    ok, reason = verify_finding("Test Capital", [], {"source_url": "https://x.com"},
                                fetcher=lambda u: (True, page))
    assert ok is False and "does not mention" in reason


def test_verify_rejects_dead_link():
    ok, reason = verify_finding("Test Capital", [], {"source_url": "https://x.com"},
                                fetcher=lambda u: (False, ""))
    assert ok is False and "did not load" in reason


def test_verify_uses_aliases():
    page = "<p>ACME led the bridge</p>"
    ok, _ = verify_finding("Acme Ventures", ["ACME"], {"source_url": "https://x.com"},
                           fetcher=lambda u: (True, page))
    assert ok is True


def test_page_text_strips_tags_and_scripts():
    html = "<script>var x='Hidden Co'</script><p>Visible Co here</p>"
    text = _page_text(html)
    assert "visible co" in text and "hidden co" not in text


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
