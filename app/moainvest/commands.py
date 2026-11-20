"""Comandos de ``flask`` del sitio MOAINVEST."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import click
from flask import Flask

from app.moainvest import worldmap

# Versión del binario de Tailwind con la que se compila static/moainvest.css.
TAILWINDCSS_VERSION = "v4.3.3"

STATIC = Path(__file__).resolve().parent / "static"


def register(app: Flask) -> None:
    @app.cli.command("build-css")
    @click.option("--watch", is_flag=True, help="Recompila al cambiar las plantillas o el JS.")
    def build_css(watch: bool) -> None:
        """Compila el CSS de Tailwind del sitio MOAINVEST (sin Node).

        Usa el binario standalone de Tailwind que instala ``pytailwindcss``
        (dependencia de desarrollo de uv) en la versión fijada arriba.
        """
        binary = shutil.which("tailwindcss")
        if binary is None:
            raise click.ClickException("No se encuentra tailwindcss: ejecuta `uv sync` (instala pytailwindcss).")
        args = [binary, "-i", str(STATIC / "src" / "moainvest.css"), "-o", str(STATIC / "moainvest.css")]
        args.append("--watch" if watch else "--minify")
        env = {**os.environ, "TAILWINDCSS_VERSION": TAILWINDCSS_VERSION}
        raise SystemExit(subprocess.run(args, env=env, check=False).returncode)

    @app.cli.command("build-world-map")
    def build_world_map() -> None:
        """Regenera el mapa SVG del Barómetro Global (Natural Earth 110m, dominio público)."""
        out = worldmap.build()
        click.echo(f"Mapa escrito en {out} ({out.stat().st_size // 1024} KB)")
