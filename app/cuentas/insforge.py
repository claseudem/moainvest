"""Cliente mínimo de la API de autenticación de InsForge (REST).

El SDK oficial es de JavaScript; como esta app es Flask, hablamos con los
endpoints ``/api/auth/*`` directamente. Se usa ``client_type=server``: el
refresh token llega en el cuerpo de la respuesta (no en una cookie del
navegador) y lo guarda la sesión firmada de Flask.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from flask import current_app

TIMEOUT = 15


class AuthError(Exception):
    """Error devuelto por InsForge (credenciales, código inválido, etc.)."""

    def __init__(self, message: str, status: int = 400, code: str = ""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: dict[str, Any] | None
    refresh_token: str | None = None
    require_email_verification: bool = False


def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    base = current_app.config["INSFORGE_URL"].rstrip("/")
    anon_key = current_app.config["INSFORGE_ANON_KEY"]
    if not base or not anon_key:
        raise AuthError("El inicio de sesión no está configurado (INSFORGE_URL / INSFORGE_ANON_KEY).", 503)
    try:
        response = requests.request(
            method,
            f"{base}/api/auth/{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {anon_key}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AuthError("No se pudo conectar con el servicio de autenticación.", 503) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        message = body.get("message") or body.get("error") or "No se pudo completar la operación."
        raise AuthError(str(message), response.status_code, str(body.get("error") or ""))
    return body if isinstance(body, dict) else {}


def _result(body: dict) -> AuthResult:
    return AuthResult(
        user=body.get("user"),
        refresh_token=body.get("refreshToken"),
        require_email_verification=bool(body.get("requireEmailVerification")),
    )


def sign_up(email: str, password: str, name: str = "") -> AuthResult:
    payload = {"email": email, "password": password}
    if name:
        payload["name"] = name
    return _result(_request("POST", "users", params={"client_type": "server"}, json=payload))


def sign_in(email: str, password: str) -> AuthResult:
    payload = {"method": "password", "email": email, "password": password}
    return _result(_request("POST", "sessions", params={"client_type": "server"}, json=payload))


def verify_email(email: str, code: str) -> AuthResult:
    return _result(_request("POST", "email/verify", params={"client_type": "server"}, json={"email": email, "otp": code}))


def resend_verification(email: str) -> None:
    _request("POST", "email/send-verification", json={"email": email})


def send_reset_password(email: str) -> None:
    _request("POST", "email/send-reset-password", json={"email": email})


def exchange_reset_code(email: str, code: str) -> str:
    return _request("POST", "email/exchange-reset-password-token", json={"email": email, "code": code})["token"]


def reset_password(token: str, new_password: str) -> None:
    _request("POST", "email/reset-password", json={"newPassword": new_password, "otp": token})
