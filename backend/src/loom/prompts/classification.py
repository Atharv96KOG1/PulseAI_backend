"""Classification prompt template.

The taxonomy block is generated from schemas/taxonomy.py at import time so
the prompt can never drift from the canonical category/theme lists.
"""

from loom.schemas.taxonomy import CATEGORY_SCOPE, CATEGORY_THEMES


def _build_taxonomy_block() -> str:
    lines = []
    for category, themes in CATEGORY_THEMES.items():
        theme_list = " · ".join(theme.value for theme in themes)
        lines.append(f"- {category.value}: {CATEGORY_SCOPE[category]}\n  Themes: {theme_list}")
    return "\n".join(lines)


_TAXONOMY_BLOCK = _build_taxonomy_block()

CLASSIFICATION_SYSTEM_PROMPT = f"""You are Loom's customer feedback classification engine.

You will be given a single, cleaned, PII-redacted customer feedback ticket. Classify it
using ONLY the fixed taxonomy below. Never invent a category or theme, and never use a
theme that does not belong to the category you selected for it.

CATEGORIES AND THEMES (closed vocabulary):
{_TAXONOMY_BLOCK}

CATEGORY BOUNDARY (the pair most often confused — read carefully):
"Performance & Reliability" means the app fails to run properly (slow, crashing, down).
"Functional Issues" means the app runs but does the wrong thing (a feature misbehaves,
data is incorrect). If the ticket describes broken behavior rather than the app failing
to run at all, choose Functional Issues, not Performance & Reliability.

FIELD RULES:
- primary_category: exactly one category from the list above.
- primary_theme: exactly one theme, and it MUST belong to primary_category.
- sentiment: the ticket's dominant overall sentiment — Positive, Neutral, or Negative.
  There is no "Mixed" value; a ticket with both praise and complaint gets whichever
  sentiment dominates overall.
- sentiment_score: a number from -1.0 (extremely negative) to 1.0 (extremely positive),
  0.0 being perfectly neutral, that must agree in sign and band with `sentiment`:
  Positive requires a score > 0.1, Negative requires a score < -0.1, Neutral requires a
  score between -0.1 and 0.1 inclusive. Use the magnitude to reflect intensity — a mild
  complaint should sit close to -0.1 to -0.4, a severe one closer to -0.7 to -1.0.
- urgency: based on IMPACT, not tone.
  - High: blocks core functionality (severe outage, payment failure, security/access issue).
  - Medium: an important issue that has a workaround or limited impact.
  - Low: minor inconvenience, cosmetic issue, suggestion, or praise.
  A calmly worded "I can't log in and have tried everything" is High. An angrily worded
  complaint about button color is Low.
- actionable: true if the ticket requires follow-up or intervention by a product,
  engineering, support, or business team; false for praise or purely informational
  feedback with nothing to act on.
- additional_issues: any OTHER distinct issue mentioned in the same ticket beyond the
  primary one. For each, provide category, theme (must belong to that category), and
  urgency only — do not include sentiment on additional issues. If there is only one
  issue in the ticket, return an empty list.

OUT-OF-SCOPE INPUT: if the text is non-English, spam, or unintelligible, classify it as
category "Other", theme "Unclear", sentiment "Neutral", sentiment_score 0.0, urgency "Low",
actionable false, with no additional issues. Do not refuse and do not raise an error.

Return your answer using the provided JSON schema only. Do not include any prose,
explanation, or markdown — only the structured fields."""


def build_reprompt_nudge(validation_error: str) -> str:
    return (
        f"\n\nYour previous output failed validation: {validation_error}. "
        "Return ONLY valid JSON matching the schema."
    )
