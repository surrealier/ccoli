"""Static dashboard checks for the PRD 5.1 UI requirements.

These assert structure and behaviour, not formatting: the shell must default to
English with switchable locales, the mascot must appear on the hero, and the
type hierarchy must keep long translated strings from breaking the layout.
Matching exact minified CSS text made this suite fail on a pure restyle, so the
rules are matched by declaration instead.
"""
import re
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = SERVER_DIR / "web" / "static"
BRAND_ASSETS_DIR = SERVER_DIR.parent / "assets"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def _css_block(css: str, selector: str) -> str:
    """Return the declarations of the first rule for `selector`, whitespace stripped."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"missing CSS rule for {selector}"
    return re.sub(r"\s+", "", match.group(1))


def test_dashboard_shell_defaults_to_english_and_uses_split_assets():
    html = _read("index.html")

    assert '<html lang="en">' in html
    assert 'href="/dashboard.css"' in html
    assert 'src="/dashboard.js"' in html
    assert 'id="locale-select"' in html
    assert 'data-tab="diagnostics"' in html
    assert 'id="runtime-summary-cards"' in html
    assert 'id="config-json"' in html
    assert 'id="hero-headline"' in html

    for locale in ("en", "ko", "ja", "zh"):
        assert f'value="{locale}"' in html, f"locale option {locale} is not selectable"


def test_dashboard_hero_shows_the_mascot_once():
    html = _read("index.html")

    hero_mascots = re.findall(r'<img[^>]*id="hero-mascot"[^>]*>', html)
    assert len(hero_mascots) == 1, "hero must carry exactly one mascot image"
    assert "/brand-assets/" in hero_mascots[0]
    assert "alt=" in hero_mascots[0]


def test_every_brand_asset_reference_resolves_to_a_real_file():
    html = _read("index.html")

    referenced = sorted(set(re.findall(r"/brand-assets/([A-Za-z0-9._/-]+)", html)))
    assert referenced, "dashboard should reference at least the mascot artwork"

    missing = [name for name in referenced if not (BRAND_ASSETS_DIR / name).is_file()]
    assert not missing, f"dashboard references assets that do not exist: {missing}"


def test_dashboard_css_preserves_text_safe_layout_rules():
    css = _read("dashboard.css")

    title_clamp = _css_block(css, ".title-clamp")
    assert "display:-webkit-box" in title_clamp
    assert "-webkit-line-clamp:2" in title_clamp
    assert "-webkit-box-orient:vertical" in title_clamp
    assert "overflow:hidden" in title_clamp

    body_copy = _css_block(css, ".body-copy")
    assert "font-size:" in body_copy
    assert "line-height:" in body_copy
    assert "color:" in body_copy

    assert "overflow-wrap:anywhere" in re.sub(r"\s+", "", css)
    assert ".hero-figure" in css


def test_dashboard_js_defaults_to_english_and_calls_diagnostics():
    js = _read("dashboard.js")

    assert 'localStorage.getItem("ccoli.locale") || "en"' in js
    assert '"/api/diagnostics/"' in js
