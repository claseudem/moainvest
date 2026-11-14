"""Portadas de las noticias: extracción, proxy de miniaturas (seguro) y tarjeta."""
import io

import pytest
from PIL import Image

from app import create_app
from app.core import news
from app.noticias import feed, images
from config import TestingConfig

YAHOO = "https://s.yimg.com/ny/api/res/1.2/abc/original.jpg"


def jpeg(width=1600, height=900):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 16, 46)).save(buf, format="JPEG")
    return buf.getvalue()


class FakeResponse:
    def __init__(self, body=b"", status=200, content_type="image/jpeg", length=None):
        self.body, self.status_code = body, status
        self.headers = {"content-type": content_type}
        if length is not None:
            self.headers["content-length"] = str(length)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i : i + size]


class Calls(list):
    """Descargas hechas; ``responses`` fija la respuesta por URL."""

    responses: dict


@pytest.fixture()
def downloads(monkeypatch):
    calls = Calls()
    responses = {}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses.get(url) or FakeResponse(jpeg())

    monkeypatch.setattr(images.requests, "get", fake_get)
    images._cache.clear()
    calls.responses = responses
    return calls


# ---- Extracción ----

def test_search_items_keep_the_original_and_the_140px_thumbnail():
    item = {
        "uuid": "a", "title": "Nvidia rallies", "providerPublishTime": 1,
        "thumbnail": {"resolutions": [
            {"url": YAHOO, "width": 2560, "height": 1707, "tag": "original"},
            {"url": "https://s.yimg.com/140.jpg", "width": 140, "height": 140, "tag": "140x140"},
        ]},
    }
    headline = news.normalize(item)
    assert (headline.image_url, headline.thumb_url) == (YAHOO, "https://s.yimg.com/140.jpg")


def test_ticker_news_items_use_original_url_and_missing_images_are_none():
    item = {"id": "b", "content": {"title": "t", "pubDate": "2026-11-13T19:03:32Z", "thumbnail": {"originalUrl": YAHOO, "resolutions": []}}}
    assert news.normalize(item).image_url == YAHOO
    assert news.normalize({"uuid": "c", "title": "t", "providerPublishTime": 1}).image_url is None
    insecure = {"uuid": "d", "title": "t", "providerPublishTime": 1, "thumbnail": {"resolutions": [{"url": "http://s.yimg.com/x.jpg", "width": 10}]}}
    assert news.normalize(insecure).image_url is None


# ---- Lista blanca del proxy ----

@pytest.mark.parametrize(
    ("url", "ok"),
    [
        (YAHOO, True),
        ("https://media.zenfs.com/en/reuters/abc.jpg", True),
        ("https://l.yimg.com/x.jpg", True),
        ("http://s.yimg.com/x.jpg", False),                 # sin TLS
        ("https://s.yimg.com.attacker.com/x.jpg", False),   # sufijo engañoso
        ("https://evilyimg.com/x.jpg", False),
        ("https://user@s.yimg.com/x.jpg", False),           # credenciales en la URL
        ("https://s.yimg.com:8443/x.jpg", False),           # otro puerto
        ("https://169.254.169.254/latest/meta-data", False),
        ("", False),
        (None, False),
    ],
)
def test_only_yahoo_image_hosts_over_https_are_allowed(url, ok):
    assert images.is_allowed(url) is ok


def test_proxy_urls_offer_two_widths_and_escape_the_source():
    urls = images.proxy_urls(YAHOO + "?a=1&b=2")
    assert urls["src"].startswith("/api/noticias/imagen?u=https%3A%2F%2Fs.yimg.com") and urls["src"].endswith("&w=360")
    assert "%26b%3D2" in urls["src"] and urls["srcset"].endswith("&w=720 720w")
    assert images.proxy_urls("https://example.com/x.jpg") is None


# ---- Miniaturas ----

def test_thumbnail_is_a_small_3_2_webp_and_is_cached(downloads):
    data = images.thumbnail(YAHOO, 360)
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "WEBP" and img.size == (360, 240)
    assert len(data) < 40 * 1024
    images.thumbnail(YAHOO, 360)
    assert len(downloads) == 1  # la segunda sale de la caché
    assert downloads[0][1]["allow_redirects"] is False and downloads[0][1]["stream"] is True


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status=302),                                    # redirección: no se sigue
        FakeResponse(b"<html>", content_type="text/html"),           # no es una imagen
        FakeResponse(jpeg(), length=images.MAX_BYTES + 1),           # anuncia demasiado
        FakeResponse(b"\xff" * (images.MAX_BYTES + 10)),             # envía demasiado
        FakeResponse(b"not really a jpeg"),                          # corrupta
    ],
)
def test_bad_sources_are_rejected(downloads, response):
    downloads.responses[YAHOO] = response
    with pytest.raises(images.ImageError):
        images.thumbnail(YAHOO, 360)


def test_disallowed_widths_and_hosts_never_download(downloads):
    with pytest.raises(images.ImageError):
        images.thumbnail(YAHOO, 5000)
    with pytest.raises(images.ImageError):
        images.thumbnail("https://example.com/x.jpg", 360)
    assert downloads == []


# ---- Endpoint ----

def logged_client():
    client = create_app(TestingConfig).test_client()
    with client.session_transaction() as s:
        s["user"] = {"id": "u1", "email": "ana@example.com", "name": "Ana"}
    return client


def test_endpoint_serves_webp_with_cache_headers(downloads):
    response = logged_client().get("/api/noticias/imagen", query_string={"u": YAHOO, "w": 720})
    assert response.status_code == 200 and response.mimetype == "image/webp"
    assert response.headers["Cache-Control"].startswith("private") and response.headers["X-Content-Type-Options"] == "nosniff"
    with Image.open(io.BytesIO(response.data)) as img:
        assert img.size == (720, 480)


def test_endpoint_rejects_anonymous_and_foreign_urls(downloads):
    anon = create_app(TestingConfig).test_client()
    assert anon.get("/api/noticias/imagen", query_string={"u": YAHOO}).status_code == 401
    client = logged_client()
    assert client.get("/api/noticias/imagen", query_string={"u": "http://127.0.0.1:5000/"}).status_code == 404
    assert client.get("/api/noticias/imagen", query_string={"u": YAHOO, "w": "abc"}).status_code == 404
    assert downloads == []


# ---- Feed ----

def test_feed_items_carry_the_cover_or_none(monkeypatch):
    with_image = news.Headline("1", "Apple surges", "Reuters", "https://x", 10, ("AAPL",), image_url=YAHOO)
    without = news.Headline("2", "Apple update", "Reuters", "https://y", 9, ("AAPL",))
    monkeypatch.setattr(news, "feed", lambda tickers, **k: [(with_image, ["AAPL"]), (without, ["AAPL"])])
    first, second = feed.build(["AAPL"])
    assert first["imagen"] == images.proxy_urls(YAHOO) and second["imagen"] is None
