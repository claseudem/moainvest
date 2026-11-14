"""Trae de InsForge los activos favoritos de un usuario (tabla ``activos_favoritos``).

Uso:
    uv run data/traer_favoritos.py                 # usuario por defecto (abajo)
    uv run data/traer_favoritos.py <user_id>       # otro usuario
    uv run data/traer_favoritos.py <user_id> --json

Lee ``INSFORGE_URL`` e ``INSFORGE_API_KEY`` del ``.env`` de la raíz del proyecto.
La API key es de administrador (salta el RLS): úsala solo en local.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USER_ID = "cdff3ae8-a21a-4eed-8d39-1db6d1e4090e"
TABLE = "activos_favoritos"


def fetch_favorites(user_id: str) -> list[dict]:
    base = os.environ.get("INSFORGE_URL", "").rstrip("/")
    api_key = os.environ.get("INSFORGE_API_KEY", "")
    if not base or not api_key:
        sys.exit("Faltan INSFORGE_URL o INSFORGE_API_KEY en el .env.")
    response = requests.get(
        f"{base}/api/database/records/{TABLE}",
        params={"user_id": f"eq.{user_id}", "select": "ticker,nombre,created_at", "order": "created_at.asc"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if response.status_code >= 400:
        sys.exit(f"InsForge respondió {response.status_code}: {response.text[:200]}")
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("user_id", nargs="?", default=DEFAULT_USER_ID)
    parser.add_argument("--json", action="store_true", help="Imprime el resultado como JSON.")
    args = parser.parse_args()
    try:
        uuid.UUID(args.user_id)
    except ValueError:
        sys.exit(f"«{args.user_id}» no es un UUID válido.")

    load_dotenv(ROOT / ".env")
    rows = fetch_favorites(args.user_id)

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    print(f"Usuario {args.user_id}: {len(rows)} activo(s)")
    for r in rows:
        print(f"  {r['ticker']:<10} {r.get('nombre') or '—':<35} {r['created_at'][:10]}")


if __name__ == "__main__":
    main()
