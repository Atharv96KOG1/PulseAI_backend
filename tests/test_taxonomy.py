from loom.models.taxonomy import CATEGORY_SCOPE, CATEGORY_THEMES, Category, Theme


def test_every_category_has_at_least_one_theme():
    for category in Category:
        assert CATEGORY_THEMES[category], f"{category} has no themes"


def test_every_category_has_a_scope_description():
    for category in Category:
        assert CATEGORY_SCOPE[category].strip()


def test_every_theme_belongs_to_exactly_one_category():
    seen: dict[Theme, Category] = {}
    for category, themes in CATEGORY_THEMES.items():
        for theme in themes:
            assert theme not in seen, f"{theme} listed under both {seen.get(theme)} and {category}"
            seen[theme] = category


def test_every_enum_theme_is_mapped_to_a_category():
    mapped_themes = {theme for themes in CATEGORY_THEMES.values() for theme in themes}
    for theme in Theme:
        assert theme in mapped_themes, f"{theme} is not mapped under any category"


def test_unauthorized_access_is_under_account_access():
    assert Theme.UNAUTHORIZED_ACCESS in CATEGORY_THEMES[Category.ACCOUNT_ACCESS]
