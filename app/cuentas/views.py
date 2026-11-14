"""Controlador: cuentas de usuario (registro, login y recuperación) con InsForge.

La sesión vive en la cookie firmada de Flask (``session["user"]``: id, email y
nombre). Si ``AUTH_REQUIRED`` está activo, todo ``/app/`` exige haber iniciado
sesión; el sitio público (``/``, ``/graficas``, ``/informe``) sigue abierto.
"""
from __future__ import annotations

from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from app.cuentas import insforge
from app.cuentas.insforge import AuthError

bp = Blueprint("cuentas", __name__, template_folder="templates")


def current_user() -> dict | None:
    return session.get("user")


def login_user(user: dict) -> None:
    session.clear()  # evita fijación de sesión
    session["user"] = {"id": user["id"], "email": user["email"], "name": _display_name(user)}
    session.permanent = True


def _display_name(user: dict) -> str:
    profile = user.get("profile") or {}
    return profile.get("name") or user.get("name") or user["email"].split("@")[0]


def _safe_next(target: str | None) -> str:
    """Solo se redirige a rutas del propio sitio (evita open redirect)."""
    if target:
        host = urlparse(request.host_url)
        dest = urlparse(urljoin(request.host_url, target))
        if dest.scheme in ("http", "https") and dest.netloc == host.netloc and target.startswith("/"):
            return target
    return url_for("moainvest.app_home")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("cuentas.ingresar", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


@bp.app_context_processor
def inject_user() -> dict:
    return {"current_user": current_user()}


@bp.before_app_request
def guard_app_area():
    if current_app.config["AUTH_REQUIRED"] and request.path.startswith("/app/") and current_user() is None:
        return redirect(url_for("cuentas.ingresar", next=request.full_path.rstrip("?")))
    return None


def _form(field: str) -> str:
    return (request.form.get(field) or "").strip()


@bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if current_user() and request.method == "GET":
        return redirect(_safe_next(request.args.get("next")))
    email = _form("email").lower()
    if request.method == "POST":
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Escribe tu correo y contraseña.", "error")
        else:
            try:
                result = insforge.sign_in(email, password)
            except AuthError as exc:
                if exc.status == 403 and "verif" in exc.message.lower():
                    insforge_safe_resend(email)
                    flash("Verifica tu correo: te enviamos un código.", "info")
                    return redirect(url_for("cuentas.verificar", email=email, next=request.args.get("next")))
                flash(_credentials_message(exc), "error")
            else:
                login_user(result.user)
                return redirect(_safe_next(request.args.get("next")))
    return render_template("cuentas/ingresar.html", email=email, next=request.args.get("next"))


def _credentials_message(exc: AuthError) -> str:
    return "Correo o contraseña incorrectos." if exc.status in (400, 401) else exc.message


def insforge_safe_resend(email: str) -> None:
    try:
        insforge.resend_verification(email)
    except AuthError:
        pass


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user() and request.method == "GET":
        return redirect(url_for("moainvest.app_home"))
    email, name = _form("email").lower(), _form("name")
    if request.method == "POST":
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Escribe tu correo y una contraseña.", "error")
        elif password != (request.form.get("password2") or ""):
            flash("Las contraseñas no coinciden.", "error")
        else:
            try:
                result = insforge.sign_up(email, password, name)
            except AuthError as exc:
                flash(exc.message, "error")
            else:
                if result.require_email_verification or result.refresh_token is None:
                    flash("Cuenta creada. Te enviamos un código de 6 dígitos a tu correo.", "info")
                    return redirect(url_for("cuentas.verificar", email=email, next=request.args.get("next")))
                login_user(result.user)
                return redirect(_safe_next(request.args.get("next")))
    return render_template("cuentas/registro.html", email=email, name=name, next=request.args.get("next"))


@bp.route("/verificar", methods=["GET", "POST"])
def verificar():
    email = (request.values.get("email") or "").strip().lower()
    if request.method == "POST":
        if request.form.get("action") == "reenviar":
            insforge_safe_resend(email)
            flash("Si el correo está registrado, te enviamos un nuevo código.", "info")
        else:
            try:
                result = insforge.verify_email(email, _form("code"))
            except AuthError as exc:
                flash(exc.message, "error")
            else:
                if result.user:
                    login_user(result.user)
                    return redirect(_safe_next(request.args.get("next")))
                flash("Correo verificado. Ya puedes iniciar sesión.", "info")
                return redirect(url_for("cuentas.ingresar"))
    return render_template("cuentas/verificar.html", email=email, next=request.args.get("next"))


@bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "POST":
        email = _form("email").lower()
        if email:
            try:
                insforge.send_reset_password(email)
            except AuthError as exc:
                if exc.status >= 500:
                    flash(exc.message, "error")
                    return render_template("cuentas/recuperar.html", email=email)
        # Respuesta uniforme: no revela si el correo existe.
        flash("Si el correo está registrado, te enviamos un código de 6 dígitos.", "info")
        return redirect(url_for("cuentas.nueva_clave", email=email))
    return render_template("cuentas/recuperar.html", email="")


@bp.route("/recuperar/nueva", methods=["GET", "POST"])
def nueva_clave():
    email = (request.values.get("email") or "").strip().lower()
    if request.method == "POST":
        password = request.form.get("password") or ""
        if password != (request.form.get("password2") or ""):
            flash("Las contraseñas no coinciden.", "error")
        else:
            try:
                token = insforge.exchange_reset_code(email, _form("code"))
                insforge.reset_password(token, password)
            except AuthError as exc:
                flash(exc.message, "error")
            else:
                flash("Contraseña actualizada. Inicia sesión con la nueva.", "info")
                return redirect(url_for("cuentas.ingresar"))
    return render_template("cuentas/nueva_clave.html", email=email)


@bp.post("/salir")
def salir():
    session.clear()
    return redirect(url_for("moainvest.resumen"))
