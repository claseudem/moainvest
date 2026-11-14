"""Comandos de ``flask`` de la app "Noticias"."""
from __future__ import annotations

import click
from flask import Flask


def register(app: Flask) -> None:
    @app.cli.command("noticias-digest")
    def noticias_digest() -> None:
        """Envía por correo los titulares nuevos a los suscritos con correo activado."""
        from app.core.db import DBError
        from app.noticias import digest

        try:
            result = digest.run()
        except DBError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Enviados: {result.sent} · sin novedades: {result.skipped} · fallidos: {result.failed}")
