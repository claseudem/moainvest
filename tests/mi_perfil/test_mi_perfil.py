"""MI PERFIL (``/app/mi-perfil/``): identidad, perfiles, nivel, misiones y trayectoria."""
import json
import re
from pathlib import Path

from app.mi_perfil.content import PROFILES, XP_BY_DIFFICULTY, XP_PER_LEVEL, level_for_xp, profiles_payload

JS = Path(__file__).resolve().parents[2] / "app" / "mi_perfil" / "static" / "mi_perfil.js"


def _payload(page: str) -> dict:
    match = re.search(r'<script id="mi-perfil-data" type="application/json">(.*?)</script>', page, re.S)
    assert match, "falta el JSON de Mi perfil"
    return json.loads(match.group(1))


def _logged(client, name="Ana Ruiz", user_id="user-1"):
    with client.session_transaction() as session:
        session["user"] = {"id": user_id, "email": "ana@example.com", "name": name}
    return client


def test_page_renders_the_sections(client):
    response = client.get("/app/mi-perfil/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<title>Mi perfil · MoaiInvest</title>" in page
    for anchor in ("data-route", "data-path", "data-next-card", "data-panel", "data-others", "data-history"):
        assert anchor in page, anchor
    assert "Tu siguiente misión" in page
    assert "Otras misiones" in page
    assert "Historial de misiones completadas" in page


def test_mission_stats_have_the_three_counters(client):
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    for stat in ("completadas", "disponibles", "bloqueadas"):
        assert f'data-stat="{stat}"' in page


def test_no_three_column_layout_remains(client):
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    assert 'data-list="pendientes"' not in page
    assert 'data-list="progreso"' not in page


def test_without_account_no_name_is_invented(client):
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    assert "Cuenta sin nombre" in page
    assert _payload(page)["userKey"] == "anonimo"


def test_account_name_is_shown_when_logged_in(client):
    _logged(client)
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    assert ">Ana Ruiz</h2>" in page
    assert _payload(page)["userKey"] == "user-1"


def test_progress_is_said_to_live_in_this_browser(client):
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    assert "se guarda en este navegador" in page


def test_six_profiles_with_the_agreed_names():
    assert [p["name"] for p in profiles_payload()] == [
        "Inversionista",
        "Ingeniería",
        "Mercadeo",
        "Negocios",
        "Diseño",
        "Análisis de Datos",
    ]


def test_every_profile_has_five_levels_with_missions():
    for profile in profiles_payload():
        assert len(profile["stages"]) == 5, profile["slug"]
        for stage in profile["stages"]:
            assert stage["mission"] and stage["objective"] and len(stage["steps"]) >= 2
            assert stage["xp"] in XP_BY_DIFFICULTY.values()


def test_difficulty_xp_matches_the_spec():
    assert XP_BY_DIFFICULTY == {"basica": 50, "intermedia": 100, "avanzada": 150}


def test_investor_and_engineering_routes_use_the_agreed_level_names():
    investor = next(p for p in profiles_payload() if p["slug"] == "inversionista")
    engineering = next(p for p in profiles_payload() if p["slug"] == "ingenieria")
    assert [s["name"] for s in investor["stages"]] == ["Explorador", "Analista", "Trader", "Gestor", "Gran inversionista"]
    assert [s["name"] for s in engineering["stages"]] == ["Explorador", "Programador", "Analista de datos", "Desarrollador", "Innovador"]


def test_profile_descriptions_match_the_spec():
    by_slug = {p.slug: p for p in PROFILES}
    assert by_slug["negocios"].description == "Comprende empresas, economía y mercados nacionales e internacionales."
    assert by_slug["diseno"].interest == "Visualización, experiencia y comunicación visual"
    assert by_slug["analisis-datos"].interest == "Métricas, estadística e indicadores"


def test_level_thresholds_follow_the_example():
    # Nivel 2 con 120 XP: faltan 80 para llegar a 200, que es el umbral del nivel 3.
    assert level_for_xp(120, 5) == (2, 200)
    assert level_for_xp(0, 5) == (1, XP_PER_LEVEL)
    assert level_for_xp(450, 5) == (5, None)


def test_profile_cards_are_real_buttons(client):
    page = client.get("/app/mi-perfil/").get_data(as_text=True)
    for profile in PROFILES:
        assert f'data-profile="{profile.slug}" aria-pressed="false"' in page


def test_js_never_writes_html_from_data():
    source = JS.read_text(encoding="utf-8")
    assert ".innerHTML" not in source
    assert "moainvest.mi-perfil.v1." in source, "el progreso debe guardarse por usuario"
