"""Builds the 'weekly' feedback report PDF for one saved analysis.

Deterministic layout over data that already exists in `db.get_analysis`:
the same KPIs, charts, and executive summary as the dashboard, plus a
table of the highest-priority tickets. No new facts are computed here —
this module only lays out numbers Python already produced elsewhere.
"""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from loom.reports.charts import (
    category_distribution_chart,
    sentiment_chart,
    theme_frequency_chart,
    urgency_chart,
)

INK = colors.HexColor("#0B0B0B")
INK_SECONDARY = colors.HexColor("#52514E")
INK_MUTED = colors.HexColor("#898781")
BORDER = colors.HexColor("#DEDCD3")
ACCENT = colors.HexColor("#2A78D6")
ACCENT_TINT = colors.HexColor("#EEF4FC")
GOOD = colors.HexColor("#0CA30C")
CRITICAL = colors.HexColor("#D03B3B")

PAGE_MARGIN = 1.8 * cm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN
URGENCY_RANK = {"High": 2, "Medium": 1, "Low": 0}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], alignment=0, fontName="Helvetica-Bold", fontSize=22, textColor=INK
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=9.5, textColor=INK_MUTED
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=INK,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10, textColor=INK_SECONDARY, leading=15
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", fontName="Helvetica-Bold", fontSize=7, textColor=INK_MUTED, leading=8.5
        ),
        "chart_caption": ParagraphStyle(
            "chart_caption", parent=base["Normal"], fontSize=9, textColor=INK_MUTED, spaceAfter=4
        ),
        "table_header": ParagraphStyle(
            "table_header", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontSize=8.5, textColor=INK_SECONDARY, leading=11
        ),
    }


def _kpi_cell(label: str, value: str, tone, styles: dict) -> Table:
    value_style = ParagraphStyle(
        "kpi_value", fontName="Helvetica-Bold", fontSize=15, textColor=tone, leading=18
    )
    cell = Table(
        [[Paragraph(label.upper(), styles["kpi_label"])], [Paragraph(escape(value), value_style)]],
        colWidths=[CONTENT_WIDTH / 5 - 0.2 * cm],
    )
    cell.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return cell


def _kpi_grid(analytics: dict, validation_report: dict, styles: dict) -> Table:
    top_category = analytics["top_categories"][0]["name"] if analytics["top_categories"] else "N/A"
    top_theme = analytics["top_themes"][0]["name"] if analytics["top_themes"] else "N/A"
    avg_score = analytics["average_sentiment_score"]
    score_tone = GOOD if avg_score > 0.1 else CRITICAL if avg_score < -0.1 else INK

    tiles = [
        ("Total Feedback", str(analytics["total_processed"]), INK),
        ("Skipped Rows", str(validation_report["skipped"]), INK),
        ("Processing Success", f"{analytics['processing_success_rate']}%", INK),
        ("Positive", f"{analytics['positive_pct']}%", GOOD),
        ("Negative", f"{analytics['negative_pct']}%", CRITICAL),
        ("Avg Sentiment", f"{'+' if avg_score > 0 else ''}{avg_score:.2f}", score_tone),
        ("Top Category", top_category, INK),
        ("Top Theme", top_theme, INK),
        (
            "High Urgency",
            str(analytics["high_urgency_count"]),
            CRITICAL if analytics["high_urgency_count"] else INK,
        ),
        ("Actionable", str(analytics["actionable_count"]), INK),
    ]
    rows = [tiles[i : i + 5] for i in range(0, len(tiles), 5)]
    grid = Table(
        [[_kpi_cell(label, value, tone, styles) for label, value, tone in row] for row in rows],
        colWidths=[CONTENT_WIDTH / 5] * 5,
        hAlign="LEFT",
    )
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return grid


def _chart_image(png_bytes: bytes, width_cm: float) -> Image:
    pil_image = PILImage.open(io.BytesIO(png_bytes))
    aspect = pil_image.height / pil_image.width
    return Image(io.BytesIO(png_bytes), width=width_cm * cm, height=width_cm * cm * aspect)


