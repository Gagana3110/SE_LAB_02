
"""Forecasting calculations for MA, Holt-Winters and SARIMAX.

DFS-15 additions:
- SARIMAX forecasting with optional market indicators.
- Three-period rolling-origin holdout backtesting.
- MAPE, MAE and bias calculation.
- Best-model selection using the lowest MAPE.
- Moving Average fallback for short histories.

The original public interfaces are retained for compatibility.
"""

import math
import warnings
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

MONTH = "MONTH"
WEEK = "WEEK"

FREQUENCY = {
    MONTH: "MS",
    WEEK: "W-MON",
}

SEASON_LENGTH = {
    MONTH: 12,
    WEEK: 52,
}

Z_80 = 1.2816
Z_95 = 1.96
OUTLIER_LIMIT = 3

SUPPORTED_MODELS = ("MA", "HW", "SARIMAX")
MIN_HISTORY_FOR_MODEL_SELECTION = 12
BACKTEST_PERIODS = 3


# ---------------------------------------------------------
# Data classes
# ---------------------------------------------------------

@dataclass
class Point:
    period: date
    forecast: float
    lower80: float
    upper80: float
    lower95: float
    upper95: float


@dataclass
class ForecastMetrics:
    model: str
    mape: Optional[float]
    mae: Optional[float]
    bias: Optional[float]
    confidence: str


@dataclass
class BacktestResult:
    model: str
    mape: Optional[float]
    mae: Optional[float]
    bias: Optional[float]
    predictions: list[float]
    actuals: list[float]


# ---------------------------------------------------------
# Existing utility functions
# ---------------------------------------------------------

def _spread(errors: pd.Series) -> float:
    return float(errors.std(ddof=1)) if len(errors) > 1 else 0.0


def demand_series(
    records: list[tuple[date, int]],
    granularity: str,
) -> pd.Series:
    """Aggregate sales by period and fill missing periods with zero."""

    if granularity not in FREQUENCY:
        raise ValueError(f"Unsupported granularity: {granularity}")

    frame = pd.DataFrame(records, columns=["period", "quantity"])

    if frame.empty:
        raise ValueError("No sales history available.")

    frame["period"] = pd.to_datetime(frame["period"])
    frame["quantity"] = pd.to_numeric(
        frame["quantity"], errors="coerce"
    ).fillna(0.0)

    totals = (
        frame.groupby(
            pd.Grouper(
                key="period",
                freq=FREQUENCY[granularity],
                closed="left",
                label="left",
            )
        )["quantity"]
        .sum()
    )

    if totals.empty:
        raise ValueError("No valid demand periods found.")

    full_index = pd.date_range(
        start=totals.index.min(),
        end=totals.index.max(),
        freq=FREQUENCY[granularity],
    )

    return totals.reindex(full_index, fill_value=0.0).astype(float)


def clean(series: pd.Series) -> pd.Series:
    """Cap extreme observations using three standard deviations."""

    if len(series) < 3:
        return series.copy()

    mean = series.mean()
    spread = series.std(ddof=1)

    if not np.isfinite(spread) or spread == 0:
        return series.copy()

    return series.clip(
        mean - OUTLIER_LIMIT * spread,
        mean + OUTLIER_LIMIT * spread,
    )


# ---------------------------------------------------------
# Moving Average
# ---------------------------------------------------------

class MovingAverage:
    name = "MA"

    def __init__(self, window: int = 3):
        self.window = window

    def fit(self, series: pd.Series) -> "MovingAverage":
        if len(series) == 0:
            raise ValueError("Moving Average requires historical data.")

        self._level = float(series.tail(self.window).mean())

        errors = series - series.rolling(
            self.window
        ).mean().shift(1)

        self._sigma = _spread(errors.dropna())

        return self

    def predict(self, horizon: int) -> tuple[np.ndarray, float]:
        return np.full(horizon, self._level), self._sigma


# ---------------------------------------------------------
# Holt-Winters
# ---------------------------------------------------------

