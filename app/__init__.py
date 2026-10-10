"""Proyecto Flask: application factory e ``INSTALLED_APPS``.

Igual que en Django, el proyecto no tiene lógica propia: solo ensambla las
apps. Cada app es un paquete de ``app/`` con la misma estructura:

    app/<app>/
      views.py      páginas: define ``bp`` (Blueprint) con sus rutas
      api.py        opcional: endpoints JSON/PNG bajo /api (otro Blueprint ``bp``)
      commands.py   opcional: ``register(app)`` añade comandos de ``flask``
      *.py          lógica de dominio de la app (los "models")
      templates/<app>/   plantillas, con el nombre de la app como espacio de nombres
      static/            estáticos, servidos con ``url_for("<app>.static", ...)``

Para añadir una app, crea su paquete y añádela a ``INSTALLED_APPS``.
"""
from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec

from flask import Flask

from config import Config

# Orden de registro: ``core`` va primero porque aporta el layout, el sidebar,
# los iconos y la API común que usan las demás.
INSTALLED_APPS = (
    "core",
    "moainvest",
    "varianza",
    "quant_stats",
    "informes",
    "graficador",
    "universo",
)


def create_app(config_class: type[Config] = Config) -> Flask:
    # Sin carpetas globales: cada app trae sus propias plantillas y estáticos.
    app = Flask(__name__, template_folder=None, static_folder=None)
    app.config.from_object(config_class)

    for name in INSTALLED_APPS:
        install_app(app, name)

    return app


def install_app(app: Flask, name: str) -> None:
    """Registra los blueprints de ``views`` y ``api`` de una app y sus comandos."""
    for module in ("views", "api"):
        if find_spec(f"app.{name}.{module}") is not None:
            app.register_blueprint(import_module(f"app.{name}.{module}").bp)
    if find_spec(f"app.{name}.commands") is not None:
        import_module(f"app.{name}.commands").register(app)
