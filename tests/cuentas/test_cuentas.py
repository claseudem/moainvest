"""Cuentas de usuario (login con InsForge): la API de InsForge está simulada."""
import pytest

from app import create_app
from app.cuentas import insforge
from app.cuentas.insforge import AuthError, AuthResult
from config import TestingConfig

USER = {"id": "u1", "email": "ana@example.com", "profile": {"name": "Ana"}}


class GuardedConfig(TestingConfig):
    AUTH_REQUIRED = True


@pytest.fixture()
def guarded_client():
    return create_app(GuardedConfig).test_client()


def test_login_form_renders(client):
    html = client.get("/ingresar").get_data(as_text=True)
    assert 'name="email"' in html and 'name="password"' in html
    assert "noindex" in html


def test_login_success_sets_session_and_shows_name(client, monkeypatch):
    monkeypatch.setattr(insforge, "sign_in", lambda e, p: AuthResult(user=USER, refresh_token="r"))
    response = client.post("/ingresar", data={"email": "Ana@Example.com", "password": "secret1"})
    assert response.status_code == 302 and response.headers["Location"].endswith("/app/")
    with client.session_transaction() as s:
        assert s["user"] == {"id": "u1", "email": "ana@example.com", "name": "Ana"}
        assert "refresh" not in str(s)
    page = client.get("/").get_data(as_text=True)
    assert "Salir" in page and "Ana" in page


def test_login_wrong_password_shows_generic_error(client, monkeypatch):
    def boom(e, p):
        raise AuthError("Invalid credentials", 401)

    monkeypatch.setattr(insforge, "sign_in", boom)
    response = client.post("/ingresar", data={"email": "ana@example.com", "password": "x"})
    assert response.status_code == 200
    assert "Correo o contraseña incorrectos." in response.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "user" not in s


def test_unverified_user_is_sent_to_verification(client, monkeypatch):
    sent = []

    def unverified(e, p):
        raise AuthError("Email not verified", 403)

    monkeypatch.setattr(insforge, "sign_in", unverified)
    monkeypatch.setattr(insforge, "resend_verification", sent.append)
    response = client.post("/ingresar", data={"email": "ana@example.com", "password": "x"})
    assert "/verificar?email=ana@example.com" in response.headers["Location"]
    assert sent == ["ana@example.com"]


def test_signup_requiring_verification_redirects_to_code_page(client, monkeypatch):
    monkeypatch.setattr(
        insforge, "sign_up", lambda e, p, n="": AuthResult(user=USER, require_email_verification=True)
    )
    response = client.post("/registro", data={"email": "ana@example.com", "password": "abcdef", "password2": "abcdef"})
    assert "/verificar" in response.headers["Location"]


def test_signup_password_mismatch(client):
    response = client.post("/registro", data={"email": "a@b.co", "password": "abcdef", "password2": "zzzzzz"})
    assert "no coinciden" in response.get_data(as_text=True)


def test_verify_code_logs_in(client, monkeypatch):
    monkeypatch.setattr(insforge, "verify_email", lambda e, c: AuthResult(user=USER, refresh_token="r"))
    response = client.post("/verificar", data={"email": "ana@example.com", "code": "123456"})
    assert response.headers["Location"].endswith("/app/")
    with client.session_transaction() as s:
        assert s["user"]["id"] == "u1"


def test_password_reset_flow(client, monkeypatch):
    calls = []
    monkeypatch.setattr(insforge, "send_reset_password", lambda e: calls.append(("send", e)))
    monkeypatch.setattr(insforge, "exchange_reset_code", lambda e, c: "tok")
    monkeypatch.setattr(insforge, "reset_password", lambda t, p: calls.append(("reset", t, p)))
    assert client.post("/recuperar", data={"email": "ana@example.com"}).status_code == 302
    response = client.post(
        "/recuperar/nueva", data={"email": "ana@example.com", "code": "123456", "password": "nuevo12", "password2": "nuevo12"}
    )
    assert response.headers["Location"].endswith("/ingresar")
    assert calls == [("send", "ana@example.com"), ("reset", "tok", "nuevo12")]


def test_logout_clears_session(client):
    with client.session_transaction() as s:
        s["user"] = {"id": "u1", "email": "a@b.co", "name": "A"}
    assert client.post("/salir").status_code == 302
    with client.session_transaction() as s:
        assert "user" not in s
    assert client.get("/salir").status_code == 405


def test_app_area_requires_login_but_public_site_does_not(guarded_client):
    response = guarded_client.get("/app/pyportfolio-opt/")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/ingresar?next=/app/pyportfolio-opt/")
    assert guarded_client.get("/").status_code == 200
    with guarded_client.session_transaction() as s:
        s["user"] = {"id": "u1", "email": "a@b.co", "name": "A"}
    assert guarded_client.get("/app/pyportfolio-opt/").status_code == 200


@pytest.mark.parametrize("target", ["https://evil.example/x", "//evil.example", "javascript:alert(1)"])
def test_login_ignores_external_next(client, monkeypatch, target):
    monkeypatch.setattr(insforge, "sign_in", lambda e, p: AuthResult(user=USER))
    response = client.post("/ingresar", query_string={"next": target}, data={"email": "a@b.co", "password": "x"})
    assert response.headers["Location"].endswith("/app/")


def test_insforge_error_message_is_parsed(app, monkeypatch):
    class Resp:
        status_code = 401

        def json(self):
            return {"error": "INVALID_CREDENTIALS", "message": "Invalid credentials"}

    monkeypatch.setattr(insforge.requests, "request", lambda *a, **k: Resp())
    with app.app_context(), pytest.raises(AuthError) as exc:
        insforge.sign_in("a@b.co", "x")
    assert exc.value.status == 401 and exc.value.message == "Invalid credentials"
