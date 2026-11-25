# Prompt Used to Produce the Dashboard

Below are the exact instructions provided to the AI coding agent to build, automate, and verify the Iceland Macroeconomic Monitor dashboard:

```text
Choose the country of Iceland whose economy you would like to monitor. Use an AI coding agent to build a dashboard that helps answer your question and updates automatically as new data become available.

Select and present your data
Choose 4–8 relevant indicators that will help you visualize the country’s performance. Use reliable primary sources, such as central banks, national statistical agencies, or international organizations. Avoid secondary sources such as social media.

1. Real GDP Growth (YoY % or Quarterly SA) — Units: %; Frequency: Quarterly; Source: Statistics Iceland / IMF; Transformations: YoY % or annualized growth rate.
2. Consumer Price Index (CPI) Inflation (YoY %) — Units: Index (base = 100 or reference period) and % YoY; Frequency: Monthly; Source: Statistics Iceland; Transformations: 12-month percentage change ((CPI_t / CPI_{t-12} - 1) * 100).
3. CBI Policy Interest Rate (7-Day Term Deposit Rate) — Units: % per annum; Frequency: Policy meeting / monthly; Source: Central Bank of Iceland.
4. Exchange Rate (ISK per USD or EUR) — Units: ISK per 1 USD (state clearly whether direct/indirect quotation and whether rising ISK means króna depreciation or appreciation); Frequency: Daily/Monthly; Source: Central Bank of Iceland / IMF ER data.
5. Merchandise Trade Balance or Goods Exports/Imports — Units: ISK millions (or USD millions); Frequency: Monthly; Source: Statistics Iceland.
6. Unemployment Rate — Units: % of labor force; Frequency: Monthly or Quarterly; Source: Statistics Iceland (Labor Force Survey).

For each chart, report the units, data frequency, source, and latest observation date. Specify exchange rate quotation conventions and explain any transformations, such as growth rates or rebasing an index. Choose a sample period that provides enough context to interpret recent developments.

Automate and verify the refresh
Configure the dashboard to retrieve data and update its charts on a regular schedule. Display the date and time of the last successful refresh separately from the latest observation date.

Check at least one observation from each series against its original source. Demonstrate a successful refresh using a screenshot or log. A successful refresh need not produce different values if the source has released no new data.

Submit your work
Submit:
- Your dashboard: an example of the dashboard you produced.
- Your prompt: the instructions you used to produce the dashboard.
- Evidence of verification: document your data checks and successful refresh.

Maybe use a Github / Streamlit setup (app.py, requirements.txt, README.md)
```
