from importlib import import_module
from importlib.util import find_spec

from app import INSTALLED_APPS
from app.core.navigation import APPS
from app.core.watchlists import WATCHLISTS


def _is_sentence_case(name: str) -> bool:
    return name == name[:1].upper() + name[1:].lower()


def test_sidebar_names_are_sentence_case():
    names = [app.name for app in APPS]
    names += [section.name for app in APPS for section in app.sections]
    names += [watchlist.name for watchlist in WATCHLISTS]
    assert [n for n in names if not _is_sentence_case(n)] == []


def test_every_installed_app_with_pages_is_in_sidebar(app):
    """Toda subapp con páginas propias sale en el sidebar, salvo las del sitio público.

    ``moainvest`` y ``cuentas`` son páginas del sitio MOAINVEST, no del área App. Quant stats
    vive dentro del Graficador, así que cuenta como subsección de otra app.
    """
    entries = [*APPS, *(section for entry in APPS for section in entry.sections)]
    sidebar_blueprints = {entry.endpoint.split(".", 1)[0] for entry in entries}
    missing = []
    for name in INSTALLED_APPS:
        if name in ("core", "moainvest", "cuentas") or find_spec(f"app.{name}.views") is None:
            continue
        blueprint = import_module(f"app.{name}.views").bp.name
        has_pages = any(
            rule.endpoint.startswith(f"{blueprint}.") and rule.endpoint != f"{blueprint}.static"
            for rule in app.url_map.iter_rules()
        )
        if has_pages and blueprint not in sidebar_blueprints:
            missing.append(name)
    assert missing == []


def test_sidebar_order_without_reports_or_standalone_quant_stats():
    # Informes se eliminó y Quant stats ya no es una app del sidebar.
    assert [entry.slug for entry in APPS] == [
        "graficador",
        "analisis-varianza",
        "pyportfolio-opt",
        "favoritos",
        "pronosticador",
        "mi-perfil",
        "personas",
    ]


def test_quant_stats_lives_inside_the_graficador():
    graficador = APPS[0]
    assert graficador.kind == "sections"
    assert [(s.name, s.endpoint) for s in graficador.sections] == [
        ("Gráfico", "graficador.index"),
        ("Quant stats", "quant_stats.fundamentales"),
        ("Comparar", "quant_stats.revision"),
    ]