def _summary_box(summary: str, styles: dict) -> Table:
    box = Table([[Paragraph(escape(summary), styles["body"])]], colWidths=[CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT_TINT),
                ("BOX", (0, 0), (-1, -1), 0, colors.white),
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return box


def _highlighted_tickets_table(items: list[dict], styles: dict, limit: int = 10) -> Table:
    ranked = sorted(items, key=lambda t: (URGENCY_RANK.get(t["urgency"], 0), t["actionable"]), reverse=True)
    shown = ranked[:limit]

    columns = ("Ticket", "Category", "Theme", "Urgency", "Feedback")
    header = [Paragraph(h, styles["table_header"]) for h in columns]
    rows = [header]
    for ticket in shown:
        snippet = ticket["feedback_text"][:160] + ("…" if len(ticket["feedback_text"]) > 160 else "")
        rows.append(
            [
                Paragraph(escape(ticket["ticket_id"]), styles["table_cell"]),
                Paragraph(escape(ticket["primary_category"]), styles["table_cell"]),
                Paragraph(escape(ticket["primary_theme"]), styles["table_cell"]),
                Paragraph(escape(ticket["urgency"]), styles["table_cell"]),
                Paragraph(escape(snippet) or "—", styles["table_cell"]),
            ]
        )

    col_widths = [
        CONTENT_WIDTH * 0.10,
        CONTENT_WIDTH * 0.18,
        CONTENT_WIDTH * 0.18,
        CONTENT_WIDTH * 0.10,
        CONTENT_WIDTH * 0.44,
    ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#FAFAF8")))
    table.setStyle(TableStyle(style))
    return table


def _format_date(iso_timestamp: str) -> str:
    try:
        return datetime.fromisoformat(iso_timestamp).strftime("%B %d, %Y")
    except ValueError:
        return iso_timestamp


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.line(PAGE_MARGIN, 1.3 * cm, A4[0] - PAGE_MARGIN, 1.3 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(INK_MUTED)
    canvas.drawString(PAGE_MARGIN, 0.9 * cm, "Generated by Loom")
    canvas.drawRightString(A4[0] - PAGE_MARGIN, 0.9 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_weekly_report_pdf(record: dict) -> bytes:
    """`record` is the dict returned by db.get_analysis: analysis_id,
    created_at, validation_report, analytics, summary, items.
    """
    styles = _styles()
    analytics = record["analytics"]
    validation_report = record["validation_report"]

    story: list = [
        Paragraph("Weekly Feedback Report", styles["title"]),
        Spacer(1, 4),
        Paragraph(
            f"Analysis run on {_format_date(record['created_at'])} &nbsp;&middot;&nbsp; "
            f"{analytics['total_processed']} of {validation_report['total_rows']} tickets processed "
            f"&nbsp;&middot;&nbsp; Report ID {escape(record['analysis_id'][:8])}",
            styles["subtitle"],
        ),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=16),
        _kpi_grid(analytics, validation_report, styles),
        KeepTogether(
            [Paragraph("Executive Summary", styles["h2"]), _summary_box(record["summary"], styles)]
        ),
        KeepTogether(
            [
                Paragraph("Category Distribution", styles["h2"]),
                Paragraph("Primary category, by ticket count", styles["chart_caption"]),
                _chart_image(
                    category_distribution_chart(analytics["top_categories"]), width_cm=CONTENT_WIDTH / cm
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph("Sentiment &amp; Urgency", styles["h2"]),
                Table(
                    [
                        [
                            Paragraph("Sentiment distribution", styles["chart_caption"]),
                            Paragraph("Urgency breakdown", styles["chart_caption"]),
                        ],
                        [
                            _chart_image(
                                sentiment_chart(
                                    analytics["positive_pct"],
                                    analytics["neutral_pct"],
                                    analytics["negative_pct"],
                                ),
                                width_cm=CONTENT_WIDTH / cm / 2 - 0.3,
                            ),
                            _chart_image(
                                urgency_chart(analytics["urgency_distribution"]),
                                width_cm=CONTENT_WIDTH / cm / 2 - 0.3,
                            ),
                        ],
                    ],
                    colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2],
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph("Top Recurring Themes", styles["h2"]),
                _chart_image(theme_frequency_chart(analytics["top_themes"]), width_cm=CONTENT_WIDTH / cm),
            ]
        ),
        Paragraph("Highlighted Tickets", styles["h2"]),
        Paragraph("Highest urgency and actionable tickets from this batch", styles["chart_caption"]),
        _highlighted_tickets_table(record["items"], styles),
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title="Weekly Feedback Report",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
