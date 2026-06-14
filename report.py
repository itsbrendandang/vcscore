"""Render a FirmResult to terminal + markdown.

Two modes: a scorecard (enough verified signal for a composite) or an incident
timeline (too thin for a composite — just the sourced record). Every output
carries a disclaimer: this organizes PUBLIC sources for your own diligence, it
is not a verdict, and sources can be wrong.
"""
from __future__ import annotations

from scoring import FirmResult, DimResult

DISCLAIMER = (
    "Internal diligence tool. This organizes PUBLIC sources for your own "
    "decision; it is not a verdict on any firm and asserts nothing of its own. "
    "Sources may be incomplete or wrong. Verify before relying."
)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False


def _bar(score: float, scale_max: int, width: int = 10) -> str:
    filled = round(score / scale_max * width)
    return "█" * filled + "░" * (width - filled)


def _sign_mark(sign: str) -> str:
    return {"positive": "+", "negative": "-", "neutral": "·"}.get(sign, "·")


# ----------------------------------------------------------------- terminal

def print_report(r: FirmResult) -> None:
    if _RICH:
        _print_rich(r)
    else:
        _print_plain(r)


def _print_rich(r: FirmResult) -> None:
    c = Console()
    if r.mode == "scorecard":
        color = ("bright_green" if r.composite >= 75 else "green" if r.composite >= 60
                 else "yellow" if r.composite >= 45 else "red")
        head = (f"[bold]{r.firm}[/bold]\n"
                f"Sourced evidence index  [bold {color}]{r.composite:.0f}/100[/bold {color}]  "
                f"[{color}]{r.band_label}[/{color}]\n[dim]{r.band_note}[/dim]")
        if r.as_of:
            head += f"\n[dim]as of {r.as_of} · {r.known_count} of {len(r.dims)} dimensions have public signal[/dim]"
        c.print(Panel(head, box=box.ROUNDED, border_style=color))

        t = Table(box=box.SIMPLE_HEAVY, expand=True)
        t.add_column("Dimension", ratio=3)
        t.add_column("Signal", justify="center")
        t.add_column("", ratio=2)
        t.add_column("Wt", justify="right")
        t.add_column("Receipts", justify="right")
        for d in r.dims:
            if not d.known:
                t.add_row(d.title, "[dim]unknown[/dim]", "[dim]──────────[/dim]",
                          f"{d.weight:.0f}", "[dim]0[/dim]")
                continue
            sc = f"{d.score:.0f}" + ("*" if d.overridden else "")
            scolor = "green" if d.score >= 7 else "yellow" if d.score >= 4 else "red"
            t.add_row(d.title, f"[{scolor}]{sc}[/{scolor}]",
                      f"[{scolor}]{_bar(d.score, r.scale_max)}[/{scolor}]",
                      f"{d.weight:.0f}", str(len(d.verified_findings)))
        c.print(t)

        if r.flags:
            lines = "\n".join(f"  • [red]{d.title}[/red] ({d.score:.0f}/10)" for d in r.flags)
            c.print(Panel(lines, title="Flags", border_style="red", box=box.ROUNDED))

        _print_receipts_rich(c, r)
    else:
        head = (f"[bold]{r.firm}[/bold]\n"
                f"[yellow]Insufficient public signal for a composite[/yellow] "
                f"({r.known_count} of {len(r.dims)} dimensions known, need {r.min_known}).\n"
                f"[dim]Showing the sourced record only.[/dim]")
        c.print(Panel(head, box=box.ROUNDED, border_style="yellow"))
        _print_receipts_rich(c, r)

    if r.unverified:
        lines = "\n".join(
            f"  ? {f.dimension}: {f.claim[:80]} [dim]({f.source_url[:50]})[/dim]"
            for f in r.unverified[:20])
        c.print(Panel(lines, title=f"Could not auto-verify — check these yourself ({len(r.unverified)})",
                      border_style="dim", box=box.ROUNDED))
    c.print(f"[dim]{DISCLAIMER}[/dim]")


