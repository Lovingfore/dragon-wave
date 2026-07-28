import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from model import (
    composite_risk,
    iso_now,
    outlook_7d,
    percent_change,
    safe_float,
    wwi_for_height,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "metrics.json"
LEVERAGE_PATH = ROOT / "data" / "leverage-history.json"

COIN_METRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
DAILY_METRICS = "PriceUSD,CapMrktCurUSD,CapMVRVCur,SplyCur,SplyExNtv,BlkCnt"


def fetch_json(url, attempts=3, timeout=35):
    headers = {
        "Accept": "application/json",
        "User-Agent": "DragonWave/1.0 (+https://github.com/)",
    }
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Unable to fetch {}: {}".format(url, last_error))


def fetch_text(url, attempts=3, timeout=25):
    headers = {"User-Agent": "DragonWave/1.0 (+https://github.com/)"}
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                return response.read().decode("utf-8").strip()
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Unable to fetch {}: {}".format(url, last_error))


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def coin_metrics_records(start_date):
    query = urlencode(
        {
            "assets": "btc",
            "metrics": DAILY_METRICS,
            "frequency": "1d",
            "start_time": start_date,
            "page_size": 10000,
        }
    )
    payload = fetch_json("{}?{}".format(COIN_METRICS_URL, query), attempts=4, timeout=60)
    return payload.get("data", [])


def get_tip_height():
    providers = (
        "https://mempool.space/api/blocks/tip/height",
        "https://blockchain.info/q/getblockcount",
    )
    for provider in providers:
        try:
            return int(fetch_text(provider))
        except (RuntimeError, TypeError, ValueError):
            continue
    return None


def live_price():
    providers = (
        ("Coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot"),
        ("CoinGecko", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"),
        ("Binance", "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"),
    )
    for name, url in providers:
        try:
            payload = fetch_json(url, attempts=1, timeout=15)
            if name == "Coinbase":
                value = safe_float(payload.get("data", {}).get("amount"))
            elif name == "CoinGecko":
                value = safe_float(payload.get("bitcoin", {}).get("usd"))
            else:
                value = safe_float(payload.get("price"))
            if value:
                return value, name
        except RuntimeError:
            continue
    return None, None


def aggregate_open_interest_btc():
    sources = []
    total = 0.0

    try:
        payload = fetch_json(
            "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
            attempts=1,
            timeout=15,
        )
        value = safe_float(payload.get("openInterest"))
        if value is not None:
            total += value
            sources.append("Binance")
    except RuntimeError:
        pass

    try:
        payload = fetch_json(
            "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1h&limit=1",
            attempts=1,
            timeout=15,
        )
        rows = payload.get("result", {}).get("list", [])
        value = safe_float(rows[0].get("openInterest")) if rows else None
        if value is not None:
            total += value
            sources.append("Bybit")
    except RuntimeError:
        pass

    try:
        payload = fetch_json(
            "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP",
            attempts=1,
            timeout=15,
        )
        rows = payload.get("data", [])
        value = safe_float(rows[0].get("oiCcy")) if rows else None
        if value is not None:
            total += value
            sources.append("OKX")
    except RuntimeError:
        pass

    if not sources:
        return None, []
    return total, sources


def merge_daily(existing, incoming):
    merged = {}
    for record in existing:
        date = record.get("date")
        if date:
            merged[date] = record
    for record in incoming:
        date = str(record.get("time", ""))[:10]
        if not date:
            continue
        merged[date] = {
            "date": date,
            "price": safe_float(record.get("PriceUSD")),
            "marketCap": safe_float(record.get("CapMrktCurUSD")),
            "mvrv": safe_float(record.get("CapMVRVCur")),
            "supply": safe_float(record.get("SplyCur")),
            "exchangeReserve": safe_float(record.get("SplyExNtv")),
            "blocks": safe_float(record.get("BlkCnt")),
        }
    return [merged[key] for key in sorted(merged)]


def welford_update(state, value):
    count, mean, m2 = state
    count += 1
    delta = value - mean
    mean += delta / count
    m2 += delta * (value - mean)
    return count, mean, m2


def leverage_by_date(history):
    mapping = {}
    for point in history:
        stamp = point.get("time", "")
        if len(stamp) >= 10 and point.get("value") is not None:
            mapping[stamp[:10]] = point.get("value")
    return mapping


def derive_series(raw_series, leverage_history):
    derived = []
    block_height = -1
    cap_state = (0, 0.0, 0.0)
    leverage_map = leverage_by_date(leverage_history)
    leverage_values = [point.get("value") for point in leverage_history if point.get("value") is not None]

    for raw in raw_series:
        blocks = raw.get("blocks")
        if blocks is not None:
            block_height += int(round(blocks))

        market_cap = raw.get("marketCap")
        mvrv = raw.get("mvrv")
        supply = raw.get("supply")
        price = raw.get("price")
        realized_cap = market_cap / mvrv if market_cap is not None and mvrv not in (None, 0) else None
        realized_price = realized_cap / supply if realized_cap is not None and supply not in (None, 0) else None
        nupl = 1.0 - 1.0 / mvrv if mvrv not in (None, 0) else None

        mvrv_z = None
        if market_cap is not None:
            cap_state = welford_update(cap_state, market_cap)
            count, _, m2 = cap_state
            standard_deviation = (m2 / count) ** 0.5 if count > 1 else None
            if standard_deviation not in (None, 0) and realized_cap is not None:
                mvrv_z = (market_cap - realized_cap) / standard_deviation

        wwi_data = wwi_for_height(max(0, block_height))
        values = {
            "price": price,
            "nupl": nupl,
            "realizedPrice": realized_price,
            "mvrv": mvrv,
            "mvrvZ": mvrv_z,
            "leverage": leverage_map.get(raw["date"]),
            "wwi": wwi_data["value"],
        }
        score, components = composite_risk(values, leverage_values)
        derived.append(
            {
                **raw,
                "blockHeight": max(0, block_height),
                "nupl": nupl,
                "realizedPrice": realized_price,
                "mvrvZ": mvrv_z,
                "leverage": values["leverage"],
                "wwi": wwi_data["value"],
                "wwiDirection": wwi_data["direction"],
                "riskScore": score,
                "riskComponents": components,
            }
        )
    return derived


def find_previous(series, days):
    if not series:
        return None
    target = datetime.strptime(series[-1]["date"], "%Y-%m-%d").date() - timedelta(days=days)
    candidates = [row for row in series if datetime.strptime(row["date"], "%Y-%m-%d").date() <= target]
    return candidates[-1] if candidates else None


def build_metric(value, one_day_value, seven_day_value, source_age="daily"):
    return {
        "value": value,
        "change1d": percent_change(value, one_day_value),
        "change7d": percent_change(value, seven_day_value),
        "sourceAge": source_age,
    }


def main():
    parser = argparse.ArgumentParser(description="Update Dragon Wave market data")
    parser.add_argument("--full", action="store_true", help="Fetch all historical daily data")
    parser.add_argument(
        "--daily-only",
        action="store_true",
        help="Skip live exchange endpoints when generating a local preview",
    )
    args = parser.parse_args()

    existing = read_json(DATA_PATH, {})
    existing_series = existing.get("series", [])
    if args.full or not existing_series:
        start_date = "2009-01-03"
    else:
        last_date = datetime.strptime(existing_series[-1]["date"], "%Y-%m-%d").date()
        start_date = (last_date - timedelta(days=14)).isoformat()

    incoming = coin_metrics_records(start_date)
    raw_series = merge_daily(existing_series, incoming)
    if not raw_series:
        raise RuntimeError("Coin Metrics returned no usable daily records")

    leverage_history = read_json(LEVERAGE_PATH, [])
    exchange_reserve = raw_series[-1].get("exchangeReserve")
    if args.daily_only:
        open_interest, oi_sources = None, []
    else:
        open_interest, oi_sources = aggregate_open_interest_btc()
    leverage_value = None
    if open_interest is not None and exchange_reserve not in (None, 0):
        leverage_value = open_interest / exchange_reserve
        leverage_history.append({"time": iso_now(), "value": leverage_value, "sources": oi_sources})
        cutoff = datetime.now(timezone.utc) - timedelta(days=3650)
        leverage_history = [
            point
            for point in leverage_history
            if datetime.fromisoformat(point["time"].replace("Z", "+00:00")) >= cutoff
        ]
        write_json(LEVERAGE_PATH, leverage_history)
    elif leverage_history:
        leverage_value = leverage_history[-1].get("value")
        oi_sources = leverage_history[-1].get("sources", [])

    series = derive_series(raw_series, leverage_history)
    latest = series[-1]
    one_day = find_previous(series, 1) or latest
    seven_day = find_previous(series, 7) or latest

    spot_price, spot_source = (None, None) if args.daily_only else live_price()
    current_price = spot_price or latest.get("price")
    live_ratio = current_price / latest["price"] if current_price and latest.get("price") else 1.0
    current_mvrv = latest.get("mvrv") * live_ratio if latest.get("mvrv") is not None else None
    current_nupl = 1.0 - 1.0 / current_mvrv if current_mvrv not in (None, 0) else None
    current_market_cap = latest.get("marketCap") * live_ratio if latest.get("marketCap") is not None else None
    current_mvrv_z = latest.get("mvrvZ")
    if current_market_cap and latest.get("marketCap") and latest.get("mvrvZ") is not None:
        realized_cap = latest["marketCap"] / latest["mvrv"]
        historical_numerator = latest["marketCap"] - realized_cap
        if historical_numerator:
            current_mvrv_z = latest["mvrvZ"] * (current_market_cap - realized_cap) / historical_numerator

    tip_height = get_tip_height() or latest.get("blockHeight", 0)
    current_wwi = wwi_for_height(tip_height)
    future_wwi = wwi_for_height(tip_height + 7 * 144)

    current_values = {
        "price": current_price,
        "nupl": current_nupl,
        "realizedPrice": latest.get("realizedPrice"),
        "mvrv": current_mvrv,
        "mvrvZ": current_mvrv_z,
        "leverage": leverage_value,
        "wwi": current_wwi["value"],
    }
    leverage_values = [point.get("value") for point in leverage_history if point.get("value") is not None]
    current_risk, risk_components = composite_risk(current_values, leverage_values)
    recent_risks = [row.get("riskScore") for row in series[-7:]]
    outlook = outlook_7d(current_risk, recent_risks, future_wwi["value"])

    current = {
        "price": build_metric(current_price, one_day.get("price"), seven_day.get("price"), "live" if spot_price else "daily"),
        "nupl": build_metric(current_nupl, one_day.get("nupl"), seven_day.get("nupl")),
        "realizedPrice": build_metric(latest.get("realizedPrice"), one_day.get("realizedPrice"), seven_day.get("realizedPrice")),
        "mvrv": build_metric(current_mvrv, one_day.get("mvrv"), seven_day.get("mvrv")),
        "mvrvZ": build_metric(current_mvrv_z, one_day.get("mvrvZ"), seven_day.get("mvrvZ")),
        "leverage": build_metric(leverage_value, None, None, "live" if open_interest is not None else "cached"),
        "wwi": build_metric(current_wwi["value"], one_day.get("wwi"), seven_day.get("wwi"), "block"),
    }

    payload = {
        "schemaVersion": 1,
        "metadata": {
            "generatedAt": iso_now(),
            "dailyDataDate": latest["date"],
            "spotSource": spot_source or "Coin Metrics",
            "openInterestSources": oi_sources,
            "dataQuality": "complete" if leverage_value is not None else "partial",
        },
        "current": current,
        "cycle": {
            "blockHeight": tip_height,
            "direction": current_wwi["direction"],
            "phase": current_wwi["phase"],
            "future7d": future_wwi,
        },
        "assessment": {
            "riskScore": current_risk,
            "components": risk_components,
            "outlook7d": outlook,
        },
        "series": series,
        "leverageSeries": leverage_history,
        "sources": [
            {"name": "Coin Metrics Community", "use": "价格、链上估值、交易所储备、区块统计"},
            {"name": "Mempool.space / Blockchain.com", "use": "最新区块高度"},
            {"name": "Binance / Bybit / OKX", "use": "公开未平仓合约量"},
        ],
    }
    write_json(DATA_PATH, payload)
    print("Updated {} daily rows; latest {}".format(len(series), latest["date"]))
    if leverage_value is None:
        print("Warning: live leverage sources were unavailable; using cached value", file=sys.stderr)


if __name__ == "__main__":
    main()
