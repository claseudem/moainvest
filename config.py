"""Configuración de la aplicación, cargada desde variables de entorno (.env)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración base. Sirve tal cual para desarrollo."""

    # Nombre de la marca: se muestra en títulos, sidebar y emails.
    # Cambiarlo aquí basta para renombrar toda la app.
    SITE_NAME = "MoaiInvest"

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")

    # Segundos que se conservan en caché los datos descargados de Yahoo Finance,
    # para no golpear la API en cada refresco de página o petición del sidebar.
    QUOTE_CACHE_TTL = int(os.environ.get("QUOTE_CACHE_TTL", "15"))
    CANDLE_CACHE_TTL = int(os.environ.get("CANDLE_CACHE_TTL", "60"))

    # Envío de emails vía Resend (https://resend.com). En desarrollo, si no
    # hay clave configurada, se usa el dominio de pruebas onboarding@resend.dev.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    # Imágenes optimizadas vía Cloudinary (https://console.cloudinary.com).
    # Formato: cloudinary://<api_key>:<api_secret>@<cloud_name>. Sin ella, la
    # página de Informes usa las copias locales de static/img/informes.
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    QUOTE_CACHE_TTL = 0
    CANDLE_CACHE_TTL = 0