def _print_receipts_rich(c, r: FirmResult) -> None:
    any_shown = False
    for d in r.dims:
        if not d.verified_findings:
            continue
        any_shown = True
        c.print(f"\n[bold]{d.title}[/bold]")
        for f in d.verified_findings:
            mk = _sign_mark(f.sign)
            col = "green" if f.sign == "positive" else "red" if f.sign == "negative" else "white"
            c.print(f"  [{col}]{mk}[/{col}] {f.claim}  [dim](sev {f.severity})[/dim]")
            c.print(f"     [dim]{f.source_url}[/dim]")
    if not any_shown:
        c.print("[dim]No verified findings.[/dim]")


def _print_plain(r: FirmResult) -> None:
    line = "=" * 64
    print(f"\n{line}\n{r.firm}")
    if r.mode == "scorecard":
        print(f"Sourced evidence index: {r.composite:.0f}/100   {r.band_label}")
        print(r.band_note)
        print(f"{r.known_count} of {len(r.dims)} dimensions have public signal" +
              (f"   as of {r.as_of}" if r.as_of else ""))
        print(line)
        for d in r.dims:
            if not d.known:
                print(f"  unknown  {'─'*10}  {d.title:<34} (wt {d.weight:.0f})")
            else:
                star = "*" if d.overridden else " "
                print(f"  {d.score:>4.0f}/10 {star}{_bar(d.score, r.scale_max)}  "
                      f"{d.title:<34} (wt {d.weight:.0f}, {len(d.verified_findings)} receipts)")
    else:
        print(f"Insufficient public signal for a composite "
              f"({r.known_count}/{len(r.dims)} known, need {r.min_known}). Sourced record only.")
    print(line)
    for d in r.dims:
        if not d.verified_findings:
            continue
        print(f"\n{d.title}:")
        for f in d.verified_findings:
            print(f"  [{_sign_mark(f.sign)}] {f.claim} (sev {f.severity})")
            print(f"      {f.source_url}")
    if r.unverified:
        print(f"\nCOULD NOT AUTO-VERIFY ({len(r.unverified)}) — check yourself:")
        for f in r.unverified[:20]:
            print(f"  ? {f.dimension}: {f.claim[:80]} ({f.source_url[:50]})")
    print(f"\n{DISCLAIMER}\n")


# ----------------------------------------------------------------- markdown

def to_markdown(r: FirmResult) -> str:
    o: list[str] = [f"# {r.firm} — VCScore (internal diligence)\n"]
    if r.mode == "scorecard":
        o.append(f"## Sourced evidence index: {r.composite:.0f}/100 — {r.band_label}\n")
        o.append(f"{r.band_note}\n")
        o.append(f"*{r.known_count} of {len(r.dims)} dimensions have public signal"
                 + (f", as of {r.as_of}" if r.as_of else "") + ".*\n")
        o.append("| Dimension | Signal | Weight | Receipts |")
        o.append("|---|---|---|---|")
        for d in r.dims:
            sig = "unknown" if not d.known else f"{d.score:.0f}/10" + (" *(override)*" if d.overridden else "")
            o.append(f"| {d.title} | {sig} | {d.weight:.0f} | {len(d.verified_findings)} |")
        o.append("")
    else:
        o.append("## Insufficient public signal for a composite\n")
        o.append(f"Only {r.known_count} of {len(r.dims)} dimensions have verified signal "
                 f"(need {r.min_known}). Sourced record below.\n")

    o.append("## Receipts (verified sources)\n")
    any_shown = False
    for d in r.dims:
        if not d.verified_findings:
            continue
        any_shown = True
        o.append(f"### {d.title}\n")
        for f in d.verified_findings:
            o.append(f"- **{_sign_mark(f.sign)}** (sev {f.severity}) {f.claim}  \n  [{f.source_url}]({f.source_url})")
        o.append("")
    if not any_shown:
        o.append("_No verified findings._\n")

    if r.unverified:
        o.append(f"## Could not auto-verify ({len(r.unverified)}) — check yourself\n")
        for f in r.unverified:
            o.append(f"- {f.dimension}: {f.claim} ([source]({f.source_url}))")
        o.append("")

    o.append("---\n")
    o.append(f"*{DISCLAIMER}*")
    return "\n".join(o)
