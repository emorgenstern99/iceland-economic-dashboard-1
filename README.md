# 🇮🇸 Iceland Macroeconomic Monitor

An automated, primary-source macroeconomic monitoring dashboard for **Iceland** built with **Python**, **Streamlit**, and **Plotly**, designed to run locally or deploy on **GitHub + Streamlit Community Cloud** with scheduled data refreshes.

## Key Research Question

> **Is Iceland achieving a soft landing — bringing CPI inflation down toward the Central Bank's 2.5% target while preserving growth, employment, and króna stability?**

---

## Selected Indicators & Primary Sources

All data are retrieved directly from official primary statistical and monetary authorities via machine-readable APIs (no secondary aggregators or social media):

| # | Indicator | Units | Frequency | Primary Source & Series ID | Transformations & Conventions |
|---|-----------|-------|-----------|----------------------------|-------------------------------|
| 1 | **Real GDP Growth** | `%` (chain-volume change) | Quarterly | Statistics Iceland (`THJ01601`) | YoY % = `(RealGDP_t / RealGDP_{t-4} - 1) × 100`; QoQ SA % = seasonally adjusted quarter-on-quarter volume growth |
| 2 | **Consumer Price Index (CPI) & Inflation** | `% YoY` & Index (`May 1988 = 100`; rebased `2015M01 = 100`) | Monthly | Statistics Iceland (`VIS01000`) | 12-month % change computed as `(CPI_t / CPI_{t-12} - 1) × 100` (cross-checked vs. published annual change); rebased series = `(CPI_t / CPI_2015M01) × 100` |
| 3 | **CBI Policy Interest Rate (7-Day Term Deposit Rate)** | `% per annum` | Policy meeting / Daily effective step series | Central Bank of Iceland (`TimeSeriesID=75`, matches Key Policy Rate `ID=17923`) | Nominal policy stance rate (effective since May 2014); step-line reflects exact effective dates; dashboard also reports ex-post real policy rate (`Policy Rate − CPI YoY`) |
| 4 | **Exchange Rate (ISK per 1 USD & 1 EUR)** | `ISK per 1 USD` (and `ISK per 1 EUR`) | Daily (business days) | Central Bank of Iceland (`TimeSeriesID=4055` USD, `4064` EUR) | **Direct quotation from Iceland's perspective (price notation: ISK per 1 unit FX).** A **rising** ISK/USD rate indicates **króna (ISK) depreciation**; a **falling** ISK/USD rate indicates **króna appreciation**. Includes 30-business-day moving average |
| 5 | **Merchandise Trade Balance & Goods Flows** | `ISK millions` | Monthly | Statistics Iceland (`UTA06001`) | `Trade Balance = Goods Exports (FOB) − Goods Imports (CIF)`; includes 12-month rolling cumulative balance |
| 6 | **Unemployment Rate (Labor Force Survey)** | `% of labor force` (ages 16–74) | Monthly | Statistics Iceland (`VIN00002` SA & `VIN00001` Original) | Seasonally adjusted headline monthly rate plotted alongside unadjusted original survey rate |

### Sample Period
- Default sample starts in **2015** (`2015–Present`), providing full macro context across Iceland's pre-COVID tourism expansion, the 2020–2021 pandemic shock, the 2022–2024 inflation surge and monetary tightening cycle, and the 2025–2026 disinflation phase. Interactive sidebar presets also allow zooming into `2020–Present` and `2022–Present`.

---

## Repository Structure

```text
.
├── app.py                              # Streamlit interactive dashboard
├── data_pipeline.py                    # Primary API fetcher, normalizer, cache & audit logger
├── refresh_data.py                     # CLI entry point for automated/scheduled refreshes
├── verify_sources.py                   # Independent raw-API verification & math check script
├── requirements.txt                    # Python package requirements
├── .github/
│   └── workflows/
│       └── refresh_data.yml            # Daily GitHub Actions cron job (12:00 UTC)
├── scripts/
│   └── register_windows_task.ps1       # Optional Windows Task Scheduler registration script
├── data/
│   ├── iceland_macro.json              # Normalized cached dataset for all 6 series
│   ├── refresh_metadata.json           # Latest refresh timestamp, duration, and payload hash
│   ├── refresh_log.jsonl               # Append-only audit log of all refresh runs
│   └── verification_report.json        # Independent source-to-dashboard reconciliation report
├── PROMPT.md                           # Prompt / instructions used to build this project
├── VERIFICATION.md                     # Documented data checks & refresh evidence
└── evidence/                           # Dashboard screenshots for verification
```

---

## Automated Refresh Architecture

1. **GitHub Actions Cron (`.github/workflows/refresh_data.yml`):**
   - Runs `python refresh_data.py --trigger scheduled_ci` automatically every day at **12:00 UTC** (after the Central Bank of Iceland's daily FX fixing) and commits updated `data/` artifacts back to the repository.
2. **In-App Scheduled Auto-Refresh (`app.py`):**
   - Uses Streamlit's `@st.fragment(run_every=...)` (configurable in the sidebar: Every 6 hours, 1 hour, 15 minutes, or Manual) plus a **Refresh Data Now** button to pull fresh data while the dashboard is open.
3. **Local Windows Task Scheduler (`scripts/register_windows_task.ps1`):**
   - Registers a daily Windows scheduled task for local automation.
4. **Clear Separation of Timestamps:**
   - The top **Last Successful Data Refresh** banner displays the exact UTC and local date/time of the latest pipeline run, completely separate from each chart's **Latest Observation Date**.

---

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Fetch fresh data from Statistics Iceland & Central Bank of Iceland
python refresh_data.py --trigger manual_cli

# 3. Verify observations against raw primary APIs
python verify_sources.py

# 4. Launch the Streamlit dashboard
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. Push this repository to GitHub (make sure GitHub Actions permissions allow `Read and write permissions` under **Settings → Actions → General** so `refresh_data.yml` can commit daily data updates).
2. Connect the repository on [share.streamlit.io](https://share.streamlit.io/) with `app.py` as the main file path.
3. The live app will automatically reflect daily scheduled GitHub Actions data commits as well as in-app scheduled/manual refreshes.
