"""Imitación de la API REST de base de datos de InsForge para los tests.

Entiende lo que usan las apps: filtros ``eq.`` e ``in.(...)``, ``limit``,
POST (con restricciones UNIQUE → 409), PATCH y DELETE. Se instala con
``monkeypatch.setattr("requests.request", FakeDB(...))``: todas las apps
llaman a ``requests.request``.
"""
from __future__ import annotations


class FakeDB:
    def __init__(self, unique: dict[str, tuple[str, ...]] | None = None, missing: set[str] | None = None):
        self.tables: dict[str, list[dict]] = {}
        self.unique = unique or {}
        # Tablas sin crear: InsForge responde 404 con el código de Postgres 42P01.
        self.missing = set(missing or ())
        self.calls: list[tuple] = []

    def rows(self, table: str) -> list[dict]:
        return self.tables.setdefault(table, [])

    @staticmethod
    def _match(row: dict, params: dict | None) -> bool:
        for key, cond in (params or {}).items():
            if key in ("select", "order", "limit"):
                continue
            op, _, value = str(cond).partition(".")
            current = row.get(key)
            if isinstance(current, bool):
                current = str(current).lower()
            if op == "eq" and str(current) != value:
                return False
            if op == "in" and str(current) not in [v.strip('"') for v in value.strip("()").split(",")]:
                return False
        return True

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit("/", 1)[1]
        rows = self.rows(table)
        self.calls.append((method, table, params, json, headers))
        status, body = 200, None
        if table in self.missing:
            status = 404
            body = {"code": "42P01", "details": None, "hint": None, "message": f'relation "public.{table}" does not exist'}
        elif method == "GET":
            body = [dict(r) for r in rows if self._match(r, params)]
        elif method == "POST":
            keys = self.unique.get(table)
            for new in json:
                if keys and any(tuple(r.get(k) for k in keys) == tuple(new.get(k) for k in keys) for r in rows):
                    status = 409
                    continue
                rows.append({"created_at": "2026-11-14T10:00:00Z", **new})
        elif method == "PATCH":
            for r in rows:
                if self._match(r, params):
                    r.update(json)
        elif method == "DELETE":
            self.tables[table] = [r for r in rows if not self._match(r, params)]

        class Resp:
            status_code = status

            def json(self):
                return body

        return Resp()
