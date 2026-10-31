"""Forecasting calculations, independent of the web app and the database.

Every model implements fit(series) and predict(horizon), so a new model (SARIMAX in DFS-15) is added
by writing one class and listing it in MODELS.
"""

import math
import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

MONTH = "MONTH"
WEEK = "WEEK"
FREQUENCY = {MONTH: "MS", WEEK: "W-MON"}
SEASON_LENGTH = {MONTH: 12, WEEK: 52}
Z_80 = 1.2816
Z_95 = 1.96
OUTLIER_LIMIT = 3  # standard deviations


@dataclass
class Point:
    period: date
    forecast: float
    lower80: float
    upper80: float
    lower95: float
    upper95: float


class MovingAverage:
    name = "MA"

    def __init__(self, window: int = 3):
        self.window = window

    def fit(self, series: pd.Series) -> "MovingAverage":
        self._level = float(series.tail(self.window).mean())
        errors = series - series.rolling(self.window).mean().shift(1)
        self._sigma = _spread(errors.dropna())
        return self

    def predict(self, horizon: int) -> tuple[np.ndarray, float]:
        return np.full(horizon, self._level), self._sigma


class HoltWinters:
    name = "HW"

    def __init__(self, season_length: int):
        self.season_length = season_length

    def fit(self, series: pd.Series) -> "HoltWinters":
        if len(series) < 2 * self.season_length:
            raise ValueError("Holt-Winters needs two full seasons of history")
        # Seasonal swings normally grow with demand, but that form cannot handle zero-sales periods.
        seasonal = "mul" if (series > 0).all() else "add"
        model = ExponentialSmoothing(series.to_numpy(dtype=float), trend="add", damped_trend=True,
                                     seasonal=seasonal, seasonal_periods=self.season_length,
                                     initialization_method="estimated")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # optimiser notes; results are checked in predict
            self._fitted = model.fit()
        self._sigma = _spread(pd.Series(self._fitted.resid))
        return self

    def predict(self, horizon: int) -> tuple[np.ndarray, float]:
        values = np.asarray(self._fitted.forecast(horizon), dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Holt-Winters did not produce a usable forecast")
        return values, self._sigma


MODELS = {MovingAverage.name: lambda _: MovingAverage(), HoltWinters.name: HoltWinters}


def _spread(errors: pd.Series) -> float:
    return float(errors.std(ddof=1)) if len(errors) > 1 else 0.0


def demand_series(records: list[tuple[date, int]], granularity: str) -> pd.Series:
    """Totals demand per period across regions. Periods with no sales count as zero demand."""
    frame = pd.DataFrame(records, columns=["period", "quantity"])
    frame["period"] = pd.to_datetime(frame["period"])
    totals = frame.groupby(pd.Grouper(key="period", freq=FREQUENCY[granularity], closed="left",
                                      label="left"))["quantity"].sum()
    return totals.astype(float)


def clean(series: pd.Series) -> pd.Series:
    """Caps extreme one-off values, so a single unusual period does not distort the forecast."""
    if len(series) < 3:
        return series
    mean, spread = series.mean(), series.std(ddof=1)
    return series.clip(mean - OUTLIER_LIMIT * spread, mean + OUTLIER_LIMIT * spread)


def choose_model(length: int, granularity: str, allowed: list[str]) -> str:
    """Holt-Winters when there is enough history. Comparing models by accuracy comes in DFS-15."""
    if HoltWinters.name in allowed and length >= 2 * SEASON_LENGTH[granularity]:
        return HoltWinters.name
    return MovingAverage.name


def forecast_product(records: list[tuple[date, int]], horizon: int, granularity: str,
                     allowed: list[str]) -> tuple[str, list[Point]]:
    """Returns the model used and one point per future period. Falls back to moving average."""
    series = clean(demand_series(records, granularity))
    name = choose_model(len(series), granularity, allowed)
    try:
        values, sigma = MODELS[name](SEASON_LENGTH[granularity]).fit(series).predict(horizon)
    except (ValueError, np.linalg.LinAlgError):
        name = MovingAverage.name
        values, sigma = MovingAverage().fit(series).predict(horizon)

    offset = pd.tseries.frequencies.to_offset(FREQUENCY[granularity])
    periods = pd.date_range(series.index[-1] + offset, periods=horizon, freq=offset)
    return name, [_point(p, v, sigma, h) for h, (p, v) in enumerate(zip(periods, values), start=1)]


def _point(period: pd.Timestamp, value: float, sigma: float, step: int) -> Point:
    """Uncertainty grows with distance into the future. Demand can never be negative."""
    forecast = max(float(value), 0.0)
    spread = sigma * math.sqrt(step)
    return Point(
        period=period.date(),
        forecast=round(forecast, 2),
        lower80=round(max(forecast - Z_80 * spread, 0.0), 2),
        upper80=round(forecast + Z_80 * spread, 2),
        lower95=round(max(forecast - Z_95 * spread, 0.0), 2),
        upper95=round(forecast + Z_95 * spread, 2),
    )
