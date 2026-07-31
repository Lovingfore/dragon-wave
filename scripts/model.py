import math
from datetime import datetime, timedelta, timezone


METRIC_KEYS = (
    "price",
    "nupl",
    "realizedPrice",
    "mvrv",
    "mvrvZ",
    "wwi",
)

BEAR_MARKET_WINDOWS = (
    ("2011-06-01", "2012-11-28"),
    ("2013-12-01", "2016-07-09"),
    ("2017-12-01", "2020-05-11"),
    ("2021-11-01", "2024-04-20"),
)


def clamp(value, lower=0.0, upper=100.0):
    return max(lower, min(upper, value))


def safe_float(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _median(values):
    usable = sorted(value for value in values if value is not None)
    if not usable:
        return None
    middle = len(usable) // 2
    if len(usable) % 2:
        return usable[middle]
    return (usable[middle - 1] + usable[middle]) / 2.0


def _recency_weighted_mean(values):
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    weights = range(1, len(usable) + 1)
    total_weight = sum(weights)
    return sum(value * weight for value, weight in zip(usable, weights)) / total_weight


def _bear_market_bottoms(series):
    bottoms = []
    for start, end in BEAR_MARKET_WINDOWS:
        candidates = [
            row
            for row in series
            if start <= row.get("date", "") <= end
            and safe_float(row.get("price")) is not None
        ]
        bottoms.append(
            min(candidates, key=lambda row: safe_float(row.get("price")))
            if candidates
            else None
        )
    return bottoms


def percent_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def wwi_for_height(height):
    phase = (int(height) + 78750) % 210000
    if phase < 157500:
        return {
            "value": phase / 157500.0,
            "direction": "rising",
            "phase": "bull",
        }
    return {
        "value": 1.0 - (phase - 157500) / 52500.0,
        "direction": "falling",
        "phase": "bear",
    }


def _linear_score(value, low, high):
    if value is None:
        return None
    return clamp((value - low) / (high - low) * 100.0)


def component_scores(values):
    price = values.get("price")
    realized_price = values.get("realizedPrice")
    price_ratio = None
    if price is not None and realized_price not in (None, 0):
        price_ratio = price / realized_price

    return {
        "nupl": _linear_score(values.get("nupl"), -0.15, 0.75),
        "mvrv": _linear_score(values.get("mvrv"), 0.75, 3.75),
        "mvrvZ": _linear_score(values.get("mvrvZ"), -0.5, 7.5),
        "priceToRealized": _linear_score(price_ratio, 0.8, 3.2),
        "wwi": _linear_score(values.get("wwi"), 0.0, 1.0),
    }


def composite_risk(values):
    scores = component_scores(values)
    core_keys = ("nupl", "mvrv", "mvrvZ", "priceToRealized", "wwi")
    if sum(scores[key] is not None for key in core_keys) < 4:
        return None, scores
    weights = {
        "nupl": 0.18,
        "mvrv": 0.17,
        "mvrvZ": 0.22,
        "priceToRealized": 0.13,
        "wwi": 0.18,
    }
    weighted = [(scores[key], weight) for key, weight in weights.items() if scores[key] is not None]
    if not weighted:
        return None, scores
    total_weight = sum(weight for _, weight in weighted)
    risk = sum(score * weight for score, weight in weighted) / total_weight
    return round(risk, 1), scores


def bottom_forecast(series, current, block_height, daily_data_date=None):
    value_keys = (
        "price",
        "nupl",
        "realizedPrice",
        "mvrv",
        "mvrvZ",
        "wwi",
        "riskScore",
    )
    if not series:
        return {
            "values": {key: None for key in value_keys},
            "asOf": daily_data_date,
            "targetDate": None,
        }

    bottoms = _bear_market_bottoms(series)
    latest_row = next(
        (
            row
            for row in reversed(series)
            if safe_float(row.get("realizedPrice")) is not None
        ),
        None,
    )
    latest_date = (latest_row or {}).get("date") or daily_data_date
    latest_bottom_date = next(
        (row["date"] for row in reversed(bottoms) if row),
        None,
    )
    current_cycle_rows = [
        row
        for row in series
        if (not latest_bottom_date or row.get("date", "") >= latest_bottom_date)
        and safe_float(row.get("price")) is not None
    ]
    current_top = (
        max(current_cycle_rows, key=lambda row: safe_float(row.get("price")))
        if current_cycle_rows
        else None
    )
    forecast_rows = [
        row
        for row in series
        if not current_top or row.get("date", "") >= current_top["date"]
    ]

    height = safe_float(
        block_height
        if block_height is not None
        else (latest_row or {}).get("blockHeight")
    )
    phase = (height + 78750) % 210000 if height is not None else None
    blocks_to_bottom = (210000 - phase) % 210000 if phase is not None else 0
    month_start = latest_date[:8] + "01" if latest_date else None
    recent_blocks = [
        safe_float(row.get("blocks"))
        for row in series
        if month_start and row.get("date", "") >= month_start
    ]
    recent_blocks = [
        value for value in recent_blocks if value is not None and value > 0
    ]
    average_blocks_per_day = (
        sum(recent_blocks) / len(recent_blocks) if recent_blocks else 144
    )
    days_to_bottom = (
        blocks_to_bottom / average_blocks_per_day
        if average_blocks_per_day > 0
        else 0
    )
    target_date = None
    if latest_date:
        target = datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(
            days=math.floor(days_to_bottom + 0.5)
        )
        target_date = target.strftime("%Y-%m-%d")

    def historical_values(key):
        return [
            safe_float(row.get(key))
            for row in bottoms
            if row and safe_float(row.get(key)) is not None
        ]

    expected_mvrv_baseline = _recency_weighted_mean(
        historical_values("mvrv")
    )
    expected_mvrv_z = _recency_weighted_mean(historical_values("mvrvZ"))
    expected_wwi = _recency_weighted_mean(historical_values("wwi"))
    current_cycle_mvrv = [
        safe_float(row.get("mvrv"))
        for row in forecast_rows
        if safe_float(row.get("mvrv")) is not None
    ]
    if expected_mvrv_baseline is None:
        expected_mvrv = None
    elif current_cycle_mvrv:
        expected_mvrv = min(expected_mvrv_baseline, min(current_cycle_mvrv))
    else:
        expected_mvrv = expected_mvrv_baseline

    realized_rows = [
        row
        for row in series
        if safe_float(row.get("realizedPrice")) is not None
    ]
    trend_start = (
        realized_rows[max(0, len(realized_rows) - 181)]
        if realized_rows
        else None
    )
    trend_end = realized_rows[-1] if realized_rows else None
    trend_days = 0
    if trend_start and trend_end:
        trend_days = max(
            1,
            (
                datetime.strptime(trend_end["date"], "%Y-%m-%d")
                - datetime.strptime(trend_start["date"], "%Y-%m-%d")
            ).days,
        )
    trend_rate = 0.0
    trend_start_value = safe_float(
        trend_start.get("realizedPrice") if trend_start else None
    )
    trend_end_value = safe_float(
        trend_end.get("realizedPrice") if trend_end else None
    )
    if (
        trend_days
        and trend_start_value is not None
        and trend_start_value > 0
        and trend_end_value is not None
        and trend_end_value > 0
    ):
        trend_rate = max(
            -0.001,
            min(
                0.001,
                math.log(trend_end_value / trend_start_value) / trend_days,
            ),
        )

    current_realized_price = safe_float(
        current.get("realizedPrice", {}).get("value")
    )
    if current_realized_price is None and latest_row:
        current_realized_price = safe_float(latest_row.get("realizedPrice"))
    projected_days = min(540, max(0, days_to_bottom))
    expected_realized_price = (
        current_realized_price * math.exp(trend_rate * projected_days)
        if current_realized_price is not None
        else None
    )
    expected_price = (
        expected_realized_price * expected_mvrv
        if expected_realized_price is not None and expected_mvrv is not None
        else _median(historical_values("price"))
    )
    expected_nupl = (
        1 - 1 / expected_mvrv
        if expected_mvrv is not None and expected_mvrv > 0
        else None
    )
    expected_risk_score, _ = composite_risk(
        {
            "price": expected_price,
            "nupl": expected_nupl,
            "realizedPrice": expected_realized_price,
            "mvrv": expected_mvrv,
            "mvrvZ": expected_mvrv_z,
            "wwi": expected_wwi,
        }
    )
    return {
        "values": {
            "price": expected_price,
            "nupl": expected_nupl,
            "realizedPrice": expected_realized_price,
            "mvrv": expected_mvrv,
            "mvrvZ": expected_mvrv_z,
            "wwi": expected_wwi,
            "riskScore": expected_risk_score,
        },
        "asOf": daily_data_date or latest_date,
        "targetDate": target_date,
    }


def risk_state(score):
    if score is None:
        return {"key": "unavailable", "label": "数据不足", "tone": "muted"}
    if score >= 85:
        return {"key": "near_top", "label": "接近牛市顶部", "tone": "danger"}
    if score >= 70:
        return {"key": "top_risk", "label": "顶部风险升高", "tone": "warning"}
    if score <= 15:
        return {"key": "near_bottom", "label": "接近熊市底部", "tone": "positive"}
    if score <= 30:
        return {"key": "bottom_watch", "label": "底部区间观察", "tone": "info"}
    return {"key": "neutral", "label": "周期中性区间", "tone": "neutral"}


def _slope(points):
    usable = [point for point in points if point is not None]
    if len(usable) < 2:
        return 0.0
    count = len(usable)
    xs = list(range(count))
    x_mean = sum(xs) / count
    y_mean = sum(usable) / count
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, usable)) / denominator


