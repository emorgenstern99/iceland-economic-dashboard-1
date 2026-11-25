"""Live data pipeline for the Iceland Macroeconomic Monitor.

Retrieves primary macroeconomic indicators directly from:
1. Statistics Iceland (Hagstofa Íslands) PxWeb API v1
2. Central Bank of Iceland (Seðlabanki Íslands) XML TimeSeries API

Stores normalized datasets, per-series metadata, and an append-only refresh log
in the local `data/` directory.
"""

from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATASET_PATH = DATA_DIR / "iceland_macro.json"
METADATA_PATH = DATA_DIR / "refresh_metadata.json"
REFRESH_LOG_PATH = DATA_DIR / "refresh_log.jsonl"

PX_BASE_URL = "https://px.hagstofa.is/pxen/api/v1/en"
CBI_XML_URL = "https://www.sedlabanki.is/xmltimeseries/Default.aspx"
HTTP_TIMEOUT = 30
HEADERS = {"User-Agent": "Iceland-Macro-Monitor/1.0 (FINC470)"}

START_YEAR_PX = 2014
START_DATE_CBI = "2015-01-01"


def _request_with_retry(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Execute an HTTP request with retry/backoff for PxWeb 429 rate limits."""
    max_attempts = 5
    for attempt in range(max_attempts):
        resp = requests.request(method, url, headers=HEADERS, timeout=HTTP_TIMEOUT, **kwargs)
        if resp.status_code in (429, 503) and attempt < max_attempts - 1:
            retry_after = resp.headers.get("Retry-After")
            wait_sec = float(retry_after) if retry_after and retry_after.isdigit() else 2.5 * (2 ** attempt)
            time.sleep(min(wait_sec, 20.0))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def _post_pxweb(table_path: str, query: list[dict[str, Any]]) -> dict[str, Any]:
    """Query a Statistics Iceland PxWeb table and return parsed JSON-stat2."""
    time.sleep(0.6)  # Polite pacing for Statistics Iceland PxWeb rate limit
    url = f"{PX_BASE_URL}/{table_path}"
    payload = {"query": query, "response": {"format": "json-stat2"}}
    resp = _request_with_retry("POST", url, json=payload)
    return resp.json()


def _fetch_cbi_series(series_id: int, start_date: str = START_DATE_CBI) -> list[dict[str, Any]]:
    """Fetch a single Central Bank of Iceland XML time series."""
    params = {
        "DagsFra": start_date,
        "TimeSeriesID": str(series_id),
        "Type": "xml",
    }
    resp = _request_with_retry("GET", CBI_XML_URL, params=params)
    root = ET.fromstring(resp.text)
    ts = root.find("TimeSeries")
    if ts is None:
        raise ValueError(f"CBI TimeSeriesID={series_id} missing <TimeSeries> node.")
    rows: list[dict[str, Any]] = []
    for entry in ts.findall("TimeSeriesData/Entry"):
        raw_date = entry.findtext("Date")
        raw_val = entry.findtext("Value")
        if not raw_date or raw_val is None or raw_val.strip() == "":
            continue
        dt = datetime.strptime(raw_date.strip(), "%m/%d/%Y %I:%M:%S %p")
        rows.append({"date": dt.strftime("%Y-%m-%d"), "value": float(raw_val)})
    rows.sort(key=lambda r: r["date"])
    return rows


def _jsonstat_to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
    """Flatten a JSON-stat2 response into a tidy DataFrame."""
    dim_ids: list[str] = data["id"]
    sizes: list[int] = data["size"]
    values: list[Any] = data["value"]

    dim_codes: list[list[str]] = []
    dim_labels: list[dict[str, str]] = []
    for dim_id in dim_ids:
        cat = data["dimension"][dim_id]["category"]
        idx = cat["index"]
        if isinstance(idx, dict):
            ordered = [k for k, _ in sorted(idx.items(), key=lambda kv: kv[1])]
        else:
            ordered = list(idx)
        dim_codes.append(ordered)
        dim_labels.append(cat.get("label", {k: k for k in ordered}))

    records: list[dict[str, Any]] = []
    total = 1
    for s in sizes:
        total *= s

    for flat_idx in range(total):
        rem = flat_idx
        coords: list[int] = [0] * len(sizes)
        for i in range(len(sizes) - 1, -1, -1):
            coords[i] = rem % sizes[i]
            rem //= sizes[i]
        row: dict[str, Any] = {}
        for i, dim_id in enumerate(dim_ids):
            code = dim_codes[i][coords[i]]
            row[dim_id] = code
            row[f"{dim_id}_label"] = dim_labels[i].get(code, code)
        row["value"] = values[flat_idx]
        records.append(row)

    return pd.DataFrame(records)


def _quarter_to_iso_date(quarter_str: str) -> str:
    """Convert 'YYYYQn' (e.g. '2026Q2') to quarter-end ISO date ('2026-06-30')."""
    year = int(quarter_str[:4])
    q = int(quarter_str[-1])
    month_end_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    m, d = month_end_day[q]
    return f"{year:04d}-{m:02d}-{d:02d}"


def _month_to_iso_date(month_str: str) -> str:
    """Convert 'YYYYMmm' (e.g. '2026M10') to first-of-month ISO date ('2026-10-01')."""
    year = int(month_str[:4])
    month = int(month_str[5:7])
    return f"{year:04d}-{month:02d}-01"


def fetch_real_gdp() -> dict[str, Any]:
    """Fetch Quarterly Real GDP growth (YoY % and QoQ % SA) from Statistics Iceland THJ01601."""
    table_path = "Efnahagur/thjodhagsreikningar/landsframl/2_landsframleidsla_arsfj/THJ01601.px"
    meta_url = f"{PX_BASE_URL}/{table_path}"
    raw = _post_pxweb(
        table_path,
        [
            {"code": "Mælikvarði", "selection": {"filter": "item", "values": ["1", "2", "3", "4"]}},
            {"code": "Skipting", "selection": {"filter": "item", "values": ["14"]}},
            {"code": "Ársfjórðungur", "selection": {"filter": "all", "values": ["*"]}},
        ],
    )
    df = _jsonstat_to_dataframe(raw)
    df = df[df["Ársfjórðungur"].str[:4].astype(int) >= START_YEAR_PX]
    piv = df.pivot(index="Ársfjórðungur", columns="Mælikvarði", values="value").reset_index()
    piv = piv.sort_values("Ársfjórðungur").reset_index(drop=True)
    piv["chain_vol"] = pd.to_numeric(piv["1"], errors="coerce")
    piv["yoy_pct"] = pd.to_numeric(piv["2"], errors="coerce")
    piv["chain_vol_sa"] = pd.to_numeric(piv["3"], errors="coerce")
    piv["qoq_sa_pct"] = pd.to_numeric(piv["4"], errors="coerce")
    piv["yoy_calc_pct"] = ((piv["chain_vol"] / piv["chain_vol"].shift(4)) - 1.0) * 100.0
    piv = piv[piv["Ársfjórðungur"] >= "2015Q1"].copy()

    records = [
        {
            "period": row["Ársfjórðungur"],
            "date": _quarter_to_iso_date(row["Ársfjórðungur"]),
            "yoy_pct": None if pd.isna(row["yoy_pct"]) else round(float(row["yoy_pct"]), 2),
            "qoq_sa_pct": None if pd.isna(row["qoq_sa_pct"]) else round(float(row["qoq_sa_pct"]), 2),
            "yoy_calc_pct": None if pd.isna(row["yoy_calc_pct"]) else round(float(row["yoy_calc_pct"]), 2),
            "chain_volume": None if pd.isna(row["chain_vol"]) else float(row["chain_vol"]),
        }
        for _, row in piv.iterrows()
    ]
    latest = records[-1]
    return {
        "id": "gdp",
        "name": "Real GDP Growth",
        "source": "Statistics Iceland (Hagstofa Íslands), Table THJ01601",
        "source_url": "https://px.hagstofa.is/pxen/pxweb/en/Efnahagur/thjodhagsreikningar__landsframl__2_landsframleidsla_arsfj/THJ01601.px",
        "api_url": meta_url,
        "frequency": "Quarterly",
        "units": "% (real chain-volume change)",
        "transformation": "YoY % = (RealGDP_t / RealGDP_{t-4} - 1) * 100; QoQ SA % = seasonally adjusted quarter-on-quarter chain-volume growth.",
        "latest_observation_date": latest["period"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["yoy_pct"],
        "latest_qoq_sa": latest["qoq_sa_pct"],
        "records": records,
    }


def fetch_cpi_inflation() -> dict[str, Any]:
    """Fetch Monthly CPI and YoY Inflation from Statistics Iceland VIS01000."""
    table_path = "Efnahagur/visitolur/1_vnv/1_vnv/VIS01000.px"
    meta_url = f"{PX_BASE_URL}/{table_path}"
    raw = _post_pxweb(
        table_path,
        [
            {"code": "Month", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Index", "selection": {"filter": "item", "values": ["CPI"]}},
            {"code": "Item", "selection": {"filter": "item", "values": ["index", "change_A", "change_M"]}},
        ],
    )
    df = _jsonstat_to_dataframe(raw)
    df = df[df["Month"].str[:4].astype(int) >= START_YEAR_PX]
    piv = df.pivot(index="Month", columns="Item", values="value").reset_index()
    piv = piv.sort_values("Month").reset_index(drop=True)
    piv["cpi_index"] = pd.to_numeric(piv["index"], errors="coerce")
    piv["yoy_published"] = pd.to_numeric(piv["change_A"], errors="coerce")
    piv["mom_published"] = pd.to_numeric(piv["change_M"], errors="coerce")
    piv["yoy_calc"] = ((piv["cpi_index"] / piv["cpi_index"].shift(12)) - 1.0) * 100.0

    piv = piv[piv["Month"] >= "2015M01"].copy()
    base_2015m01 = float(piv.iloc[0]["cpi_index"])
    piv["cpi_rebased_2015"] = (piv["cpi_index"] / base_2015m01) * 100.0

    records = [
        {
            "period": row["Month"],
            "date": _month_to_iso_date(row["Month"]),
            "cpi_index": round(float(row["cpi_index"]), 2),
            "cpi_rebased_2015": round(float(row["cpi_rebased_2015"]), 2),
            "yoy_pct": round(float(row["yoy_calc"]), 2),
            "yoy_published_pct": round(float(row["yoy_published"]), 2),
            "mom_pct": round(float(row["mom_published"]), 2),
        }
        for _, row in piv.iterrows()
    ]
    latest = records[-1]
    return {
        "id": "cpi",
        "name": "Consumer Price Index (CPI) & Inflation",
        "source": "Statistics Iceland (Hagstofa Íslands), Table VIS01000",
        "source_url": "https://px.hagstofa.is/pxen/pxweb/en/Efnahagur/visitolur__1_vnv__1_vnv/VIS01000.px",
        "api_url": meta_url,
        "frequency": "Monthly",
        "units": "% YoY and Index (May 1988 = 100; also shown rebased 2015M01 = 100)",
        "transformation": "12-month inflation computed as (CPI_t / CPI_{t-12} - 1) * 100 and cross-checked against Statistics Iceland published annual change; rebased index = (CPI_t / CPI_2015M01) * 100. CBI inflation target = 2.5%.",
        "latest_observation_date": latest["period"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["yoy_pct"],
        "latest_index": latest["cpi_index"],
        "records": records,
    }


def fetch_policy_rate() -> dict[str, Any]:
    """Fetch Central Bank of Iceland 7-Day Term Deposit Rate (TimeSeriesID=75)."""
    rows = _fetch_cbi_series(75, START_DATE_CBI)
    records: list[dict[str, Any]] = []
    prev_val: float | None = None
    for r in rows:
        is_change = prev_val is None or abs(r["value"] - prev_val) > 1e-9
        records.append(
            {
                "date": r["date"],
                "rate_pct": round(r["value"], 3),
                "is_decision_change": is_change,
            }
        )
        prev_val = r["value"]

    latest = records[-1]
    return {
        "id": "policy_rate",
        "name": "CBI Policy Interest Rate (7-Day Term Deposit Rate)",
        "source": "Central Bank of Iceland (Seðlabanki Íslands), TimeSeriesID=75 (matches Key Policy Rate ID=17923)",
        "source_url": "https://www.cb.is/monetary-policy/central-bank-interest-rates/",
        "api_url": f"{CBI_XML_URL}?DagsFra={START_DATE_CBI}&TimeSeriesID=75&Type=xml",
        "frequency": "Policy meeting / Daily effective step series",
        "units": "% per annum",
        "transformation": "Unadjusted nominal policy rate (7-day term deposit rate, CBI's key stance rate since May 2014). Step-line reflects effective dates.",
        "latest_observation_date": latest["date"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["rate_pct"],
        "records": records,
    }


def fetch_exchange_rate() -> dict[str, Any]:
    """Fetch Daily ISK per 1 USD (ID=4055) and ISK per 1 EUR (ID=4064) official mid-rates."""
    usd_rows = _fetch_cbi_series(4055, START_DATE_CBI)
    eur_rows = _fetch_cbi_series(4064, START_DATE_CBI)
    df_usd = pd.DataFrame(usd_rows).rename(columns={"value": "isk_per_usd"})
    df_eur = pd.DataFrame(eur_rows).rename(columns={"value": "isk_per_eur"})
    df = pd.merge(df_usd, df_eur, on="date", how="inner").sort_values("date").reset_index(drop=True)
    df["usd_ma30"] = df["isk_per_usd"].rolling(30, min_periods=1).mean()
    df["eur_ma30"] = df["isk_per_eur"].rolling(30, min_periods=1).mean()

    records = [
        {
            "date": row["date"],
            "isk_per_usd": round(float(row["isk_per_usd"]), 4),
            "isk_per_eur": round(float(row["isk_per_eur"]), 4),
            "usd_ma30": round(float(row["usd_ma30"]), 4),
            "eur_ma30": round(float(row["eur_ma30"]), 4),
        }
        for _, row in df.iterrows()
    ]
    latest = records[-1]
    return {
        "id": "exchange_rate",
        "name": "Exchange Rate (ISK per 1 USD & 1 EUR)",
        "source": "Central Bank of Iceland (Seðlabanki Íslands), Official Mid-Rate TimeSeriesID=4055 (USD) & 4064 (EUR)",
        "source_url": "https://www.cb.is/statistics/official-exchange-rate/",
        "api_url": f"{CBI_XML_URL}?DagsFra={START_DATE_CBI}&TimeSeriesID=4055&Type=xml",
        "frequency": "Daily (business days)",
        "units": "ISK per 1 USD (and ISK per 1 EUR)",
        "transformation": "Direct quotation (price notation: ISK per 1 unit of foreign currency). Rising ISK/USD indicates Icelandic króna depreciation; falling ISK/USD indicates króna appreciation. Includes 30-business-day moving average.",
        "latest_observation_date": latest["date"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["isk_per_usd"],
        "latest_eur_value": latest["isk_per_eur"],
        "records": records,
    }


def fetch_trade_balance() -> dict[str, Any]:
    """Fetch Monthly Merchandise Exports, Imports, and Trade Balance from Statistics Iceland UTA06001."""
    table_path = "Efnahagur/utanrikisverslun/1_voruvidskipti/01_voruskipti/UTA06001.px"
    meta_url = f"{PX_BASE_URL}/{table_path}"
    raw = _post_pxweb(
        table_path,
        [
            {"code": "Vara", "selection": {"filter": "item", "values": ["XFRETTVx0", "MNFLKM0", "M_X_00"]}},
            {"code": "Mánuður", "selection": {"filter": "all", "values": ["*"]}},
        ],
    )
    df = _jsonstat_to_dataframe(raw)
    df = df[df["Mánuður"].str[:4].astype(int) >= 2015]
    piv = df.pivot(index="Mánuður", columns="Vara", values="value").reset_index()
    piv = piv.sort_values("Mánuður").reset_index(drop=True)
    piv["exports_fob"] = pd.to_numeric(piv["XFRETTVx0"], errors="coerce")
    piv["imports_cif"] = pd.to_numeric(piv["MNFLKM0"], errors="coerce")
    piv["balance"] = pd.to_numeric(piv["M_X_00"], errors="coerce")
    piv["balance_12m_sum"] = piv["balance"].rolling(12, min_periods=1).sum()

    records = [
        {
            "period": row["Mánuður"],
            "date": _month_to_iso_date(row["Mánuður"]),
            "exports_fob_isk_m": round(float(row["exports_fob"]), 1),
            "imports_cif_isk_m": round(float(row["imports_cif"]), 1),
            "balance_isk_m": round(float(row["balance"]), 1),
            "balance_12m_isk_m": round(float(row["balance_12m_sum"]), 1),
        }
        for _, row in piv.iterrows()
    ]
    latest = records[-1]
    return {
        "id": "trade_balance",
        "name": "Merchandise Trade Balance (Goods Exports & Imports)",
        "source": "Statistics Iceland (Hagstofa Íslands), Table UTA06001",
        "source_url": "https://px.hagstofa.is/pxen/pxweb/en/Efnahagur/utanrikisverslun__1_voruvidskipti__01_voruskipti/UTA06001.px",
        "api_url": meta_url,
        "frequency": "Monthly",
        "units": "ISK millions (Exports FOB, Imports CIF, Trade Balance = FOB - CIF)",
        "transformation": "Monthly merchandise balance (Exports FOB minus Imports CIF) plus 12-month rolling cumulative trade balance.",
        "latest_observation_date": latest["period"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["balance_isk_m"],
        "latest_exports": latest["exports_fob_isk_m"],
        "latest_imports": latest["imports_cif_isk_m"],
        "records": records,
    }


def fetch_unemployment() -> dict[str, Any]:
    """Fetch Monthly Unemployment Rate (SA and Original) from Statistics Iceland VIN00002 & VIN00001."""
    sa_path = "Samfelag/vinnumarkadur/vinnumarkadsrannsokn/1_manadartolur/VIN00002.px"
    orig_path = "Samfelag/vinnumarkadur/vinnumarkadsrannsokn/1_manadartolur/VIN00001.px"
    sa_url = f"{PX_BASE_URL}/{sa_path}"
    query = [
        {"code": "Mánuður", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Kyn/aldur", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Eining", "selection": {"filter": "item", "values": ["7"]}},
    ]
    df_sa = _jsonstat_to_dataframe(_post_pxweb(sa_path, query))[["Mánuður", "value"]].rename(
        columns={"value": "unemp_sa_pct"}
    )
    df_orig = _jsonstat_to_dataframe(_post_pxweb(orig_path, query))[["Mánuður", "value"]].rename(
        columns={"value": "unemp_orig_pct"}
    )
    df = pd.merge(df_sa, df_orig, on="Mánuður", how="inner")
    df = df[df["Mánuður"].str[:4].astype(int) >= 2015].sort_values("Mánuður").reset_index(drop=True)

    records = [
        {
            "period": row["Mánuður"],
            "date": _month_to_iso_date(row["Mánuður"]),
            "unemp_sa_pct": round(float(row["unemp_sa_pct"]), 1),
            "unemp_orig_pct": round(float(row["unemp_orig_pct"]), 1),
        }
        for _, row in df.iterrows()
    ]
    latest = records[-1]
    return {
        "id": "unemployment",
        "name": "Unemployment Rate (Labor Force Survey, Ages 16–74)",
        "source": "Statistics Iceland (Hagstofa Íslands), Tables VIN00002 (SA) & VIN00001 (Original)",
        "source_url": "https://px.hagstofa.is/pxen/pxweb/en/Samfelag/vinnumarkadur__vinnumarkadsrannsokn__1_manadartolur/VIN00002.px",
        "api_url": sa_url,
        "frequency": "Monthly",
        "units": "% of labor force",
        "transformation": "Seasonally adjusted headline monthly unemployment rate (total, ages 16–74) plotted alongside unadjusted original survey rate.",
        "latest_observation_date": latest["period"],
        "latest_observation_iso": latest["date"],
        "latest_value": latest["unemp_sa_pct"],
        "latest_unadjusted": latest["unemp_orig_pct"],
        "records": records,
    }


def _compute_payload_hash(series_dict: dict[str, Any]) -> str:
    canonical = json.dumps(series_dict, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def refresh_all(trigger: str = "manual") -> dict[str, Any]:
    """Fetch all 6 indicators from primary sources, persist datasets, and log the refresh."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now().astimezone()

    prev_hash = None
    if METADATA_PATH.exists():
        try:
            prev_meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            prev_hash = prev_meta.get("data_hash")
        except Exception:
            prev_hash = None

    try:
        series = {
            "gdp": fetch_real_gdp(),
            "cpi": fetch_cpi_inflation(),
            "policy_rate": fetch_policy_rate(),
            "exchange_rate": fetch_exchange_rate(),
            "trade_balance": fetch_trade_balance(),
            "unemployment": fetch_unemployment(),
        }
        duration = round(time.perf_counter() - t0, 2)
        data_hash = _compute_payload_hash(series)
        data_changed = prev_hash is not None and data_hash != prev_hash

        payload = {
            "country": "Iceland",
            "research_question": (
                "Is Iceland achieving a soft landing — bringing CPI inflation down toward "
                "the Central Bank's 2.5% target while preserving growth, employment, and króna stability?"
            ),
            "refreshed_at_utc": now_utc.isoformat(timespec="seconds"),
            "refreshed_at_local": now_local.isoformat(timespec="seconds"),
            "series": series,
        }
        DATASET_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        series_summary = {
            k: {
                "name": v["name"],
                "latest_observation_date": v["latest_observation_date"],
                "latest_value": v["latest_value"],
                "observation_count": len(v["records"]),
                "source": v["source"],
            }
            for k, v in series.items()
        }

        metadata = {
            "status": "success",
            "trigger": trigger,
            "last_successful_refresh_utc": now_utc.isoformat(timespec="seconds"),
            "last_successful_refresh_local": now_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "duration_seconds": duration,
            "data_hash": data_hash,
            "data_changed_since_prior_refresh": data_changed,
            "series_summary": series_summary,
        }
        METADATA_PATH.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        with REFRESH_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        return metadata
    except Exception as exc:
        duration = round(time.perf_counter() - t0, 2)
        err_entry = {
            "status": "error",
            "trigger": trigger,
            "attempted_at_utc": now_utc.isoformat(timespec="seconds"),
            "attempted_at_local": now_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "duration_seconds": duration,
            "error": str(exc),
        }
        with REFRESH_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(err_entry, ensure_ascii=False) + "\n")
        raise


def load_cached_data() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load cached macro dataset and metadata, refreshing if missing."""
    if not DATASET_PATH.exists() or not METADATA_PATH.exists():
        refresh_all(trigger="initial_bootstrap")
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return dataset, metadata


def load_refresh_log(limit: int = 25) -> list[dict[str, Any]]:
    """Load the most recent refresh audit log entries (newest first)."""
    if not REFRESH_LOG_PATH.exists():
        return []
    lines = [ln.strip() for ln in REFRESH_LOG_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    entries = [json.loads(ln) for ln in lines]
    return list(reversed(entries[-limit:]))
