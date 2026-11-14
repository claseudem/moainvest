"""Compara los tiempos de leer la tabla bronze de MotherDuck vs. descargar directo de Dukascopy.

Uso:
    uv run pipelines/lector.py

Antes hay que haber cargado la tabla con ``cargar_bronze_1_min.py``.
"""
from __future__ import annotations

import time

from cargar_bronze_1_min import TABLE, conectar, descargar


def main() -> None:
    con = conectar()

    t0 = time.perf_counter()
    desde_db = con.execute(f"SELECT * FROM {TABLE}").df()
    t_db = time.perf_counter() - t0
    print(f"MotherDuck : {len(desde_db):>9,} filas en {t_db:.2f}s")

    t0 = time.perf_counter()
    directo = descargar()
    t_directo = time.perf_counter() - t0
    print(f"Dukascopy  : {len(directo):>9,} filas en {t_directo:.2f}s")

    if t_db > 0:
        print(f"Leer de MotherDuck es {t_directo / t_db:.1f}x más rápido que descargar directo")


if __name__ == "__main__":
    main()
