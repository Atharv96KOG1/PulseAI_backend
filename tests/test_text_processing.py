from loom.services.text_preprocessing_service import TextPreprocessingService
from loom.utils.text import TextInspector


def test_strip_html_removes_tags():
    result = TextPreprocessingService.strip_html("<p>Hello <b>world</b></p>")
    assert "<" not in result
    assert "Hello" in result and "world" in result


def test_clean_markdown_removes_formatting():
    result = TextPreprocessingService().clean_markdown("**bold** and `code` and [link](http://x.com)")
    assert "**" not in result
    assert "`" not in result
    assert "link" in result and "http://x.com" not in result


def test_normalize_whitespace_collapses_and_trims():
    result = TextPreprocessingService.normalize_whitespace("  a   b\n\tc  ")
    assert result == "a b c"


def test_normalize_text_removes_urls_when_requested():
    service = TextPreprocessingService()
    result = service.normalize_text("check https://example.com now", remove_urls=True)
    assert "example.com" not in result


def test_redact_pii_masks_email():
    result = TextPreprocessingService.redact_pii("contact me at jane.doe@example.com please")
    assert "jane.doe@example.com" not in result
    assert "[EMAIL]" in result


def test_redact_pii_masks_card_before_phone():
    text = "card 4111111111111111 phone 555-123-4567"
    result = TextPreprocessingService.redact_pii(text)
    assert "[CARD]" in result
    assert "4111111111111111" not in result


def test_word_count_counts_whitespace_separated_tokens():
    assert TextInspector.word_count("one two three") == 3


def test_contains_html_detects_tags():
    assert TextInspector.contains_html("<div>hi</div>") is True
    assert TextInspector.contains_html("no tags here") is False


def test_contains_markdown_detects_bold_and_bullets():
    assert TextInspector.contains_markdown("**bold text**") is True
    assert TextInspector.contains_markdown("- a bullet point") is True
    assert TextInspector.contains_markdown("plain sentence") is False
