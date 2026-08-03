import html
import re
import unicodedata

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_BOLD_ITALIC_RE = re.compile(r"(\*\*|__)(.*?)\1")
_MD_ITALIC_RE = re.compile(r"(?<!\w)(\*|_)(.*?)\1(?!\w)")
_MD_CODE_RE = re.compile(r"`([^`]*)`")
_MD_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_MD_LIST_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)

# PII patterns. Order matters: cards (long digit runs) are redacted before
# phone numbers so a card number is never mistaken for a shorter phone match.
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
ID_RE = re.compile(r"\b[A-Z]{2,5}-?\d{4,}\b")


class TextPreprocessingService:
    """Normalize formatting, then redact PII — always in that order."""

    @staticmethod
    def strip_html(text: str) -> str:
        return html.unescape(_TAG_RE.sub(" ", text))

    @staticmethod
    def clean_markdown(text: str) -> str:
        text = _MD_LINK_RE.sub(r"\1", text)
        text = _MD_BOLD_ITALIC_RE.sub(r"\2", text)
        text = _MD_ITALIC_RE.sub(r"\2", text)
        text = _MD_CODE_RE.sub(r"\1", text)
        text = _MD_HEADER_RE.sub("", text)
        text = _MD_LIST_RE.sub("", text)
        return text

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()

    def normalize_text(self, text: str, remove_urls: bool = False) -> str:
        text = self.strip_html(text)
        text = self.clean_markdown(text)
        text = unicodedata.normalize("NFKC", text)
        if remove_urls:
            text = _URL_RE.sub("", text)
        return self.normalize_whitespace(text)

    @staticmethod
    def redact_pii(text: str) -> str:
        text = EMAIL_RE.sub("[EMAIL]", text)
        text = CARD_RE.sub("[CARD]", text)
        text = PHONE_RE.sub("[PHONE]", text)
        text = ID_RE.sub("[ID]", text)
        return text
