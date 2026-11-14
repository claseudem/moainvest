"""PERSONAS, la comunidad (``/app/personas/``): directorio, filtros, perfil público e indicadores."""
import json
import re
from pathlib import Path

from app.mi_perfil.content import PROFILES
from app.personas import community
from app.personas.content import PILLARS, TEAMS

JS = Path(__file__).resolve().parents[2] / "app" / "personas" / "static" / "personas.js"


def _payload(page: str) -> dict:
    match = re.search(r'<script id="personas-data" type="application/json">(.*?)</script>', page, re.S)
    assert match, "falta el JSON del directorio"
    return json.loads(match.group(1))


def test_page_renders_the_directory(client):
    response = client.get("/app/personas/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<title>Personas · MoaiInvest</title>" in page
    assert "Conoce a las personas de nuestra" in page
    assert 'id="directorio"' in page
    assert "data-search" in page
    assert 'id="comunidad-indicadores"' in page


def test_filters_cover_every_profile_and_levels_one_to_five(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    for profile in PROFILES:
        assert f'data-filter-profile="{profile.slug}"' in page
    for level in range(1, 6):
        assert f'data-filter-level="{level}"' in page


def test_directory_is_empty_without_a_user_database(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert _payload(page)["members"] == []
    assert "Aún no hay integrantes que mostrar" in page
    assert "Sin base de datos" in page


def test_members_carry_only_public_fields(client, monkeypatch):
    monkeypatch.setattr(
        community,
        "members",
        lambda: [{"name": "Ana", "initial": "A", "profile": "inversionista", "level": 2, "level_name": "Analista", "interests": ["Acciones"], "bio": "", "achievements": []}],
    )
    payload = _payload(client.get("/app/personas/").get_data(as_text=True))
    assert set(payload["members"][0]) == {"name", "initial", "profile", "level", "level_name", "interests", "bio", "achievements"}


def test_indicators_are_labelled_as_examples(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert f"data-member-count>{community.DEMO_MEMBER_COUNT}<" in page
    assert page.count("Cifra de ejemplo") >= 3
    assert "Cifras demostrativas" in page


def test_demo_distribution_adds_up_to_the_example_count():
    assert sum(community.DEMO_BY_PROFILE.values()) == community.DEMO_MEMBER_COUNT


def test_personas_shows_no_personal_progress(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    for hook in ("data-next-card", "data-panel", "data-path", "Tu siguiente misión"):
        assert hook not in page, hook


def test_teams_are_not_here_anymore_and_have_no_individual_names():
    assert len(TEAMS) == 5
    assert [t.name for t in TEAMS] == [
        "Equipo Ingeniería",
        "Equipo Negocios Internacionales",
        "Equipo Mercadeo",
        "Equipo Finanzas",
        "Equipo Análisis de Datos",
    ]


def test_teams_show_on_the_moainvest_landing(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="equipos-title"' in page
    for team in TEAMS:
        assert team.name in page
    assert "Nombre por definir" not in page


def test_purpose_is_kept(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert "Nuestro propósito" in page
    assert len(PILLARS) == 3


def test_invite_link_points_to_registration(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    match = re.search(r'id="invite-link"[^>]*value="([^"]+)"', page)
    assert match and match.group(1).endswith("/registro")


def test_legacy_personas_url_redirects_into_the_app(client):
    response = client.get("/personas/")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/app/personas/")


def test_sidebar_groups_tools_and_new_sections(client):
    page = client.get("/app/personas/").get_data(as_text=True)
    assert '<p class="sidebar__group" role="presentation">Herramientas</p>' in page
    assert '<p class="sidebar__group" role="presentation">Nuevas secciones</p>' in page
    assert page.index("Herramientas") < page.index("Nuevas secciones")
    assert 'class="sidebar__app-name">Mi perfil</span>' in page
    assert 'class="sidebar__app-name">Personas</span>' in page


def test_js_never_writes_html_from_data():
    source = JS.read_text(encoding="utf-8")
    assert ".innerHTML" not in source
    assert "localStorage" not in source, "Personas no debe guardar progreso personal"


def test_milestones_keep_the_agreed_goals():
    goals = [m.target for m in community.MILESTONES]
    assert goals == [100, 250, 500, 1000, 2500]


def test_milestone_states_for_example_count():
    states = community.milestone_states(137)
    assert [s["state"] for s in states] == ["completado", "proximo", "bloqueado", "bloqueado", "bloqueado"]
    assert states[1]["percent"] == 55
