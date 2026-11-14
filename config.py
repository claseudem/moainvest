"""Configuración de la aplicación, cargada desde variables de entorno (.env)."""
from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración base. Sirve tal cual para desarrollo."""

    # Nombre de la marca: se muestra en títulos, sidebar y emails.
    # Cambiarlo aquí basta para renombrar toda la app.
    SITE_NAME = "MoaiInvest"

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

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

    # Alpha Vantage (https://www.alphavantage.co/support/#api-key): proveedor de
    # precios opcional del Graficador. Sin clave aparece como no disponible.
    # El plan gratuito permite ~25 peticiones al día, de ahí la caché larga.
    ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
    ALPHAVANTAGE_CACHE_TTL = int(os.environ.get("ALPHAVANTAGE_CACHE_TTL", "300"))


    # Login con InsForge (https://insforge.dev): URL del proyecto y anon key
    # (``npx @insforge/cli secrets get ANON_KEY``). Con AUTH_REQUIRED activo,
    # todo /app/ exige iniciar sesión.
    INSFORGE_URL = os.environ.get("INSFORGE_URL", "")
    INSFORGE_ANON_KEY = os.environ.get("INSFORGE_ANON_KEY", "")
    # API key del proyecto (full-access, solo servidor): la usa app/favoritos para la BD.
    INSFORGE_API_KEY = os.environ.get("INSFORGE_API_KEY", "")
    AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "1") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get("SESSION_DAYS", "7")))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    QUOTE_CACHE_TTL = 0
    CANDLE_CACHE_TTL = 0
    ALPHAVANTAGE_API_KEY = ""
    ALPHAVANTAGE_CACHE_TTL = 0
    AUTH_REQUIRED = False
    INSFORGE_URL = "https://insforge.test"
    INSFORGE_ANON_KEY = "anon-test"
    INSFORGE_API_KEY = "api-test"
