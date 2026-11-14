"""Miniaturas de las noticias: reduce la portada original de Yahoo en el servidor.

Yahoo solo ofrece dos tamaños de portada: 140×140 (borrosa en pantallas
retina) y la original (hasta 3840 px y cientos de KB). Su redimensionador
tiene las URL firmadas, así que no se pueden pedir otros tamaños. Aquí se
descarga la original una vez, se recorta al formato de la tarjeta (3:2) y se
comprime en WebP (unos 15–30 KB), con caché en memoria.

Seguridad (evita un proxy abierto / SSRF):
* solo HTTPS y solo hosts de imágenes de Yahoo (``ALLOWED_HOSTS``);
* sin redirecciones (podrían llevar a una IP interna);
* tamaño máximo de descarga y de píxeles (bombas de descompresión);
* el endpoint exige sesión.
"""
from __future__ import annotations

import io
import threading
from collections import OrderedDict
from urllib.parse import quote, urlparse

import requests
from PIL import Image, ImageOps

ALLOWED_HOSTS = ("s.yimg.com", "media.zenfs.com")
ALLOWED_SUFFIXES = (".yimg.com", ".zenfs.com")
WIDTHS = (360, 720)
ASPECT = 2 / 3  # alto / ancho: 3:2
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
TIMEOUT = 8
CACHE_SIZE = 400
QUALITY = 78


class ImageError(Exception):
    """La imagen no está permitida o no se pudo procesar."""


_cache: OrderedDict[tuple[str, int], bytes] = OrderedDict()
_lock = threading.Lock()


def is_allowed(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and parsed.port in (None, 443)
        and not parsed.username
        and (host in ALLOWED_HOSTS or host.endswith(ALLOWED_SUFFIXES))
    )


def proxy_urls(image_url: str | None) -> dict | None:
    """``src`` y ``srcset`` del proxy para la portada, o ``None`` si no hay imagen válida."""
    if not is_allowed(image_url):
        return None
    base = f"/api/noticias/imagen?u={quote(image_url, safe='')}"
    return {
        "src": f"{base}&w={WIDTHS[0]}",
        "srcset": ", ".join(f"{base}&w={w} {w}w" for w in WIDTHS),
    }


def _download(url: str) -> bytes:
    try:
        with requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
            if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                raise ImageError("La fuente no devolvió una imagen.")
            if int(response.headers.get("content-length") or 0) > MAX_BYTES:
                raise ImageError("Imagen demasiado grande.")
            data = bytearray()
            for chunk in response.iter_content(64 * 1024):
                data += chunk
                if len(data) > MAX_BYTES:
                    raise ImageError("Imagen demasiado grande.")
            return bytes(data)
    except requests.RequestException as exc:
        raise ImageError("No se pudo descargar la imagen.") from exc


def _resize(raw: bytes, width: int) -> bytes:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.draft("RGB", (width * 2, width * 2))  # JPEG: decodifica ya reducida
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = ImageOps.fit(img, (width, round(width * ASPECT)), method=Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=QUALITY, method=4)
            return out.getvalue()
    except (OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ImageError("No se pudo procesar la imagen.") from exc


def thumbnail(url: str, width: int) -> bytes:
    """Miniatura WebP de ``url`` con ``width`` px de ancho (uno de ``WIDTHS``)."""
    if width not in WIDTHS:
        raise ImageError("Ancho no permitido.")
    if not is_allowed(url):
        raise ImageError("Origen de imagen no permitido.")
    key = (url, width)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    data = _resize(_download(url), width)
    with _lock:
        _cache[key] = data
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return data
