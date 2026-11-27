"""Iceland Macroeconomic Monitor — Interactive Streamlit Dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data_pipeline import (
    DATASET_PATH,
    load_cached_data,
    load_refresh_log,
    refresh_all,
)

st.set_page_config(
    page_title="Iceland Macroeconomic Monitor",
    page_icon="🇮🇸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Clean light editorial theme styling
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1420px;
    }
    .hero-box {
        background: linear-gradient(135deg, #0b2545 0%, #134074 100%);
        color: #ffffff;
        padding: 1.35rem 1.6rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border-left: 6px solid #dc2f02;
    }
    .hero-title {
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.02em;
    }
    .hero-question {
        font-size: 1.02rem;
        color: #e2ecf7;
        margin: 0;
        line-height: 1.45;
    }
    .refresh-banner {
        background-color: #f4f7fb;
        border: 1px solid #d5e0ee;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        color: #1d3557;
    }
    .meta-caption {
        background-color: #f8fafc;
        border-left: 3px solid #1d3557;
        padding: 0.6rem 0.85rem;
        border-radius: 4px;
        font-size: 0.82rem;
        color: #334155;
        margin-top: 0.25rem;
        line-height: 1.45;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        box-sizing: border-box;
        width: 100%;
    }
    .meta-details {
        width: 100%;
        min-width: 0;
        overflow-wrap: anywhere;
    }
    .latest-value-row {
        display: flex;
        justify-content: flex-end;
        width: 100%;
    }
    .latest-value-box {
        max-width: 100%;
        box-sizing: border-box;
        text-align: right;
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 0.35rem 0.65rem;
    }
    .latest-value-label {
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #64748b;
        display: block;
    }
    .latest-value-num {
        font-size: 1.0rem;
        font-weight: 700;
        color: #0b2545;
        display: block;
        line-height: 1.25;
    }
    .latest-value-date {
        font-size: 0.72rem;
        color: #475569;
        display: block;
    }
    .meta-caption code, .refresh-banner code {
        background-color: #e2e8f0;
        color: #0f172a;
        padding: 0.1rem 0.35rem;
        border-radius: 4px;
        font-size: 0.82rem;
    }
    .convention-alert {
        background-color: #fff7ed;
        border-left: 3px solid #c2410c;
        padding: 0.5rem 0.75rem;
        border-radius: 4px;
        font-size: 0.82rem;
        color: #7c2d12;
        margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PALETTE = {
    "navy": "#0b2545",
    "blue": "#1d4ed8",
    "sky": "#0284c7",
    "teal": "#0f766e",
    "red": "#dc2626",
    "amber": "#d97706",
    "slate": "#64748b",
    "grid": "#e2e8f0",
}

AUTO_REFRESH_OPTIONS = {
    "Every 6 hours (recommended)": timedelta(hours=6),
    "Every 1 hour": timedelta(hours=1),
    "Every 15 minutes": timedelta(minutes=15),
    "Manual / GitHub Actions only": None,
}

SAMPLE_WINDOWS = {
    "Full Sample (2015–Present)": "2015-01-01",
    "COVID & Post-COVID (2020–Present)": "2020-01-01",
    "Recent Tightening & Disinflation (2022–Present)": "2022-01-01",
}


def _apply_base_layout(fig: go.Figure, height: int = 360, right_margin: int = 20) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        height=height,
        margin=dict(l=16, r=right_margin, t=28, b=16),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="#1e293b"),
        ),
        hovermode="x unified",
        font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1e293b"),
        xaxis=dict(showgrid=True, gridcolor=PALETTE["grid"], zeroline=False, tickfont=dict(color="#334155")),
        yaxis=dict(showgrid=True, gridcolor=PALETTE["grid"], zeroline=True, zerolinecolor="#94a3b8", tickfont=dict(color="#334155")),
    )
    return fig


def _filter_df(df: pd.DataFrame, start_iso: str) -> pd.DataFrame:
    return df[df["date"] >= start_iso].copy()


def _chart_metadata_html(
    series_meta: dict[str, Any],
    latest_value_str: str,
    extra_note: str = "",
) -> str:
    extra = f"<br><b>Note:</b> {extra_note}" if extra_note else ""
    return (
        f"<div class='meta-caption'>"
        f"<div class='meta-details'>"
        f"<b>Units:</b> {series_meta['units']} &nbsp;|&nbsp; "
        f"<b>Frequency:</b> {series_meta['frequency']} &nbsp;|&nbsp; "
        f"<b>Latest Observation:</b> <code>{series_meta['latest_observation_date']}</code><br>"
        f"<b>Source:</b> <a href='{series_meta['source_url']}' target='_blank'>{series_meta['source']}</a><br>"
        f"<b>Transformation:</b> {series_meta['transformation']}"
        f"{extra}"
        f"</div>"
        f"<div class='latest-value-row'>"
        f"<div class='latest-value-box'>"
        f"<span class='latest-value-label'>Latest Value</span>"
        f"<span class='latest-value-num'>{latest_value_str}</span>"
        f"<span class='latest-value-date'>{series_meta['latest_observation_date']}</span>"
        f"</div>"
        f"</div>"
        f"</div>"
    )


def render_dashboard() -> None:
    # Sidebar controls
    with st.sidebar:
        st.header("Dashboard Controls")
        sample_label = st.selectbox(
            "Sample Period",
            options=list(SAMPLE_WINDOWS.keys()),
            index=0,
            help="2015–Present provides pre-COVID tourism boom, pandemic shock, inflation surge, and 2024–2026 disinflation context.",
        )
        start_iso = SAMPLE_WINDOWS[sample_label]

        schedule_label = st.selectbox(
            "In-App Scheduled Auto-Refresh",
            options=list(AUTO_REFRESH_OPTIONS.keys()),
            index=0,
            help="Automatically polls Statistics Iceland and Central Bank of Iceland APIs on a schedule while the app is open (complemented by daily GitHub Actions cron).",
        )

        st.divider()
        st.subheader("Chart Display Options")
        gdp_show_qoq = st.checkbox("GDP: Overlay QoQ SA growth", value=True)
        cpi_view = st.radio(
            "CPI Display Mode",
            options=["YoY Inflation (%) vs 2.5% Target", "CPI Index (May 1988=100 & Rebased 2015=100)"],
            index=0,
        )
        rate_show_real = st.checkbox("Policy Rate: Overlay CPI YoY for real rate context", value=True)
        fx_currency = st.radio(
            "Exchange Rate Pair",
            options=["ISK per 1 USD", "ISK per 1 EUR", "Both USD & EUR"],
            index=0,
        )
        trade_show_12m = st.checkbox("Trade: Show 12-month cumulative balance", value=True)
        unemp_show_orig = st.checkbox("Unemployment: Overlay unadjusted survey rate", value=True)

        st.divider()
        if st.button("Refresh Data Now", type="primary", use_container_width=True):
            with st.spinner("Fetching latest observations from Statistics Iceland & Central Bank of Iceland..."):
                refresh_all(trigger="manual_ui")
            st.toast("All 6 primary series refreshed successfully.", icon="✅")
            st.rerun()

    run_every = AUTO_REFRESH_OPTIONS[schedule_label]

    @st.fragment(run_every=run_every)
    def _live_dashboard_body() -> None:
        # If scheduled fragment fires after interval, trigger a fresh pull when due
        dataset, metadata = load_cached_data()
        if run_every is not None:
            last_utc = datetime.fromisoformat(metadata["last_successful_refresh_utc"])
            age = datetime.now(last_utc.tzinfo) - last_utc
            if age >= run_every:
                metadata = refresh_all(trigger="scheduled_ui_fragment")
                dataset, metadata = load_cached_data()

        series = dataset["series"]

        # Hero header & research question
        st.markdown(
            f"""
            <div class="hero-box">
                <div class="hero-title">🇮🇸 Iceland Macroeconomic Monitor</div>
                <p class="hero-question">
                    <b>Key Question:</b> {dataset['research_question']}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Separate Last Successful Refresh banner (distinct from observation dates)
        st.markdown(
            f"""
            <div class="refresh-banner">
                <b>Last Successful Data Refresh (Pipeline Execution):</b>
                <code>{metadata['last_successful_refresh_local']}</code>
                (<code>{metadata['last_successful_refresh_utc']}</code>)
                &nbsp;•&nbsp; <b>Trigger:</b> <code>{metadata['trigger']}</code>
                &nbsp;•&nbsp; <b>Schedule:</b> In-app ({schedule_label}) + Daily GitHub Actions Cron (12:00 UTC)
                &nbsp;•&nbsp; <b>Fetch Duration:</b> {metadata['duration_seconds']}s
                <br>
                <span style="font-size:0.82rem; color:#475569;">
                    Note: Refresh timestamp indicates when primary APIs were queried; each chart below separately reports its own Latest Observation Date from the statistical agency or central bank.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # KPI Strip (6 indicators)
        gdp_df = pd.DataFrame(series["gdp"]["records"])
        cpi_df = pd.DataFrame(series["cpi"]["records"])
        rate_df = pd.DataFrame(series["policy_rate"]["records"])
        fx_df = pd.DataFrame(series["exchange_rate"]["records"])
        trade_df = pd.DataFrame(series["trade_balance"]["records"])
        unemp_df = pd.DataFrame(series["unemployment"]["records"])

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        with k1:
            g_last, g_prev = gdp_df.iloc[-1], gdp_df.iloc[-2]
            st.metric(
                "Real GDP Growth (YoY)",
                f"{g_last['yoy_pct']:+.1f}%",
                delta=f"{g_last['yoy_pct'] - g_prev['yoy_pct']:+.1f} pp vs {g_prev['period']}",
            )
            st.caption(f"Obs: **{g_last['period']}** · Quarterly")
        with k2:
            c_last, c_prev = cpi_df.iloc[-1], cpi_df.iloc[-2]
            st.metric(
                "CPI Inflation (YoY)",
                f"{c_last['yoy_pct']:.1f}%",
                delta=f"{c_last['yoy_pct'] - c_prev['yoy_pct']:+.1f} pp vs {c_prev['period']}",
                delta_color="inverse",
            )
            st.caption(f"Obs: **{c_last['period']}** · Monthly")
        with k3:
            r_last = rate_df.iloc[-1]
            changes = rate_df[rate_df["is_decision_change"]]
            r_prev_decision = changes.iloc[-2] if len(changes) >= 2 else rate_df.iloc[0]
            st.metric(
                "CBI Policy Rate (7D)",
                f"{r_last['rate_pct']:.2f}%",
                delta=f"{r_last['rate_pct'] - r_prev_decision['rate_pct']:+.2f} pp last move",
                delta_color="off",
            )
            st.caption(f"Obs: **{r_last['date']}** · Daily step")
        with k4:
            f_last = fx_df.iloc[-1]
            f_30d = fx_df.iloc[max(0, len(fx_df) - 22)]
            st.metric(
                "ISK per 1 USD (Mid)",
                f"{f_last['isk_per_usd']:.2f}",
                delta=f"{f_last['isk_per_usd'] - f_30d['isk_per_usd']:+.2f} ISK (~1M)",
                delta_color="inverse",
            )
            st.caption(f"Obs: **{f_last['date']}** · Direct quote")
        with k5:
            t_last, t_prev = trade_df.iloc[-1], trade_df.iloc[-2]
            st.metric(
                "Goods Balance (B ISK)",
                f"{t_last['balance_isk_m'] / 1000:,.1f}B",
                delta=f"{(t_last['balance_isk_m'] - t_prev['balance_isk_m']) / 1000:+.1f}B vs {t_prev['period']}",
            )
            st.caption(f"Obs: **{t_last['period']}** · Monthly")
        with k6:
            u_last, u_prev = unemp_df.iloc[-1], unemp_df.iloc[-2]
            st.metric(
                "Unemployment Rate (SA)",
                f"{u_last['unemp_sa_pct']:.1f}%",
                delta=f"{u_last['unemp_sa_pct'] - u_prev['unemp_sa_pct']:+.1f} pp vs {u_prev['period']}",
                delta_color="inverse",
            )
            st.caption(f"Obs: **{u_last['period']}** · Monthly")

        st.markdown("---")

        # Filter dataframes for selected sample window
        gdp_f = _filter_df(gdp_df, start_iso)
        cpi_f = _filter_df(cpi_df, start_iso)
        rate_f = _filter_df(rate_df, start_iso)
        fx_f = _filter_df(fx_df, start_iso)
        trade_f = _filter_df(trade_df, start_iso)
        unemp_f = _filter_df(unemp_df, start_iso)

        # Row 1: Real GDP Growth & CPI Inflation
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("1. Real GDP Growth (Quarterly)")
            fig_gdp = go.Figure()
            bar_colors = [
                PALETTE["teal"] if (v is not None and v >= 0) else PALETTE["red"]
                for v in gdp_f["yoy_pct"]
            ]
            fig_gdp.add_trace(
                go.Bar(
                    x=gdp_f["date"],
                    y=gdp_f["yoy_pct"],
                    name="Real GDP YoY %",
                    marker_color=bar_colors,
                    customdata=gdp_f["period"],
                    hovertemplate="%{customdata}: %{y:.1f}% YoY<extra></extra>",
                )
            )
            if gdp_show_qoq:
                fig_gdp.add_trace(
                    go.Scatter(
                        x=gdp_f["date"],
                        y=gdp_f["qoq_sa_pct"],
                        name="QoQ % (Seasonally Adjusted)",
                        mode="lines+markers",
                        line=dict(color=PALETTE["navy"], width=2),
                        marker=dict(size=4),
                        customdata=gdp_f["period"],
                        hovertemplate="%{customdata}: %{y:.1f}% QoQ SA<extra></extra>",
                    )
                )
            _apply_base_layout(fig_gdp)
            fig_gdp.update_yaxes(title_text="Percent (%)")
            st.plotly_chart(fig_gdp, use_container_width=True, theme=None)
            gdp_latest_str = f"{gdp_df.iloc[-1]['yoy_pct']:+.1f}% YoY"
            if gdp_show_qoq:
                gdp_latest_str += f"<br><span style='font-size:0.82rem;font-weight:600;color:#334155;'>{gdp_df.iloc[-1]['qoq_sa_pct']:+.1f}% QoQ SA</span>"
            st.markdown(_chart_metadata_html(series["gdp"], gdp_latest_str), unsafe_allow_html=True)

        with col2:
            st.subheader("2. Consumer Price Index (CPI) & Inflation")
            if cpi_view.startswith("YoY"):
                fig_cpi = go.Figure()
                fig_cpi.add_trace(
                    go.Scatter(
                        x=cpi_f["date"],
                        y=cpi_f["yoy_pct"],
                        name="CPI Inflation YoY % (Computed)",
                        mode="lines",
                        line=dict(color=PALETTE["red"], width=2.5),
                        fill="tozeroy",
                        fillcolor="rgba(220, 38, 38, 0.08)",
                        customdata=cpi_f["period"],
                        hovertemplate="%{customdata}: %{y:.2f}% YoY<extra></extra>",
                    )
                )
                fig_cpi.add_hline(
                    y=2.5,
                    line_dash="dash",
                    line_color=PALETTE["teal"],
                    annotation_text="CBI Inflation Target (2.5%)",
                    annotation_position="top right",
                )
                _apply_base_layout(fig_cpi)
                fig_cpi.update_yaxes(title_text="YoY Change (%)")
            else:
                fig_cpi = make_subplots(specs=[[{"secondary_y": True}]])
                fig_cpi.add_trace(
                    go.Scatter(
                        x=cpi_f["date"],
                        y=cpi_f["cpi_index"],
                        name="Official CPI (May 1988 = 100)",
                        mode="lines",
                        line=dict(color=PALETTE["navy"], width=2.5),
                    ),
                    secondary_y=False,
                )
                fig_cpi.add_trace(
                    go.Scatter(
                        x=cpi_f["date"],
                        y=cpi_f["cpi_rebased_2015"],
                        name="Rebased CPI (2015M01 = 100)",
                        mode="lines",
                        line=dict(color=PALETTE["amber"], width=2, dash="dot"),
                    ),
                    secondary_y=True,
                )
                _apply_base_layout(fig_cpi, right_margin=45)
                fig_cpi.update_yaxes(title_text="May 1988 = 100", secondary_y=False)
                fig_cpi.update_yaxes(title_text="2015M01 = 100", secondary_y=True)
            st.plotly_chart(fig_cpi, use_container_width=True, theme=None)
            cpi_latest_str = (
                f"{cpi_df.iloc[-1]['yoy_pct']:.2f}% YoY"
                if cpi_view.startswith("YoY")
                else f"{cpi_df.iloc[-1]['cpi_index']:.1f} idx"
            )
            st.markdown(_chart_metadata_html(series["cpi"], cpi_latest_str), unsafe_allow_html=True)

        st.markdown("")

        # Row 2: CBI Policy Rate & Exchange Rate
        col3, col4 = st.columns(2)
        with col3:
            st.subheader("3. CBI Policy Interest Rate (7-Day Term Deposit Rate)")
            fig_rate = go.Figure()
            fig_rate.add_trace(
                go.Scatter(
                    x=rate_f["date"],
                    y=rate_f["rate_pct"],
                    name="7-Day Term Deposit Rate (% p.a.)",
                    mode="lines",
                    line=dict(color=PALETTE["blue"], width=2.8, shape="hv"),
                )
            )
            decisions = rate_f[rate_f["is_decision_change"]]
            if not decisions.empty:
                fig_rate.add_trace(
                    go.Scatter(
                        x=decisions["date"],
                        y=decisions["rate_pct"],
                        name="Rate Decision Change",
                        mode="markers",
                        marker=dict(color=PALETTE["navy"], size=6),
                    )
                )
            if rate_show_real:
                fig_rate.add_trace(
                    go.Scatter(
                        x=cpi_f["date"],
                        y=cpi_f["yoy_pct"],
                        name="CPI Inflation YoY (%) [Context]",
                        mode="lines",
                        line=dict(color=PALETTE["red"], width=1.8, dash="dash"),
                    )
                )
            _apply_base_layout(fig_rate)
            fig_rate.update_yaxes(title_text="Percent per annum (%)")
            st.plotly_chart(fig_rate, use_container_width=True, theme=None)
            real_ex_post = rate_df.iloc[-1]["rate_pct"] - cpi_df.iloc[-1]["yoy_pct"]
            st.markdown(
                _chart_metadata_html(
                    series["policy_rate"],
                    f"{rate_df.iloc[-1]['rate_pct']:.2f}%",
                    extra_note=f"Current ex-post real policy rate (Policy Rate {rate_df.iloc[-1]['rate_pct']:.2f}% − CPI YoY {cpi_df.iloc[-1]['yoy_pct']:.2f}%) = {real_ex_post:+.2f}%.",
                ),
                unsafe_allow_html=True,
            )

        with col4:
            st.subheader("4. Exchange Rate (ISK per Foreign Currency)")
            st.markdown(
                "<div class='convention-alert'>"
                "<b>Quotation Convention:</b> Direct quotation from Iceland's perspective "
                "(<b>ISK per 1 USD / 1 EUR</b>). <b>Rising value = ISK depreciation</b> (more krónur per USD); "
                "<b>Falling value = ISK appreciation</b>."
                "</div>",
                unsafe_allow_html=True,
            )
            fig_fx = go.Figure()
            if fx_currency in ("ISK per 1 USD", "Both USD & EUR"):
                fig_fx.add_trace(
                    go.Scatter(
                        x=fx_f["date"],
                        y=fx_f["isk_per_usd"],
                        name="ISK per 1 USD (Daily Mid-Rate)",
                        mode="lines",
                        line=dict(color=PALETTE["sky"], width=1.8),
                    )
                )
                if fx_currency == "ISK per 1 USD":
                    fig_fx.add_trace(
                        go.Scatter(
                            x=fx_f["date"],
                            y=fx_f["usd_ma30"],
                            name="30-Business-Day Moving Avg",
                            mode="lines",
                            line=dict(color=PALETTE["navy"], width=2.2, dash="dash"),
                        )
                    )
            if fx_currency in ("ISK per 1 EUR", "Both USD & EUR"):
                fig_fx.add_trace(
                    go.Scatter(
                        x=fx_f["date"],
                        y=fx_f["isk_per_eur"],
                        name="ISK per 1 EUR (Daily Mid-Rate)",
                        mode="lines",
                        line=dict(color=PALETTE["amber"], width=1.8),
                    )
                )
                if fx_currency == "ISK per 1 EUR":
                    fig_fx.add_trace(
                        go.Scatter(
                            x=fx_f["date"],
                            y=fx_f["eur_ma30"],
                            name="30-Business-Day Moving Avg",
                            mode="lines",
                            line=dict(color=PALETTE["navy"], width=2.2, dash="dash"),
                        )
                    )
            _apply_base_layout(fig_fx, height=320)
            fig_fx.update_yaxes(title_text="ISK per 1 unit FX (↑ = ISK depreciation)")
            st.plotly_chart(fig_fx, use_container_width=True, theme=None)
            if fx_currency == "ISK per 1 USD":
                fx_latest_str = f"{fx_df.iloc[-1]['isk_per_usd']:.2f} ISK/USD"
            elif fx_currency == "ISK per 1 EUR":
                fx_latest_str = f"{fx_df.iloc[-1]['isk_per_eur']:.2f} ISK/EUR"
            else:
                fx_latest_str = f"{fx_df.iloc[-1]['isk_per_usd']:.2f} USD / {fx_df.iloc[-1]['isk_per_eur']:.2f} EUR"
            st.markdown(_chart_metadata_html(series["exchange_rate"], fx_latest_str), unsafe_allow_html=True)

        st.markdown("")

        # Row 3: Merchandise Trade Balance & Unemployment Rate
        col5, col6 = st.columns(2)
        with col5:
            st.subheader("5. Merchandise Trade Balance & Goods Flows")
            fig_trade = make_subplots(specs=[[{"secondary_y": True}]])
            fig_trade.add_trace(
                go.Bar(
                    x=trade_f["date"],
                    y=trade_f["exports_fob_isk_m"],
                    name="Goods Exports (FOB, ISK M)",
                    marker_color="rgba(15, 118, 110, 0.72)",
                    customdata=trade_f["period"],
                    hovertemplate="%{customdata} Exports FOB: %{y:,.1f}M ISK<extra></extra>",
                ),
                secondary_y=False,
            )
            fig_trade.add_trace(
                go.Bar(
                    x=trade_f["date"],
                    y=-trade_f["imports_cif_isk_m"],
                    name="Goods Imports (-CIF, ISK M)",
                    marker_color="rgba(220, 38, 38, 0.60)",
                    customdata=trade_f["period"],
                    hovertemplate="%{customdata} Imports (-CIF): %{y:,.1f}M ISK<extra></extra>",
                ),
                secondary_y=False,
            )
            fig_trade.add_trace(
                go.Scatter(
                    x=trade_f["date"],
                    y=trade_f["balance_isk_m"],
                    name="Monthly Trade Balance (FOB − CIF)",
                    mode="lines",
                    line=dict(color=PALETTE["navy"], width=2.2),
                    customdata=trade_f["period"],
                    hovertemplate="%{customdata} Balance: %{y:,.1f}M ISK<extra></extra>",
                ),
                secondary_y=False,
            )
            if trade_show_12m:
                fig_trade.add_trace(
                    go.Scatter(
                        x=trade_f["date"],
                        y=trade_f["balance_12m_isk_m"],
                        name="12M Rolling Cumulative Balance",
                        mode="lines",
                        line=dict(color=PALETTE["amber"], width=2, dash="dot"),
                    ),
                    secondary_y=True,
                )
            fig_trade.update_layout(barmode="relative")
            _apply_base_layout(fig_trade, right_margin=50)
            fig_trade.update_yaxes(title_text="Monthly Flow (ISK Millions)", secondary_y=False)
            fig_trade.update_yaxes(title_text="12M Cumul. (ISK M)", secondary_y=True, showgrid=False)
            st.plotly_chart(fig_trade, use_container_width=True, theme=None)
            trade_latest_str = f"{trade_df.iloc[-1]['balance_isk_m']:,.1f}M ISK"
            st.markdown(_chart_metadata_html(series["trade_balance"], trade_latest_str), unsafe_allow_html=True)

        with col6:
            st.subheader("6. Unemployment Rate (Labor Force Survey)")
            fig_unemp = go.Figure()
            fig_unemp.add_trace(
                go.Scatter(
                    x=unemp_f["date"],
                    y=unemp_f["unemp_sa_pct"],
                    name="Unemployment Rate (Seasonally Adjusted, %)",
                    mode="lines",
                    line=dict(color=PALETTE["navy"], width=2.6),
                    fill="tozeroy",
                    fillcolor="rgba(11, 37, 69, 0.08)",
                    customdata=unemp_f["period"],
                    hovertemplate="%{customdata} SA: %{y:.1f}%<extra></extra>",
                )
            )
            if unemp_show_orig:
                fig_unemp.add_trace(
                    go.Scatter(
                        x=unemp_f["date"],
                        y=unemp_f["unemp_orig_pct"],
                        name="Unadjusted Survey Rate (%)",
                        mode="lines",
                        line=dict(color=PALETTE["slate"], width=1.5, dash="dot"),
                        customdata=unemp_f["period"],
                        hovertemplate="%{customdata} Unadjusted: %{y:.1f}%<extra></extra>",
                    )
                )
            _apply_base_layout(fig_unemp)
            fig_unemp.update_yaxes(title_text="% of Labor Force (Ages 16–74)")
            st.plotly_chart(fig_unemp, use_container_width=True, theme=None)
            unemp_latest_str = f"{unemp_df.iloc[-1]['unemp_sa_pct']:.1f}% SA"
            st.markdown(_chart_metadata_html(series["unemployment"], unemp_latest_str), unsafe_allow_html=True)

        st.markdown("---")

        # Bottom tabs: Synthesis, Metadata Table, Automation & Audit Log
        tab1, tab2, tab3 = st.tabs(
            [
                "Macro Assessment & Soft-Landing Check",
                "Series Metadata & Latest Observations",
                "Automated Refresh Schedule & Audit Log",
            ]
        )

        with tab1:
            g_last = gdp_df.iloc[-1]
            c_last = cpi_df.iloc[-1]
            r_last = rate_df.iloc[-1]
            f_last = fx_df.iloc[-1]
            t_last = trade_df.iloc[-1]
            u_last = unemp_df.iloc[-1]
            real_rate = r_last["rate_pct"] - c_last["yoy_pct"]
            st.markdown(
                f"""
                ### Interpreting Recent Developments ({sample_label})
                - **Disinflation & Monetary Stance:** Headline CPI inflation stands at **{c_last['yoy_pct']:.1f}% YoY** ({c_last['period']}), still above the Central Bank of Iceland's **2.5% inflation target**. With the 7-day term deposit policy rate at **{r_last['rate_pct']:.2f}%** ({r_last['date']}), the ex-post real policy rate is **{real_rate:+.2f}%**, maintaining restrictive financial conditions.
                - **Growth & Labor Market Cooling:** Real GDP contracted **{g_last['yoy_pct']:+.1f}% YoY** ({g_last['qoq_sa_pct']:+.1f}% QoQ SA) in **{g_last['period']}**, while seasonally adjusted unemployment stands at **{u_last['unemp_sa_pct']:.1f}%** ({u_last['period']}). Tight monetary policy is clearly cooling domestic demand, pointing to a bumpy rather than effortless soft landing.
                - **External Balance & Króna Stability:** The official USD/ISK mid-rate is **{f_last['isk_per_usd']:.2f} ISK per 1 USD** (and **{f_last['isk_per_eur']:.2f} ISK per 1 EUR**) as of **{f_last['date']}**, supported by high domestic interest rates even as monthly merchandise goods trade recorded a **{t_last['balance_isk_m']:,.1f}M ISK** deficit in **{t_last['period']}** (partially offset in the broader current account by services/tourism exports).
                """
            )

        with tab2:
            summary_rows = []
            for s in series.values():
                summary_rows.append(
                    {
                        "Indicator": s["name"],
                        "Latest Observation Date": s["latest_observation_date"],
                        "Latest Value": s["latest_value"],
                        "Units": s["units"],
                        "Frequency": s["frequency"],
                        "Primary Source": s["source"],
                        "Observations Loaded": len(s["records"]),
                    }
                )
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

            if DATASET_PATH.exists():
                st.download_button(
                    "Download Full Normalized Dataset (JSON)",
                    data=DATASET_PATH.read_text(encoding="utf-8"),
                    file_name="iceland_macro_dataset.json",
                    mime="application/json",
                )

        with tab3:
            st.markdown(
                f"""
                - **Last Successful Refresh (Local):** `{metadata['last_successful_refresh_local']}`
                - **Last Successful Refresh (UTC):** `{metadata['last_successful_refresh_utc']}`
                - **Automated Schedules Configured:**
                  1. **In-App Scheduled Fragment:** Polls primary APIs automatically on the sidebar interval (currently `{schedule_label}`).
                  2. **GitHub Actions Cron (`.github/workflows/refresh_data.yml`):** Runs `python refresh_data.py --trigger scheduled_ci` daily at `12:00 UTC` and commits updated `data/` artifacts.
                  3. **Local Windows Task Scheduler (`scripts/register_windows_task.ps1`):** Optional local daily task runner.
                """
            )
            log_entries = load_refresh_log(limit=20)
            if log_entries:
                log_rows = [
                    {
                        "Refresh Timestamp (UTC)": e.get("last_successful_refresh_utc") or e.get("attempted_at_utc"),
                        "Refresh Timestamp (Local)": e.get("last_successful_refresh_local") or e.get("attempted_at_local"),
                        "Status": e.get("status"),
                        "Trigger": e.get("trigger"),
                        "Duration (s)": e.get("duration_seconds"),
                        "Data Changed": e.get("data_changed_since_prior_refresh"),
                        "Payload Hash": e.get("data_hash"),
                    }
                    for e in log_entries
                ]
                st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No refresh log entries recorded yet.")

    _live_dashboard_body()


if __name__ == "__main__":
    render_dashboard()
