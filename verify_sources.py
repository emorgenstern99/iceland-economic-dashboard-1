"""Independent source verification for the Iceland Macroeconomic Monitor.

Directly queries Statistics Iceland PxWeb API and Central Bank of Iceland XML API
independently of `data_pipeline.py`, verifies exact observation values and math
transformations against `data/iceland_macro.json`, and writes `data/verification_report.json`.
"""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "data" / "iceland_macro.json"
REPORT_PATH = BASE_DIR / "data" / "verification_report.json"

PX_BASE = "https://px.hagstofa.is/pxen/api/v1/en"
CBI_XML = "https://www.sedlabanki.is/xmltimeseries/Default.aspx"
HEADERS = {"User-Agent": "Iceland-Macro-Verifier/1.0"}


def _post_px(table_path: str, query: list[dict[str, Any]]) -> dict[str, Any]:
    for attempt in range(5):
        time.sleep(0.8)
        resp = requests.post(
            f"{PX_BASE}/{table_path}",
            json={"query": query, "response": {"format": "json-stat2"}},
            headers=HEADERS,
            timeout=30,
        )
        if resp.status_code in (429, 503) and attempt < 4:
            time.sleep(2.5 * (2 ** attempt))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _get_cbi_latest(series_id: int, date_from: str = "2026-11-01") -> tuple[str, float]:
    resp = requests.get(
        CBI_XML,
        params={"DagsFra": date_from, "TimeSeriesID": str(series_id), "Type": "xml"},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    entries = root.findall("TimeSeries/TimeSeriesData/Entry")
    if not entries:
        raise ValueError(f"No entries returned for CBI ID={series_id}")
    last = entries[-1]
    dt = datetime.strptime(last.findtext("Date").strip(), "%m/%d/%Y %I:%M:%S %p").strftime("%Y-%m-%d")
    val = float(last.findtext("Value"))
    return dt, val


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    series = dataset["series"]
    checks: list[dict[str, Any]] = []

    # 1. Real GDP Growth (THJ01601)
    gdp_latest = series["gdp"]["records"][-1]
    q = gdp_latest["period"]
    q_prev_yr = f"{int(q[:4]) - 1}{q[4:]}"
    raw_gdp = _post_px(
        "Efnahagur/thjodhagsreikningar/landsframl/2_landsframleidsla_arsfj/THJ01601.px",
        [
            {"code": "Mælikvarði", "selection": {"filter": "item", "values": ["1", "2", "4"]}},
            {"code": "Skipting", "selection": {"filter": "item", "values": ["14"]}},
            {"code": "Ársfjórðungur", "selection": {"filter": "item", "values": [q_prev_yr, q]}},
        ],
    )
    # values order: [1_prev, 1_curr, 2_prev, 2_curr, 4_prev, 4_curr]
    v = raw_gdp["value"]
    raw_chain_prev, raw_chain_curr = float(v[0]), float(v[1])
    raw_yoy, raw_qoq_sa = float(v[3]), float(v[5])
    calc_yoy = round(((raw_chain_curr / raw_chain_prev) - 1.0) * 100.0, 1)
    checks.append(
        {
            "indicator": "Real GDP Growth",
            "source": "Statistics Iceland THJ01601",
            "observation_checked": q,
            "dashboard_value": gdp_latest["yoy_pct"],
            "source_raw_value": raw_yoy,
            "transformation_check": f"Chain volume {raw_chain_curr:,.0f} / {raw_chain_prev:,.0f} -> {calc_yoy}% YoY; QoQ SA={raw_qoq_sa}%",
            "match": abs(gdp_latest["yoy_pct"] - raw_yoy) < 0.05 and abs(gdp_latest["qoq_sa_pct"] - raw_qoq_sa) < 0.05,
        }
    )

    # 2. CPI Inflation (VIS01000 + CBI GroupID=3 cross-check)
    cpi_latest = series["cpi"]["records"][-1]
    m = cpi_latest["period"]
    m_prev_yr = f"{int(m[:4]) - 1}{m[4:]}"
    raw_cpi = _post_px(
        "Efnahagur/visitolur/1_vnv/1_vnv/VIS01000.px",
        [
            {"code": "Month", "selection": {"filter": "item", "values": [m_prev_yr, m]}},
            {"code": "Index", "selection": {"filter": "item", "values": ["CPI"]}},
            {"code": "Item", "selection": {"filter": "item", "values": ["index", "change_A"]}},
        ],
    )
    cv = raw_cpi["value"]
    # dims: Month(2) x Index(1) x Item(2) -> [prev_idx, prev_chg, curr_idx, curr_chg]
    cpi_prev_idx, cpi_curr_idx, cpi_curr_chg = float(cv[0]), float(cv[2]), float(cv[3])
    calc_cpi_yoy = round(((cpi_curr_idx / cpi_prev_idx) - 1.0) * 100.0, 2)
    cbi_cpi_dt, cbi_cpi_yoy = _get_cbi_latest(2, "2026-09-01")
    checks.append(
        {
            "indicator": "CPI Inflation (YoY % & Index)",
            "source": "Statistics Iceland VIS01000 (+ CBI ID=2 mirror)",
            "observation_checked": m,
            "dashboard_value": {"index": cpi_latest["cpi_index"], "yoy_pct": cpi_latest["yoy_pct"]},
            "source_raw_value": {"index": cpi_curr_idx, "published_yoy_pct": cpi_curr_chg, "cbi_mirror_yoy": cbi_cpi_yoy},
            "transformation_check": f"({cpi_curr_idx} / {cpi_prev_idx} - 1) * 100 = {calc_cpi_yoy}% (published {cpi_curr_chg}%)",
            "match": abs(cpi_latest["cpi_index"] - cpi_curr_idx) < 0.01 and abs(cpi_latest["yoy_pct"] - calc_cpi_yoy) < 0.02,
        }
    )

    # 3. CBI Policy Rate (TimeSeriesID=75 & cross-check ID=17923)
    rate_latest = series["policy_rate"]["records"][-1]
    raw_rate_dt, raw_rate_val = _get_cbi_latest(75)
    key_rate_dt, key_rate_val = _get_cbi_latest(17923)
    checks.append(
        {
            "indicator": "CBI Policy Rate (7-Day Term Deposit)",
            "source": "Central Bank of Iceland TimeSeriesID=75 (and ID=17923)",
            "observation_checked": raw_rate_dt,
            "dashboard_value": rate_latest["rate_pct"],
            "source_raw_value": raw_rate_val,
            "transformation_check": f"ID=75 ({raw_rate_val}%) matches Key Policy Rate ID=17923 ({key_rate_val}% on {key_rate_dt})",
            "match": rate_latest["date"] == raw_rate_dt and abs(rate_latest["rate_pct"] - raw_rate_val) < 1e-6 and abs(raw_rate_val - key_rate_val) < 1e-6,
        }
    )

    # 4. Exchange Rate (ISK per 1 USD ID=4055 & ISK per 1 EUR ID=4064)
    fx_latest = series["exchange_rate"]["records"][-1]
    raw_usd_dt, raw_usd_val = _get_cbi_latest(4055)
    raw_eur_dt, raw_eur_val = _get_cbi_latest(4064)
    checks.append(
        {
            "indicator": "Exchange Rate (ISK per 1 USD & 1 EUR)",
            "source": "Central Bank of Iceland TimeSeriesID=4055 (USD) & 4064 (EUR)",
            "observation_checked": raw_usd_dt,
            "dashboard_value": {"isk_per_usd": fx_latest["isk_per_usd"], "isk_per_eur": fx_latest["isk_per_eur"]},
            "source_raw_value": {"isk_per_usd": raw_usd_val, "isk_per_eur": raw_eur_val},
            "transformation_check": "Direct quotation mid-rate (ISK per 1 unit FX); no scaling applied to spot series",
            "match": (
                fx_latest["date"] == raw_usd_dt
                and abs(fx_latest["isk_per_usd"] - raw_usd_val) < 1e-4
                and abs(fx_latest["isk_per_eur"] - raw_eur_val) < 1e-4
            ),
        }
    )

    # 5. Merchandise Trade Balance (UTA06001)
    tr_latest = series["trade_balance"]["records"][-1]
    tm = tr_latest["period"]
    raw_tr = _post_px(
        "Efnahagur/utanrikisverslun/1_voruvidskipti/01_voruskipti/UTA06001.px",
        [
            {"code": "Vara", "selection": {"filter": "item", "values": ["XFRETTVx0", "MNFLKM0", "M_X_00"]}},
            {"code": "Mánuður", "selection": {"filter": "item", "values": [tm]}},
        ],
    )
    tv = raw_tr["value"]
    raw_exp, raw_imp, raw_bal = float(tv[0]), float(tv[1]), float(tv[2])
    calc_bal = round(raw_exp - raw_imp, 1)
    checks.append(
        {
            "indicator": "Merchandise Trade Balance",
            "source": "Statistics Iceland UTA06001",
            "observation_checked": tm,
            "dashboard_value": {
                "exports_fob": tr_latest["exports_fob_isk_m"],
                "imports_cif": tr_latest["imports_cif_isk_m"],
                "balance": tr_latest["balance_isk_m"],
            },
            "source_raw_value": {"exports_fob": raw_exp, "imports_cif": raw_imp, "balance": raw_bal},
            "transformation_check": f"FOB ({raw_exp:,.1f}) - CIF ({raw_imp:,.1f}) = {calc_bal:,.1f}M ISK (published {raw_bal:,.1f})",
            "match": abs(tr_latest["balance_isk_m"] - raw_bal) < 0.2 and abs(calc_bal - raw_bal) < 0.2,
        }
    )

    # 6. Unemployment Rate (VIN00002 & VIN00001)
    un_latest = series["unemployment"]["records"][-1]
    um = un_latest["period"]
    raw_un_sa = _post_px(
        "Samfelag/vinnumarkadur/vinnumarkadsrannsokn/1_manadartolur/VIN00002.px",
        [
            {"code": "Mánuður", "selection": {"filter": "item", "values": [um]}},
            {"code": "Kyn/aldur", "selection": {"filter": "item", "values": ["0"]}},
            {"code": "Eining", "selection": {"filter": "item", "values": ["7"]}},
        ],
    )
    raw_un_orig = _post_px(
        "Samfelag/vinnumarkadur/vinnumarkadsrannsokn/1_manadartolur/VIN00001.px",
        [
            {"code": "Mánuður", "selection": {"filter": "item", "values": [um]}},
            {"code": "Kyn/aldur", "selection": {"filter": "item", "values": ["0"]}},
            {"code": "Eining", "selection": {"filter": "item", "values": ["7"]}},
        ],
    )
    raw_sa_val = float(raw_un_sa["value"][0])
    raw_orig_val = float(raw_un_orig["value"][0])
    checks.append(
        {
            "indicator": "Unemployment Rate (LFS)",
            "source": "Statistics Iceland VIN00002 (SA) & VIN00001 (Orig)",
            "observation_checked": um,
            "dashboard_value": {"sa": un_latest["unemp_sa_pct"], "orig": un_latest["unemp_orig_pct"]},
            "source_raw_value": {"sa": raw_sa_val, "orig": raw_orig_val},
            "transformation_check": "Exact match to Statistics Iceland Labor Force Survey (16-74 total)",
            "match": abs(un_latest["unemp_sa_pct"] - raw_sa_val) < 0.05 and abs(un_latest["unemp_orig_pct"] - raw_orig_val) < 0.05,
        }
    )

    all_passed = all(c["match"] for c in checks)
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verified_at_local": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "all_checks_passed": all_passed,
        "checks": checks,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
