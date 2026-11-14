"""Comandos de ``flask`` de la app "Alertas"."""
from __future__ import annotations

import click
from flask import Flask


def register(app: Flask) -> None:
    @app.cli.command("alertas-scan")
    def alertas_scan() -> None:
        """Evalúa las alertas de todos los usuarios con preferencias guardadas.

        Pensado para cron o un schedule cada 5-15 minutos en horario de mercado.
        """
        from app.alertas import service, store

        try:
            users = store.users_with_settings()
        except store.StoreError as exc:
            raise click.ClickException(str(exc)) from exc
        total = 0
        for user_id, settings in users:
            try:
                created = service.scan_user(user_id, settings, force=True)
            except store.StoreError as exc:
                click.echo(f"{user_id}: {exc}", err=True)
                continue
            total += len(created)
            for trigger in created:
                click.echo(f"{user_id}: {trigger.ticker} {trigger.change_percent:+.2f}% (nivel {trigger.level})")
        click.echo(f"{len(users)} usuario(s) evaluados, {total} alerta(s) nueva(s).")
