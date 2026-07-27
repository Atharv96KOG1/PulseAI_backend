"""Shared, dependency-free text inspection helpers.

Used by both validation (to flag warnings) and preprocessing (to decide
whether cleanup is needed). Kept separate from preprocess.py so validate.py
can inspect raw text without pulling in normalization/redaction logic.
"""

import re

_WORD_RE = re.compile(r"\S+")
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
_MARKDOWN_RE = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|^#{1,6}\s|\[[^\]]+\]\([^)]+\)|^\s*[-*+]\s+)",
    re.MULTILINE,
)


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def contains_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(text))


def contains_markdown(text: str) -> bool:
    return bool(_MARKDOWN_RE.search(text))
