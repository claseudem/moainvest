"""Sección PERSONAS (``/personas``): páginas, niveles, misiones y hitos de comunidad."""
import re

from app.personas import community
from app.personas.content import (
    DEMO_PROGRESS,
    LEVELS,
    Progress,
    level_requirement,
    level_state,
)


def test_personas_renders_all_blocks(client):
    response = client.get("/personas/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<title>Personas · MOAINVEST</title>" in page
    assert 'id="quienes-somos"' in page
    assert 'id="camino"' in page
    assert 'id="comunidad"' in page
    assert "Datos de demostración" in page


def test_levels_show_the_eight_stages_with_their_state(client):
    page = client.get("/personas/").get_data(as_text=True)
    for level in LEVELS:
        assert level.name in page
    # Estados del progreso de demostración: 1 completado, 2 actual, resto bloqueado.
    track = page[page.index('aria-label="Niveles"') : page.index('id="detalle-nivel"')]
    badges = re.findall(r">\s*(Completado|Actual|Bloqueado)\s*</span>", track)
    assert badges.count("Completado") == 1
    assert badges.count("Actual") == 1
    assert badges.count("Bloqueado") == len(LEVELS) - 2


def test_default_detail_is_the_current_level(client):
    page = client.get("/personas/").get_data(as_text=True)
    current = DEMO_PROGRESS.current
    assert 'aria-labelledby="detalle-titulo"' in page
    assert f'<h3 id="detalle-titulo" class="mt-2 text-3xl font-semibold tracking-[-0.03em]">{LEVELS[current - 1].name}</h3>' in page


def test_nivel_query_selects_that_level(client):
    page = client.get("/personas/?nivel=5").get_data(as_text=True)
    assert f'<h3 id="detalle-titulo" class="mt-2 text-3xl font-semibold tracking-[-0.03em]">{LEVELS[4].name}</h3>' in page


def test_invalid_nivel_falls_back_to_current(client):
    page = client.get("/personas/?nivel=99").get_data(as_text=True)
    assert f">{LEVELS[DEMO_PROGRESS.current - 1].name}</h3>" in page


def test_invite_link_points_to_registration(client):
    page = client.get("/personas/").get_data(as_text=True)
    match = re.search(r'id="invite-link"[^>]*value="([^"]+)"', page)
    assert match, "falta el campo con el enlace de invitación"
    assert match.group(1).endswith("/registro")
    assert "data-copy-invite" in page


def test_community_count_is_marked_as_demo(client):
    page = client.get("/personas/").get_data(as_text=True)
    assert f'data-member-count>{community.DEMO_MEMBER_COUNT}<' in page
    assert "Cifra de demostración" in page


def test_landing_links_to_personas(client):
    page = client.get("/").get_data(as_text=True)
    assert 'href="/personas/"' in page


def test_level_state_follows_progress():
    progress = Progress(completed=frozenset({1, 2}), partial_xp=0)
    assert level_state(1, progress) == "desbloqueado"
    assert level_state(2, progress) == "desbloqueado"
    assert level_state(3, progress) == "actual"
    assert level_state(4, progress) == "bloqueado"


def test_all_levels_completed_has_no_current():
    progress = Progress(completed=frozenset(level.number for level in LEVELS))
    assert progress.current is None
    assert progress.xp == len(LEVELS) * 100


def test_requirement_refers_to_previous_level():
    assert "Punto de partida" in level_requirement(1)
    assert LEVELS[0].name in level_requirement(2)


def test_milestone_states_for_demo_count():
    states = community.milestone_states(137)
    assert [s["state"] for s in states] == ["completado", "proximo", "bloqueado", "bloqueado", "bloqueado"]
    assert states[1]["percent"] == 55


def test_milestones_when_everything_is_reached():
    states = community.milestone_states(3000)
    assert {s["state"] for s in states} == {"completado"}
    assert community.next_target(3000) is None
