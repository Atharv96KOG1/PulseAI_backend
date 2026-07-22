"""Demo CLI: run the full pipeline end-to-end and print a polished report.

Verifies the pipeline spine (validate -> classify -> analytics -> summary)
without needing the FastAPI layer running, and doubles as a demo script —
run it against the bundled sample tickets, or point it at a real CSV.

Usage:
    python cli.py                  # runs the 10 bundled sample tickets
    python cli.py --csv path.csv   # runs a real CSV through the same pipeline
    python cli.py --limit 5        # caps the sample tickets to the first N
"""

import argparse
import asyncio

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import config
from analytics.aggregate import compute_analytics
from pipeline.classify import classify_all
from pipeline.summarize import build_summary_facts, generate_executive_summary
from pipeline.validate import RowRecord, validate_csv
from schemas.response import AnalyticsResult, ValidationReport
from schemas.ticket import TicketClassification
from utils.errors import FileValidationError
from utils.text import word_count

console = Console()

SAMPLE_TICKETS = [
    "Payment failed after checkout, my card was charged but the order never went through.",
    "The app crashes every time I open Settings on my phone.",
    "I love the new dashboard design, it's so much cleaner than before!",
    "I can't log in. I've tried resetting my password three times and the reset email never arrives.",
    (
        "The search feature is broken - it shows results from a completely different "
        "category than what I typed. Also, the app has been extremely slow to load "
        "the last few days."
    ),
    "It would be great if you added a dark mode option, and maybe an export-to-PDF button too.",
    "Navigation is confusing, I can never find the billing settings page.",
    "I've been waiting three days for a reply from support and no one has responded to my ticket.",
    "asdkj alksdj boop boop random text!!! 123",
    "",
]

SENTIMENT_STYLE = {"Positive": "bold green", "Neutral": "dim white", "Negative": "bold red"}
URGENCY_STYLE = {"High": "bold red", "Medium": "bold yellow", "Low": "bold green"}


def _sample_rows(limit: int | None) -> tuple[list[RowRecord], int, int]:
    tickets = SAMPLE_TICKETS[:limit] if limit else SAMPLE_TICKETS
    rows = []
    for idx, text in enumerate(tickets):
        if not text.strip():
            continue
        rows.append(
            RowRecord(
                ticket_id=str(idx),
                raw_feedback=text,
                source="cli-sample",
                date=None,
                word_count=word_count(text),
            )
        )
    total_uploaded = len(tickets)
    skipped = total_uploaded - len(rows)
    return rows, total_uploaded, skipped


def _print_banner() -> None:
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "[bold]Loom[/bold] — customer feedback intelligence pipeline\n"
                f"[dim]Model:[/dim] {config.LLM_MODEL}   "
                f"[dim]Batch size:[/dim] {config.BATCH_SIZE}   "
                f"[dim]Max concurrency:[/dim] {config.MAX_CONCURRENCY}"
            ),
            border_style="blue",
            padding=(1, 2),
        )
    )


def _print_validation_report(report: ValidationReport) -> None:
    table = Table(title="Validation", show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_row("Total rows uploaded", str(report.total_rows))
    table.add_row("Processed", f"[green]{report.processed}[/green]")
    table.add_row("Skipped", f"[yellow]{report.skipped}[/yellow]" if report.skipped else "0")
    if report.skip_reasons:
        table.add_row("Skip reasons", ", ".join(f"{k}={v}" for k, v in report.skip_reasons.items()))
    console.print(table)


def _print_items_table(items: list[TicketClassification]) -> None:
    table = Table(title="Classified Tickets", show_lines=False, expand=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Feedback", overflow="fold", max_width=42)
    table.add_column("Category / Theme", max_width=26)
    table.add_column("Sentiment", justify="center")
    table.add_column("Urgency", justify="center")
    table.add_column("Action?", justify="center")

    for item in items:
        sentiment_style = SENTIMENT_STYLE.get(item.sentiment.value, "white")
        urgency_style = URGENCY_STYLE.get(item.urgency.value, "white")
        sentiment_cell = (
            f"[{sentiment_style}]{item.sentiment.value} ({item.sentiment_score:+.2f})[/{sentiment_style}]"
        )
        urgency_cell = f"[{urgency_style}]{item.urgency.value}[/{urgency_style}]"
        action_cell = "[bold green]Yes[/bold green]" if item.actionable else "[dim]No[/dim]"
        category_cell = f"{item.primary_category.value}\n[dim]{item.primary_theme.value}[/dim]"

        table.add_row(
            item.ticket_id,
            item.feedback_text,
            category_cell,
            sentiment_cell,
            urgency_cell,
            action_cell,
        )

    console.print(table)


def _print_analytics(analytics: AnalyticsResult) -> None:
    kpi = Table(title="Key Metrics", show_header=False, box=None, padding=(0, 2, 0, 0))
    kpi.add_row("Processing success rate", f"{analytics.processing_success_rate}%")
    kpi.add_row(
        "Positive / Neutral / Negative",
        f"{analytics.positive_pct}% / {analytics.neutral_pct}% / {analytics.negative_pct}%",
    )
    kpi.add_row("Average sentiment score", f"{analytics.average_sentiment_score:+.2f}")
    kpi.add_row("High urgency tickets", str(analytics.high_urgency_count))
    kpi.add_row("Actionable tickets", str(analytics.actionable_count))
    console.print(kpi)

    dist = Table(title="Category Distribution")
    dist.add_column("Category")
    dist.add_column("Count", justify="right")
    for ranked in analytics.top_categories:
        dist.add_row(ranked.name, str(ranked.count))
    console.print(dist)

    themes = Table(title="Top Recurring Themes")
    themes.add_column("Theme")
    themes.add_column("Count", justify="right")
    for ranked in analytics.top_themes[:8]:
        themes.add_row(ranked.name, str(ranked.count))
    console.print(themes)


async def run(csv_path: str | None, limit: int | None) -> None:
    _print_banner()

    if csv_path:
        with console.status(f"[bold blue]Reading {csv_path}..."):
            df = pd.read_csv(csv_path)
            try:
                validation = validate_csv(df)
            except FileValidationError as exc:
                console.print(f"[bold red]Validation failed ({exc.code}):[/bold red] {exc.message}")
                return
        rows = validation.rows
        total_uploaded = validation.total_rows
        skipped = validation.skipped
        skip_reasons = validation.skip_reasons
    else:
        rows, total_uploaded, skipped = _sample_rows(limit)
        skip_reasons = {"empty_or_null_feedback": skipped} if skipped else {}

    with console.status(f"[bold blue]Classifying {len(rows)} tickets against '{config.LLM_MODEL}'..."):
        items = await classify_all(rows)

    validation_report = ValidationReport(
        total_rows=total_uploaded,
        processed=len(items),
        skipped=skipped,
        skip_reasons=skip_reasons,
    )
    analytics = compute_analytics(items, total_uploaded=total_uploaded, skipped=skipped)

    with console.status("[bold blue]Generating executive summary..."):
        facts = build_summary_facts(analytics, validation_report)
        summary = await generate_executive_summary(facts)

    console.print()
    _print_validation_report(validation_report)
    console.print()
    _print_items_table(items)
    console.print()
    _print_analytics(analytics)
    console.print()
    console.print(Panel(summary, title="Executive Summary", border_style="blue", padding=(1, 2)))
    console.print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Loom pipeline end-to-end from the command line.")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Path to a CSV with a 'feedback' column")
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the bundled sample tickets to the first N"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.csv_path, args.limit))
