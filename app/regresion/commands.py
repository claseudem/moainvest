"""Comandos de ``flask`` de la app de regresión ML."""
from __future__ import annotations

import click
from flask import Flask

from app.regresion import model, tracking


def register(app: Flask) -> None:
    @app.cli.command("train-regression")
    @click.option("--ticker", default="SPY", show_default=True)
    @click.option("--period", default="5y", show_default=True)
    @click.option("--horizon", type=click.IntRange(min=1, max=60), default=5, show_default=True)
    def train_regression(ticker: str, period: str, horizon: int) -> None:
        """Entrena y registra los modelos de regresión para un ticker."""
        try:
            result = model.train_regression(ticker.upper(), period=period, horizon=horizon)
            tracked = tracking.log_training_runs(result)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        rows = []
        for name, fitted in result["modelos"].items():
            for split in ("train", "test"):
                metrics = fitted["metricas"][split]
                drift_metrics = tracked[name]["predicciones"] if split == "test" else {}
                rows.append((name, split, metrics, drift_metrics))
        for name, benchmark in result["benchmarks"].items():
            for split in ("train", "test"):
                rows.append((name, split, benchmark["metricas"][split], {}))

        headers = ("Modelo", "Split", "MAE", "RMSE", "R²", "Acierto", "MAE/RW", "KS", "p-value", "PSI")
        lines = ["  ".join(f"{value:<28}" for value in headers)]
        for name, split, metrics, drift_metrics in rows:
            values = (
                name,
                split,
                f"{metrics['mae']:.6f}",
                f"{metrics['rmse']:.6f}",
                f"{metrics['r2']:.4f}",
                f"{metrics['acierto_direccional']:.3f}",
                f"{metrics['mae_vs_paseo_aleatorio']:.3f}",
                f"{drift_metrics.get('ks', float('nan')):.3f}",
                f"{drift_metrics.get('p_value', float('nan')):.3g}",
                f"{drift_metrics.get('psi', float('nan')):.3f}",
            )
            lines.append("  ".join(f"{value:<28}" for value in values))
        click.echo("\n".join(lines))