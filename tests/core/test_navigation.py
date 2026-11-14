from importlib import import_module
from importlib.util import find_spec

from app import INSTALLED_APPS
from app.core.navigation import APPS
from app.core.watchlists import WATCHLISTS


def _is_sentence_case(name: str) -> bool:
    # Los signos de apertura del español (¿ ¡) no cuentan: «¿Qué piensas tú?».
    opening = len(name) - len(name.lstrip("¿¡"))
    prefix, rest = name[:opening], name[opening:]
    return name == prefix + rest[:1].upper() + rest[1:].lower()


def test_sidebar_names_are_sentence_case():
    names = [app.name for app in APPS]
    names += [section.name for app in APPS for section in app.sections]
    names += [watchlist.name for watchlist in WATCHLISTS]
    assert [n for n in names if not _is_sentence_case(n)] == []


def test_every_installed_app_with_pages_is_in_sidebar(app):
    """Toda subapp con páginas propias (salvo ``core``, ``moainvest`` y ``cuentas``) sale en el sidebar,
    como app o como subsección de otra (Quant stats vive dentro del Graficador)."""
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
    # Informes se eliminó y Quant stats ya no es una app del sidebar. Noticias y
    # ¿Qué piensas tú? van justo debajo de Mis activos.
    assert [entry.slug for entry in APPS] == [
        "graficador",
        "analisis-varianza",
        "pyportfolio-opt",
        "favoritos",
        "noticias",
        "que-piensas-tu",
        "pronosticador",
    ]


def test_quant_stats_lives_inside_the_graficador():
    graficador = APPS[0]
    assert graficador.kind == "sections"
    assert [(s.name, s.endpoint) for s in graficador.sections] == [
        ("Gráfico", "graficador.index"),
        ("Quant stats", "quant_stats.fundamentales"),
        ("Comparar", "quant_stats.revision"),
    ]


def test_sentence_case_ignores_spanish_opening_marks():
    assert _is_sentence_case("¿Qué piensas tú?")
    assert not _is_sentence_case("¿qué piensas tú?")
    assert not _is_sentence_case("¿Qué Piensas Tú?")