def outlook_7d(current_score, recent_scores, future_wwi=None):
    if current_score is None:
        return {
            "key": "unavailable",
            "label": "暂无法形成七日判断",
            "detail": "有效指标不足，等待下一次数据更新。",
        }

    slope = _slope(recent_scores[-7:])
    projected = clamp(current_score + slope * 7.0)
    if current_score >= 85 or projected >= 85:
        return {
            "key": "near_top",
            "label": "未来七日接近顶部的风险较高",
            "detail": "综合估值与周期信号已进入顶部警戒范围。",
        }
    if current_score <= 15 or projected <= 15:
        return {
            "key": "near_bottom",
            "label": "未来七日接近底部的可能性较高",
            "detail": "综合估值与周期信号已进入底部观察范围。",
        }
    if current_score >= 70 or slope >= 1.2:
        return {
            "key": "top_rising",
            "label": "未来七日顶部风险仍在上升",
            "detail": "尚未确认到达顶部，但风险分位正在抬升。",
        }
    if current_score <= 30 or slope <= -1.2:
        return {
            "key": "bottom_falling",
            "label": "未来七日继续向底部区间靠近",
            "detail": "尚未确认到达底部，但风险分位正在下降。",
        }
    if future_wwi is not None and future_wwi >= 0.85:
        return {
            "key": "cycle_top_watch",
            "label": "未来七日关注周期顶部信号",
            "detail": "狼波周期指数接近理论顶部，其他指标尚未形成共振。",
        }
    if future_wwi is not None and future_wwi <= 0.15:
        return {
            "key": "cycle_bottom_watch",
            "label": "未来七日关注周期底部信号",
            "detail": "狼波周期指数接近理论底部，其他指标尚未形成共振。",
        }
    return {
        "key": "neutral",
        "label": "未来七日未见明确顶部或底部信号",
        "detail": "指标组合仍处于中性区间，继续观察趋势变化。",
    }


def iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def beijing_now():
    return datetime.now(timezone(timedelta(hours=8)))