class HoltWinters:
    name = "HW"

    def __init__(self, season_length: int):
        self.season_length = season_length

    def fit(self, series: pd.Series) -> "HoltWinters":
        if len(series) < 2 * self.season_length:
            raise ValueError(
                "Holt-Winters needs two full seasons of history."
            )

        seasonal = "mul" if (series > 0).all() else "add"

        model = ExponentialSmoothing(
            series.to_numpy(dtype=float),
            trend="add",
            damped_trend=True,
            seasonal=seasonal,
            seasonal_periods=self.season_length,
            initialization_method="estimated",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fitted = model.fit()

        self._sigma = _spread(pd.Series(self._fitted.resid))

        return self

    def predict(self, horizon: int) -> tuple[np.ndarray, float]:
        values = np.asarray(
            self._fitted.forecast(horizon),
            dtype=float,
        )

        if not np.isfinite(values).all():
            raise ValueError(
                "Holt-Winters did not produce a usable forecast."
            )

        return values, self._sigma


# ---------------------------------------------------------
# SARIMAX
# ---------------------------------------------------------

class SARIMAXModel:
    name = "SARIMAX"

    def fit(
        self,
        series: pd.Series,
        exog: Optional[pd.DataFrame] = None,
    ) -> "SARIMAXModel":

        if len(series) < 6:
            raise ValueError(
                "SARIMAX requires at least 6 historical periods."
            )

        self.exog_columns = None
        self._exog = None

        if exog is not None and not exog.empty:
            exog = exog.copy()
            exog.index = pd.to_datetime(exog.index)
            exog = exog.reindex(series.index)
            exog = exog.apply(pd.to_numeric, errors="coerce")
            exog = exog.fillna(0.0)

            self.exog_columns = list(exog.columns)
            self._exog = exog.astype(float)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            model = SARIMAX(
                series.astype(float),
                exog=self._exog,
                order=(1, 1, 1),
                seasonal_order=(0, 0, 0, 0),
                enforce_stationarity=False,
                enforce_invertibility=False,
            )

            self._fitted = model.fit(disp=False)

        self._sigma = _spread(
            pd.Series(self._fitted.resid)
        )

        return self

    def predict(
        self,
        horizon: int,
        future_exog: Optional[pd.DataFrame] = None,
    ) -> tuple[np.ndarray, float]:

        if self.exog_columns is None:
            forecast = self._fitted.get_forecast(
                steps=horizon
            )
        else:
            if future_exog is None or future_exog.empty:
                last_values = self._exog.iloc[-1].to_numpy()

                future_exog = pd.DataFrame(
                    np.tile(last_values, (horizon, 1)),
                    columns=self.exog_columns,
                )
            else:
                future_exog = future_exog.copy()
                future_exog = future_exog.reindex(
                    columns=self.exog_columns
                ).fillna(0.0)

                if len(future_exog) != horizon:
                    raise ValueError(
                        "Future indicators must match forecast horizon."
                    )

            forecast = self._fitted.get_forecast(
                steps=horizon,
                exog=future_exog,
            )

        values = np.asarray(
            forecast.predicted_mean,
            dtype=float,
        )

        if not np.isfinite(values).all():
            raise ValueError("SARIMAX produced invalid predictions.")

        return values, self._sigma


# ---------------------------------------------------------
# Model registry
# ---------------------------------------------------------

MODELS = {
    MovingAverage.name: lambda season: MovingAverage(),
    HoltWinters.name: HoltWinters,
    SARIMAXModel.name: lambda season: SARIMAXModel(),
}


def _make_model(name: str, granularity: str):
    if name not in MODELS:
        raise ValueError(f"Unsupported forecasting model: {name}")

    return MODELS[name](SEASON_LENGTH[granularity])


def _validate_models(allowed: Sequence[str]) -> list[str]:
    result = []

    for name in allowed:
        name = str(name).upper()

        if name not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported forecasting model: {name}")

        if name not in result:
            result.append(name)

    return result or ["MA"]


# ---------------------------------------------------------
# Forecast intervals
# ---------------------------------------------------------

def _point(
    period: pd.Timestamp,
    value: float,
    sigma: float,
    step: int,
) -> Point:

    forecast = max(float(value), 0.0)
    spread = max(float(sigma), 0.0) * math.sqrt(step)

    return Point(
        period=period.date(),
        forecast=round(forecast, 2),
        lower80=round(max(forecast - Z_80 * spread, 0.0), 2),
        upper80=round(forecast + Z_80 * spread, 2),
        lower95=round(max(forecast - Z_95 * spread, 0.0), 2),
        upper95=round(forecast + Z_95 * spread, 2),
    )


# ---------------------------------------------------------
# Original model selection - retained for compatibility
# ---------------------------------------------------------

def choose_model(
    length: int,
    granularity: str,
    allowed: list[str],
) -> str:

    if (
        HoltWinters.name in allowed
        and length >= 2 * SEASON_LENGTH[granularity]
    ):
        return HoltWinters.name

    return MovingAverage.name


# ---------------------------------------------------------
# Metrics
# ---------------------------------------------------------

def calculate_metrics(
    actuals: Sequence[float],
    predictions: Sequence[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return MAPE (%), MAE and bias (prediction minus actual)."""

    actual = np.asarray(actuals, dtype=float)
    predicted = np.asarray(predictions, dtype=float)

    if len(actual) == 0 or len(actual) != len(predicted):
        return None, None, None

    errors = predicted - actual

    mae = float(np.mean(np.abs(errors)))
    bias = float(np.mean(errors))

    nonzero = actual != 0

    if np.any(nonzero):
        mape = float(
            np.mean(
                np.abs(errors[nonzero] / actual[nonzero])
            ) * 100
        )
    else:
        mape = None

    return mape, mae, bias


# ---------------------------------------------------------
# Market indicator preparation
# ---------------------------------------------------------

def prepare_indicators(
    indicators: Optional[pd.DataFrame],
    index: pd.Index,
) -> Optional[pd.DataFrame]:

    if indicators is None or indicators.empty:
        return None

    frame = indicators.copy()

    if "period" in frame.columns:
        frame["period"] = pd.to_datetime(frame["period"])
        frame = frame.set_index("period")
    else:
        frame.index = pd.to_datetime(frame.index)

    frame = frame.reindex(index)

    for column in frame.columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    return frame.fillna(0.0).astype(float)


# ---------------------------------------------------------
# Backtesting
# ---------------------------------------------------------

def backtest_model(
    series: pd.Series,
    model_name: str,
    granularity: str,
    indicators: Optional[pd.DataFrame] = None,
) -> Optional[BacktestResult]:

    if len(series) <= BACKTEST_PERIODS:
        return None

    train = series.iloc[:-BACKTEST_PERIODS]
    test = series.iloc[-BACKTEST_PERIODS:]

    historical_exog = prepare_indicators(
        indicators,
        series.index,
    )

    train_exog = (
        historical_exog.iloc[:-BACKTEST_PERIODS]
        if historical_exog is not None
        else None
    )

    test_exog = (
        historical_exog.iloc[-BACKTEST_PERIODS:]
        if historical_exog is not None
        else None
    )

    try:
        model = _make_model(model_name, granularity)
        train_clean = clean(train)

        if model_name == "SARIMAX":
            model.fit(train_clean, exog=train_exog)
            predictions, _ = model.predict(
                BACKTEST_PERIODS,
                future_exog=test_exog,
            )
        else:
            model.fit(train_clean)
            predictions, _ = model.predict(BACKTEST_PERIODS)

        predictions = np.maximum(predictions, 0.0)

        mape, mae, bias = calculate_metrics(
            test.to_numpy(),
            predictions,
        )

        return BacktestResult(
            model=model_name,
            mape=mape,
            mae=mae,
            bias=bias,
            predictions=predictions.tolist(),
            actuals=test.to_numpy().tolist(),
        )

    except Exception:
        return None


def backtest_models(
    series: pd.Series,
    granularity: str,
    allowed: Sequence[str],
    indicators: Optional[pd.DataFrame] = None,
) -> list[BacktestResult]:

    results = []

    for name in _validate_models(allowed):
        result = backtest_model(
            series,
            name,
            granularity,
            indicators,
        )

        if result is not None:
            results.append(result)

    return results


def select_best_model(
    results: Sequence[BacktestResult],
) -> Optional[BacktestResult]:

    if not results:
        return None

    with_mape = [
        result for result in results
        if result.mape is not None
    ]

    if with_mape:
        return min(with_mape, key=lambda item: item.mape)

    with_mae = [
        result for result in results
        if result.mae is not None
    ]

    if with_mae:
        return min(with_mae, key=lambda item: item.mae)

    return results[0]


# ---------------------------------------------------------
# DFS-15 enhanced forecasting interface
# ---------------------------------------------------------

def forecast_product_with_metrics(
    records: list[tuple[date, int]],
    horizon: int,
    granularity: str,
    allowed: list[str],
    indicators: Optional[pd.DataFrame] = None,
    future_indicators: Optional[pd.DataFrame] = None,
) -> tuple[str, list[Point], ForecastMetrics]:

    if horizon < 1:
        raise ValueError("Forecast horizon must be at least 1.")

    series = demand_series(records, granularity)
    allowed_models = _validate_models(allowed)

    selected_result = None

    if len(series) < MIN_HISTORY_FOR_MODEL_SELECTION:
        selected_name = "MA"
        confidence = "Low confidence"
    else:
        confidence = "Normal"

        results = backtest_models(
            series,
            granularity,
            allowed_models,
            indicators,
        )

        selected_result = select_best_model(results)

        selected_name = (
            selected_result.model
            if selected_result is not None
            else "MA"
        )

    model = _make_model(selected_name, granularity)
    full_series = clean(series)

    historical_exog = prepare_indicators(
        indicators,
        series.index,
    )

    if selected_name == "SARIMAX":
        model.fit(full_series, exog=historical_exog)

        if future_indicators is not None:
            future_exog = future_indicators.copy()
            future_exog = future_exog.apply(
                pd.to_numeric,
                errors="coerce",
            ).fillna(0.0)
        else:
            future_exog = None

        values, sigma = model.predict(
            horizon,
            future_exog=future_exog,
        )
    else:
        model.fit(full_series)
        values, sigma = model.predict(horizon)

    offset = pd.tseries.frequencies.to_offset(
        FREQUENCY[granularity]
    )

    periods = pd.date_range(
        series.index[-1] + offset,
        periods=horizon,
        freq=offset,
    )

    points = [
        _point(period, value, sigma, step)
        for step, (period, value) in enumerate(
            zip(periods, values),
            start=1,
        )
    ]

    metrics = ForecastMetrics(
        model=selected_name,
        mape=selected_result.mape if selected_result else None,
        mae=selected_result.mae if selected_result else None,
        bias=selected_result.bias if selected_result else None,
        confidence=confidence,
    )

    return selected_name, points, metrics


# ---------------------------------------------------------
# Original interface - retained for existing service/tests
# ---------------------------------------------------------

def forecast_product(
    records: list[tuple[date, int]],
    horizon: int,
    granularity: str,
    allowed: list[str],
) -> tuple[str, list[Point]]:

    """Original two-value interface used by the existing service."""

    if horizon < 1:
        raise ValueError("Forecast horizon must be at least 1.")

    series = clean(demand_series(records, granularity))

    name = choose_model(
        len(series),
        granularity,
        allowed,
    )

    try:
        model = _make_model(name, granularity)
        values, sigma = model.fit(series).predict(horizon)

    except (ValueError, np.linalg.LinAlgError):
        name = MovingAverage.name
        values, sigma = MovingAverage().fit(series).predict(horizon)

    offset = pd.tseries.frequencies.to_offset(
        FREQUENCY[granularity]
    )

    periods = pd.date_range(
        series.index[-1] + offset,
        periods=horizon,
        freq=offset,
    )

    points = [
        _point(period, value, sigma, step)
        for step, (period, value) in enumerate(
            zip(periods, values),
            start=1,
        )
    ]

    return name, points
