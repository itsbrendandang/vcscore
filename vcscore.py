#!/usr/bin/env python3
"""vcscore — internal investor-diligence tool.

Organizes PUBLIC signal about a VC firm for your own diligence, weighted toward
behavior in adversity. Not a published product, not a verdict.

  vcscore run "Firm Name"                research + verify sources + score
  vcscore gather "Firm Name" [-o f.yaml]  research + verify, save a profile
  vcscore verify <profile.yaml>           re-check the source links on a profile
  vcscore score <profile.yaml> [--md]     score a profile, print the scorecard
  vcscore new <slug> [--firm "Name"]      blank profile to fill by hand
  vcscore rubric                          print the rubric

run / gather need ANTHROPIC_API_KEY and network. score / new / rubric are offline.
verify needs network (it fetches the source URLs).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scoring import load_rubric, score_firm, blank_profile  # noqa: E402
from report import print_report, to_markdown  # noqa: E402
from verify import verify_profile  # noqa: E402

FIRMS = HERE / "firms"
REPORTS = HERE / "reports"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "firm"


def _load(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _dump(profile: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(profile, f, sort_keys=False, allow_unicode=True, width=100)


def _resolve(ref: str) -> Path | None:
    p = Path(ref)
    if p.exists():
        return p
    alt = FIRMS / f"{_slug(ref)}.yaml"
    return alt if alt.exists() else None


def _score_and_report(profile: dict, stem: str, write_md: bool) -> None:
    result = score_firm(profile, load_rubric())
    print_report(result)
    if write_md:
        md = REPORTS / f"{stem}.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(to_markdown(result))
        print(f"\nMarkdown report -> {md}")


def cmd_run(args) -> int:
    from gather import gather, GatherError
    try:
        profile = gather(args.firm, notes=args.notes or "")
    except GatherError as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 2
    print("  Verifying source links…")
    summary = verify_profile(profile, verbose=True)
    print(f"  Verified {summary['verified']}/{summary['checked']} sources "
          f"({summary['dropped']} could not be confirmed).")
    out = Path(args.output) if args.output else FIRMS / f"{_slug(args.firm)}.yaml"
    _dump(profile, out)
    print(f"Profile -> {out}")
    _score_and_report(profile, out.stem, write_md=True)
    print("Tip: edit the profile's findings/overrides, then `vcscore score` it again.")
    return 0


def cmd_gather(args) -> int:
    from gather import gather, GatherError
    try:
        profile = gather(args.firm, notes=args.notes or "")
    except GatherError as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 2
    print("  Verifying source links…")
    summary = verify_profile(profile, verbose=True)
    print(f"  Verified {summary['verified']}/{summary['checked']} sources.")
    out = Path(args.output) if args.output else FIRMS / f"{_slug(args.firm)}.yaml"
    _dump(profile, out)
    print(f"Profile saved -> {out}")
    return 0


def cmd_verify(args) -> int:
    path = _resolve(args.profile)
    if not path:
        print(f"Profile not found: {args.profile}", file=sys.stderr)
        return 1
    profile = _load(path)
    summary = verify_profile(profile, verbose=True)
    _dump(profile, path)
    print(f"\nVerified {summary['verified']}/{summary['checked']} sources "
          f"({summary['dropped']} could not be confirmed). Updated -> {path}")
    return 0


def cmd_score(args) -> int:
    path = _resolve(args.profile)
    if not path:
        print(f"Profile not found: {args.profile}", file=sys.stderr)
        return 1
    profile = _load(path)
    _score_and_report(profile, path.stem, write_md=bool(args.md) or args.save_md)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(to_markdown(score_firm(profile, load_rubric())))
        print(f"Markdown report -> {args.md}")
    return 0


def cmd_new(args) -> int:
    firm = args.firm or args.slug.replace("-", " ").title()
    profile = blank_profile(firm)
    out = FIRMS / f"{_slug(args.slug)}.yaml"
    if out.exists() and not args.force:
        print(f"{out} exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    _dump(profile, out)
    print(f"Blank profile -> {out}")
    print("Add findings (claim/source_url/sign/severity) per dimension, run `vcscore verify`, then `vcscore score`.")
    return 0


def cmd_rubric(args) -> int:
    r = load_rubric()
    print(f"\n{r['meta']['name']} (v{r['meta']['version']}) — weights sum to "
          f"{sum(d['weight'] for d in r['dimensions'].values())}")
    print(f"Composite needs >= {r['meta']['min_known_dimensions']} dimensions with verified signal, "
          f"else an incident timeline is shown.\n")
    for key, d in r["dimensions"].items():
        print(f"[{d['weight']:>2}]  {d['title']}  ({key})")
        print(f"      {d['question']}")
        print(f"      + {d['positive']}")
        print(f"      - {d['negative']}\n")
    print("Index bands:")
    for b in r["bands"]:
        print(f"  >= {b['min']:>2}  {b['label']:<26} {b['note']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vcscore", description="Internal VC diligence tool.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="research + verify + score (needs ANTHROPIC_API_KEY)")
    r.add_argument("firm")
    r.add_argument("--notes", help="known facts to feed the researcher")
    r.add_argument("-o", "--output", help="output profile YAML path")
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("gather", help="research + verify, save a profile")
    g.add_argument("firm")
    g.add_argument("--notes")
    g.add_argument("-o", "--output")
    g.set_defaults(func=cmd_gather)

    v = sub.add_parser("verify", help="re-check the source links on a profile")
    v.add_argument("profile")
    v.set_defaults(func=cmd_verify)

    s = sub.add_parser("score", help="score a profile (offline)")
    s.add_argument("profile")
    s.add_argument("--md", help="write markdown to this path")
    s.add_argument("--save-md", action="store_true", help="auto-save markdown to reports/")
    s.set_defaults(func=cmd_score)

    n = sub.add_parser("new", help="blank profile template")
    n.add_argument("slug")
    n.add_argument("--firm")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    rb = sub.add_parser("rubric", help="print the rubric")
    rb.set_defaults(func=cmd_rubric)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
