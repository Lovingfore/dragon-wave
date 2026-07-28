import math
from datetime import datetime, timedelta, timezone


METRIC_KEYS = (
    "price",
    "nupl",
    "realizedPrice",
    "mvrv",
    "mvrvZ",
    "leverage",
    "wwi",
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


def percent_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def percentile_rank(values, current):
    usable = sorted(value for value in values if value is not None and math.isfinite(value))
    if current is None or not usable:
        return None
    below = sum(1 for value in usable if value < current)
    equal = sum(1 for value in usable if value == current)
    return 100.0 * (below + 0.5 * equal) / len(usable)


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


def component_scores(values, leverage_history=None):
    price = values.get("price")
    realized_price = values.get("realizedPrice")
    price_ratio = None
    if price is not None and realized_price not in (None, 0):
        price_ratio = price / realized_price

    leverage_values = leverage_history or []
    leverage_score = percentile_rank(leverage_values, values.get("leverage"))

    return {
        "nupl": _linear_score(values.get("nupl"), -0.15, 0.75),
        "mvrv": _linear_score(values.get("mvrv"), 0.75, 3.75),
        "mvrvZ": _linear_score(values.get("mvrvZ"), -0.5, 7.5),
        "priceToRealized": _linear_score(price_ratio, 0.8, 3.2),
        "wwi": _linear_score(values.get("wwi"), 0.0, 1.0),
        "leverage": leverage_score,
    }


def composite_risk(values, leverage_history=None):
    scores = component_scores(values, leverage_history)
    weights = {
        "nupl": 0.18,
        "mvrv": 0.17,
        "mvrvZ": 0.22,
        "priceToRealized": 0.13,
        "wwi": 0.18,
        "leverage": 0.12,
    }
    weighted = [(scores[key], weight) for key, weight in weights.items() if scores[key] is not None]
    if not weighted:
        return None, scores
    total_weight = sum(weight for _, weight in weighted)
    risk = sum(score * weight for score, weight in weighted) / total_weight
    return round(risk, 1), scores


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
