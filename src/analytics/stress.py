from __future__ import annotations

"""Escenarios de estrés medidos, no supuestos.

1. Replay histórico: aplica los pesos actuales de una cartera o libro a episodios de crisis
   con fechas documentadas y precios reales de cada posición. Comprar y mantener durante la
   ventana, sin rebalanceo. Una posición sin historia que cubra la ventana no se sustituye por
   un proxy: queda como "missing" y cuenta como plana (0 %), y la cobertura se informa.
2. Regímenes de volatilidad: separa los días de la muestra según la volatilidad realizada del
   benchmark y mide en cada régimen la volatilidad, el VaR/ES histórico y la correlación de la
   cartera con el benchmark.

Los episodios de renta variable usan cierres del S&P 500 de pico a valle; los de materias primas,
liquidaciones del Brent (contrato frontal) en ventanas documentadas (GUA-20261021-9). Conviene
contrastar las fechas con una fuente oficial si se amplía la lista.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.analytics.var import historical_var_cvar

# Un precio del día hábil anterior sirve como precio de inicio o fin (festivos, fines de semana).
COVERAGE_TOLERANCE_DAYS = 7
# Cobertura mínima (peso bruto cubierto / peso bruto total) para publicar el rendimiento del libro.
MIN_EPISODE_COVERAGE = 0.5
# Si el resultado neto es menor que esta fracción del movimiento bruto de las patas, las patas se
# compensan y el reparto se mide sobre el movimiento bruto: dividir por un neto ≈ 0 daba
# −2106.9 % / 2206.9 % en un libro BNO/USO (verificación en vivo 2026-10-27).
NET_SHARE_MIN_FRACTION_OF_GROSS = 0.25


@dataclass(frozen=True)
class StressEpisode:
    episode_id: str
    label: str
    start: date
    end: date
    description: str
    # Tipo de episodio y serie que fija la ventana: "equity" (S&P 500) o "commodity" (Brent).
    kind: str = "equity"
    anchor: str = "S&P 500 close-to-close peak to trough"


# Episodios de renta variable (S&P 500, pico a valle) y de materias primas (Brent frontal),
# en orden cronológico de inicio.
HISTORICAL_STRESS_EPISODES: tuple[StressEpisode, ...] = (
    StressEpisode(
        "gfc_2007_2009",
        "Global financial crisis",
        date(2007, 10, 9),
        date(2009, 3, 9),
        "S&P 500 close-to-close peak to trough, 9 Oct 2007 to 9 Mar 2009.",
    ),
    StressEpisode(
        "q4_2018",
        "Q4 2018 sell-off",
        date(2018, 9, 20),
        date(2018, 12, 24),
        "S&P 500 close-to-close peak to trough, 20 Sep to 24 Dec 2018.",
    ),
    StressEpisode(
        "covid_2020",
        "COVID crash",
        date(2020, 2, 19),
        date(2020, 3, 23),
        "S&P 500 close-to-close peak to trough, 19 Feb to 23 Mar 2020.",
    ),
    StressEpisode(
        "oil_crash_2020",
        "2020 oil price war and demand collapse",
        date(2020, 3, 5),
        date(2020, 4, 21),
        "Brent front-month settlement from 5 Mar 2020, the last close before the OPEC+ talks collapsed on "
        "6 Mar, to its settlement low on 21 Apr 2020 (WTI's May contract settled below zero on 20 Apr).",
        kind="commodity",
        anchor="Brent front-month settlement",
    ),
    StressEpisode(
        "rates_2022",
        "2022 rate shock",
        date(2022, 1, 3),
        date(2022, 10, 12),
        "S&P 500 close-to-close peak to trough, 3 Jan to 12 Oct 2022.",
    ),
    StressEpisode(
        "energy_shock_2022",
        "2022 energy shock (invasion of Ukraine)",
        date(2022, 2, 23),
        date(2022, 3, 8),
        "Brent front-month settlement from 23 Feb 2022, the last close before Russia invaded Ukraine on "
        "24 Feb, to its settlement peak on 8 Mar 2022. A price spike: short-energy legs carry the loss.",
        kind="commodity",
        anchor="Brent front-month settlement",
    ),
    StressEpisode(
        "carry_unwind_2024",
        "August 2024 carry unwind",
        date(2024, 7, 16),
        date(2024, 8, 5),
        "S&P 500 close-to-close peak to trough, 16 Jul to 5 Aug 2024.",
    ),
    StressEpisode(
        "tariffs_2025",
        "2025 tariff shock",
        date(2025, 2, 19),
        date(2025, 4, 8),
        "S&P 500 close-to-close peak to trough, 19 Feb to 8 Apr 2025.",
    ),
)


@dataclass(frozen=True)
class EpisodeLegResult:
    key: str
    weight: float
    status: str  # "covered" | "missing"
    episode_return: float | None = None
    pnl: float | None = None
    contribution_share: float | None = None
    start_price_date: date | None = None
    end_price_date: date | None = None
    note: str | None = None


@dataclass(frozen=True)
class EpisodeReplayResult:
    episode: StressEpisode
    status: str  # "full" | "partial" | "unavailable"
    book_return: float | None
    book_pnl: float | None
    benchmark_return: float | None
    active_return: float | None
    max_drawdown: float | None
    worst_day_return: float | None
    worst_day_date: date | None
    covered_gross_weight: float
    gross_weight: float
    observation_count: int
    legs: list[EpisodeLegResult] = field(default_factory=list)
    note: str | None = None
    # Base de `contribution_share`: "net" (resultado del libro) o "gross" (Σ|P&L de las patas|).
    contribution_basis: str = "net"


def _price_on_or_before(series: pd.Series, when: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean > 0]
    window = clean.loc[:when]
    if window.empty:
        return None
    timestamp = window.index[-1]
    if (when - timestamp).days > COVERAGE_TOLERANCE_DAYS:
        return None
    return timestamp, float(window.iloc[-1])


def _normalized_index(series: pd.Series) -> pd.Series:
    clean = series.copy()
    index = pd.DatetimeIndex(clean.index)
    if index.tz is not None:
        index = index.tz_convert(None)
    clean.index = index.normalize()
    return clean[~clean.index.duplicated(keep="last")].sort_index()


def replay_episode(
    prices: dict[str, pd.Series],
    weights: pd.Series,
    episode: StressEpisode,
    *,
    portfolio_value: float,
    benchmark_prices: pd.Series | None = None,
    missing_notes: dict[str, str] | None = None,
) -> EpisodeReplayResult:
    """Rendimiento de los pesos actuales durante un episodio, comprando y manteniendo.

    ``weights`` son fracciones del capital con signo (la caja no aparece: es plana). El libro
    rinde Σ w_i·R_i sobre las posiciones cubiertas; las no cubiertas cuentan como planas.
    """
    start = pd.Timestamp(episode.start)
    end = pd.Timestamp(episode.end)
    gross = float(weights.abs().sum()) if not weights.empty else 0.0
    legs: list[EpisodeLegResult] = []
    ratios: dict[str, pd.Series] = {}
    covered_gross = 0.0
    for key, weight in weights.items():
        key = str(key)
        weight = float(weight)
        series = prices.get(key)
        if series is None or series.empty:
            note = (missing_notes or {}).get(key) or "No price history for this position."
            legs.append(EpisodeLegResult(key=key, weight=weight, status="missing", note=note))
            continue
        series = _normalized_index(series.astype(float))
        start_point = _price_on_or_before(series, start)
        end_point = _price_on_or_before(series, end)
        if start_point is None or end_point is None:
            first = series.dropna().index.min()
            note = (
                f"Price history starts {first.date().isoformat()}, after the episode began."
                if first is not None and first > start
                else "Price history does not cover this window."
            )
            legs.append(EpisodeLegResult(key=key, weight=weight, status="missing", note=note))
            continue
        start_ts, start_price = start_point
        end_ts, end_price = end_point
        episode_return = end_price / start_price - 1.0
        covered_gross += abs(weight)
        path = series.loc[start_ts:end].dropna() / start_price
        ratios[key] = path
        legs.append(
            EpisodeLegResult(
                key=key,
                weight=weight,
                status="covered",
                episode_return=float(episode_return),
                pnl=float(weight * episode_return * portfolio_value),
                start_price_date=start_ts.date(),
                end_price_date=end_ts.date(),
            )
        )

    benchmark_return = None
    if benchmark_prices is not None and not benchmark_prices.empty:
        bench = _normalized_index(benchmark_prices.astype(float))
        bench_start = _price_on_or_before(bench, start)
        bench_end = _price_on_or_before(bench, end)
        if bench_start is not None and bench_end is not None:
            benchmark_return = bench_end[1] / bench_start[1] - 1.0

    coverage = covered_gross / gross if gross > 0 else 0.0
    if gross <= 0 or not ratios or coverage < MIN_EPISODE_COVERAGE:
        note = (
            "No position has price history covering this window."
            if not ratios
            else f"Only {coverage:.0%} of gross exposure has price history for this window; the book result is withheld."
        )
        return EpisodeReplayResult(
            episode=episode,
            status="unavailable",
            book_return=None,
            book_pnl=None,
            benchmark_return=benchmark_return,
            active_return=None,
            max_drawdown=None,
            worst_day_return=None,
            worst_day_date=None,
            covered_gross_weight=covered_gross,
            gross_weight=gross,
            observation_count=0,
            legs=legs,
            note=note,
        )

    # Trayectoria comprar-y-mantener: NAV_t = 1 + Σ w_i·(P_i,t / P_i,0 - 1), con la última
    # cotización conocida en los días sin dato de una posición.
    frame = pd.DataFrame(ratios).sort_index().ffill().fillna(1.0)
    weight_vector = pd.Series({key: float(weights[key]) for key in frame.columns})
    nav = 1.0 + (frame - 1.0).mul(weight_vector, axis=1).sum(axis=1)
    nav = pd.concat([pd.Series([1.0], index=[frame.index.min() - pd.Timedelta(days=1)]), nav]).sort_index()
    nav = nav[~nav.index.duplicated(keep="last")]
    drawdown = nav / nav.cummax() - 1.0
    daily = nav.pct_change().dropna()
    worst_day_date = daily.idxmin() if not daily.empty else None
    book_return = float(sum(leg.weight * leg.episode_return for leg in legs if leg.status == "covered"))
    gross_move = float(sum(abs(leg.weight * leg.episode_return) for leg in legs if leg.status == "covered"))
    contribution_basis = (
        "gross" if gross_move > 0 and abs(book_return) < NET_SHARE_MIN_FRACTION_OF_GROSS * gross_move else "net"
    )
    denominator = gross_move if contribution_basis == "gross" else book_return
    legs = [
        EpisodeLegResult(
            **{
                **leg.__dict__,
                "contribution_share": (
                    float(leg.weight * leg.episode_return / denominator)
                    if leg.status == "covered" and denominator != 0
                    else None
                ),
            }
        )
        for leg in legs
    ]
    status = "full" if np.isclose(covered_gross, gross) else "partial"
    return EpisodeReplayResult(
        episode=episode,
        status=status,
        book_return=book_return,
        book_pnl=float(book_return * portfolio_value),
        benchmark_return=benchmark_return,
        active_return=(book_return - benchmark_return) if benchmark_return is not None else None,
        max_drawdown=float(drawdown.min()),
        worst_day_return=float(daily.min()) if not daily.empty else None,
        worst_day_date=worst_day_date.date() if worst_day_date is not None else None,
        covered_gross_weight=covered_gross,
        gross_weight=gross,
        observation_count=int(len(frame)),
        legs=legs,
        note=(
            None
            if status == "full"
            else f"{coverage:.0%} of gross exposure has history for this window; missing positions are treated as flat."
        ),
        contribution_basis=contribution_basis,
    )


def price_history_window(prices: dict[str, pd.Series]) -> tuple[date | None, date | None]:
    """Primera y última fecha con precio entre todas las posiciones (unión de ventanas)."""
    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    for series in prices.values():
        if series is None or series.empty:
            continue
        clean = _normalized_index(pd.to_numeric(series, errors="coerce").dropna())
        if clean.empty:
            continue
        starts.append(clean.index.min())
        ends.append(clean.index.max())
    if not starts:
        return None, None
    return min(starts).date(), max(ends).date()


def stress_coverage_summary(
    results: list[EpisodeReplayResult],
    history_start: date | None,
    history_end: date | None,
) -> str | None:
    """Una sola línea cuando ningún episodio queda cubierto, con la ventana disponible del libro,
    en lugar de una fila "No history" por episodio (GUA-20261021-9). Nunca sustituye un proxy."""
    if not results or any(result.status != "unavailable" for result in results):
        return None
    # Si alguna posición cubre algún episodio (aunque no llegue al mínimo), se conservan las filas.
    if any(leg.status == "covered" for result in results for leg in result.legs):
        return None
    first = min(result.episode.start for result in results)
    last = max(result.episode.end for result in results)
    span = f"the {len(results)} episodes run from {first.isoformat()} to {last.isoformat()}"
    if history_start is None or history_end is None:
        return f"No position has price history for any stress episode; {span}. No proxy history is substituted."
    return (
        f"No stress episode is covered: the book's price history runs {history_start.isoformat()} to "
        f"{history_end.isoformat()}, and {span}. No proxy history is substituted."
    )


@dataclass(frozen=True)
class VolatilityRegimeStats:
    regime: str  # "calm" | "stressed"
    observation_count: int
    annual_vol: float | None
    historical_var: float | None
    historical_cvar: float | None
    benchmark_correlation: float | None
    benchmark_annual_vol: float | None


@dataclass(frozen=True)
class VolatilityRegimeAnalysis:
    status: str  # "available" | "unavailable"
    window_days: int
    threshold_annual_vol: float | None
    regimes: list[VolatilityRegimeStats] = field(default_factory=list)
    observation_count: int = 0
    note: str | None = None
    method: str = (
        "Days are split at the median of the benchmark's trailing 21-day realized volatility; "
        "each regime reports the portfolio's own volatility, historical 1-day VaR/ES and correlation."
    )


def volatility_regimes(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series | None,
    alpha: float,
    *,
    window: int = 21,
    min_regime_obs: int = 20,
) -> VolatilityRegimeAnalysis:
    """Riesgo de la cartera en días de volatilidad alta frente a días tranquilos del benchmark."""
    if portfolio_returns is None or portfolio_returns.empty or benchmark_returns is None or benchmark_returns.empty:
        return VolatilityRegimeAnalysis(
            status="unavailable",
            window_days=window,
            threshold_annual_vol=None,
            note="Volatility regimes need portfolio and benchmark return history.",
        )
    aligned = pd.DataFrame(
        {
            "portfolio": pd.to_numeric(_normalized_index(portfolio_returns), errors="coerce"),
            "benchmark": pd.to_numeric(_normalized_index(benchmark_returns), errors="coerce"),
        }
    ).dropna()
    rolling = aligned["benchmark"].rolling(window, min_periods=window).std().dropna()
    if len(rolling) < 2 * min_regime_obs:
        return VolatilityRegimeAnalysis(
            status="unavailable",
            window_days=window,
            threshold_annual_vol=None,
            observation_count=int(len(rolling)),
            note=(
                f"Volatility regimes need at least {2 * min_regime_obs} days after the {window}-day warm-up; "
                f"{len(rolling)} are available."
            ),
        )
    threshold = float(rolling.median())
    sample = aligned.loc[rolling.index]
    masks = {"calm": rolling <= threshold, "stressed": rolling > threshold}
    regimes: list[VolatilityRegimeStats] = []
    for name, mask in masks.items():
        subset = sample[mask]
        if len(subset) < min_regime_obs:
            regimes.append(VolatilityRegimeStats(name, int(len(subset)), None, None, None, None, None))
            continue
        var, cvar = historical_var_cvar(subset["portfolio"], alpha)
        correlation = subset["portfolio"].corr(subset["benchmark"])
        regimes.append(
            VolatilityRegimeStats(
                regime=name,
                observation_count=int(len(subset)),
                annual_vol=float(subset["portfolio"].std() * np.sqrt(252.0)),
                historical_var=float(var) if var is not None else None,
                historical_cvar=float(cvar) if cvar is not None else None,
                benchmark_correlation=float(correlation) if pd.notna(correlation) else None,
                benchmark_annual_vol=float(subset["benchmark"].std() * np.sqrt(252.0)),
            )
        )
    return VolatilityRegimeAnalysis(
        status="available",
        window_days=window,
        threshold_annual_vol=float(threshold * np.sqrt(252.0)),
        regimes=regimes,
        observation_count=int(len(sample)),
    )
