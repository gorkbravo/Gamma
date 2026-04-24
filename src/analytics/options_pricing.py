from __future__ import annotations

import math
from dataclasses import dataclass


SQRT_2PI = math.sqrt(2.0 * math.pi)


@dataclass(frozen=True)
class BlackScholesGreeks:
    implied_volatility: float
    delta: float
    gamma: float
    vega: float
    theta: float
    option_price: float
    risk_free_rate: float
    dividend_yield: float
    methodology: str


def solve_implied_volatility(
    *,
    right: str,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    option_price: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
    tolerance: float = 1e-6,
    max_iterations: int = 120,
) -> float | None:
    if not _is_positive(spot) or not _is_positive(strike) or not _is_positive(time_to_expiry_years) or not _is_positive(option_price):
        return None
    intrinsic = _intrinsic_value(right, spot, strike)
    if option_price <= intrinsic:
        return None

    low = 1e-4
    high = 4.0
    low_price = _option_price(right, spot, strike, time_to_expiry_years, low, risk_free_rate, dividend_yield)
    high_price = _option_price(right, spot, strike, time_to_expiry_years, high, risk_free_rate, dividend_yield)
    if option_price < low_price or option_price > high_price:
        return None

    for _ in range(max_iterations):
        mid = (low + high) * 0.5
        mid_price = _option_price(right, spot, strike, time_to_expiry_years, mid, risk_free_rate, dividend_yield)
        if abs(mid_price - option_price) <= tolerance:
            return mid
        if mid_price > option_price:
            high = mid
        else:
            low = mid
    return (low + high) * 0.5


def calculate_black_scholes_greeks(
    *,
    right: str,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
    methodology: str = "black_scholes_fallback",
) -> BlackScholesGreeks | None:
    if not _is_positive(spot) or not _is_positive(strike) or not _is_positive(time_to_expiry_years) or not _is_positive(volatility):
        return None

    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry_years
    ) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    discount_q = math.exp(-dividend_yield * time_to_expiry_years)
    discount_r = math.exp(-risk_free_rate * time_to_expiry_years)

    if str(right or "").upper() == "P":
        price = strike * discount_r * _normal_cdf(-d2) - spot * discount_q * _normal_cdf(-d1)
        delta = discount_q * (_normal_cdf(d1) - 1.0)
        theta = (
            -(spot * discount_q * _normal_pdf(d1) * volatility) / (2.0 * sqrt_t)
            + dividend_yield * spot * discount_q * _normal_cdf(-d1)
            + risk_free_rate * strike * discount_r * _normal_cdf(-d2)
        ) / 365.0
    else:
        price = spot * discount_q * _normal_cdf(d1) - strike * discount_r * _normal_cdf(d2)
        delta = discount_q * _normal_cdf(d1)
        theta = (
            -(spot * discount_q * _normal_pdf(d1) * volatility) / (2.0 * sqrt_t)
            - dividend_yield * spot * discount_q * _normal_cdf(d1)
            + risk_free_rate * strike * discount_r * _normal_cdf(d2)
        ) / 365.0

    gamma = discount_q * _normal_pdf(d1) / (spot * volatility * sqrt_t)
    vega = spot * discount_q * _normal_pdf(d1) * sqrt_t / 100.0

    return BlackScholesGreeks(
        implied_volatility=volatility,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        option_price=price,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        methodology=methodology,
    )


def _option_price(
    right: str,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> float:
    greeks = calculate_black_scholes_greeks(
        right=right,
        spot=spot,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        volatility=volatility,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    return greeks.option_price if greeks is not None else float("nan")


def _intrinsic_value(right: str, spot: float, strike: float) -> float:
    if str(right or "").upper() == "P":
        return max(strike - spot, 0.0)
    return max(spot - strike, 0.0)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / SQRT_2PI


def _is_positive(value: float | None) -> bool:
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0.0
