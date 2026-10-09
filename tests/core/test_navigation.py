from importlib import import_module
from importlib.util import find_spec

from app import INSTALLED_APPS
from app.core.navigation import APPS
from app.core.watchlists import WATCHLISTS


def _is_sentence_case(name: str) -> bool:
    return name == "Regresión ML" or name == name[:1].upper() + name[1:].lower()


def test_sidebar_names_are_sentence_case():
    names = [app.name for app in APPS]
    names += [section.name for app in APPS for section in app.sections]
    names += [watchlist.name for watchlist in WATCHLISTS]
    assert [n for n in names if not _is_sentence_case(n)] == []


def test_every_installed_app_with_pages_is_in_sidebar(app):
    """Toda subapp con páginas propias (salvo ``core`` y ``moainvest``) sale en el sidebar."""
    sidebar_blueprints = {entry.endpoint.split(".", 1)[0] for entry in APPS}
    missing = []
    for name in INSTALLED_APPS:
        if name in ("core", "moainvest") or find_spec(f"app.{name}.views") is None:
            continue
        blueprint = import_module(f"app.{name}.views").bp.name
        has_pages = any(
            rule.endpoint.startswith(f"{blueprint}.") and rule.endpoint != f"{blueprint}.static"
            for rule in app.url_map.iter_rules()
        )
        if has_pages and blueprint not in sidebar_blueprints:
            missing.append(name)
    assert missing == []


def test_sidebar_lists_reports_right_after_the_charts():
    assert [entry.slug for entry in APPS][1:] == [
        "informes",
        "analisis-varianza",
        "quant-stats",
        "regresion",
    ]
