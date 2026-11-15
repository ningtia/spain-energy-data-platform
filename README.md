# Spain Energy Data Platform

A lakehouse for Spanish electricity market and weather data, built with the tools used in
enterprise data teams. It is the shared foundation for two analysis projects:

- **Forecasting** (data science): day-ahead electricity demand / price forecasting
- **Risk** (market risk): VaR/ES, backtesting, stress testing and model validation for power prices

> Status: 🚧 Week 1–2 — ingestion and Bronze layer

## Architecture

```
REE REData API  +  AEMET OpenData API
        │  Python ingestion (energy-ingest), idempotent, retries + backoff
        ▼
Landing zone (raw JSON, Hive-style partitions)
        │  upload → Unity Catalog volume
        ▼
Bronze  (Delta, append-only, Auto Loader)      ┐
        │  PySpark: parse, type, dedupe, TZ    │  Databricks + Delta Lake
Silver  (clean, typed)                         │  medallion architecture
        │  dbt models + data tests             │
Gold    (analytics-ready star schema)          ┘
        │
        ├─▶ Forecasting project
        └─▶ Risk project
Orchestration: Databricks Workflows · CI: GitHub Actions
```

## Data sources

| Source | Data | Granularity | Auth |
|---|---|---|---|
| [REE REData](https://www.ree.es/en/apidatos) | Day-ahead & PVPC prices | hourly | none |
| REE REData | Demand, generation mix | daily | none |
| [AEMET OpenData](https://opendata.aemet.es/) | Temperature, precipitation (5 stations) | daily | free API key |

### What each REE dataset contains

| Dataset | What it is | Unit | Used for |
|---|---|---|---|
| `market_prices` | **Spot price**: day-ahead wholesale price set daily by OMIE's auction (the price generators sell at). **PVPC**: regulated retail price for small consumers = spot + network charges and other costs. | €/MWh | Risk target (spot); retail margin in the portfolio |
| `demand` | Total electricity consumed in Spain per day. | MWh/day | Forecasting target |
| `generation_mix` | Output per technology (nuclear, wind, solar PV, hydro, combined-cycle gas, …), each tagged renewable / non-renewable, with its share of the total. | MWh/day | Features (renewable share pushes prices down); explaining price spikes |

Example from the data: on 1 Jan 2025 (holiday) demand was ~586 GWh vs ~772 GWh on Fri 31 Jan — a
calendar effect the forecasting model must capture. Wind rose from 16% to 25% of the mix while gas
(combined cycle) fell from 22% to 12%. The `percentage` field in `market_prices` (PVPC vs. spot
share) has no economic meaning and is dropped in Silver.

### Why weather data, not just grid data?

Grid data records *what happened* (load, prices); weather explains *why*. It drives both sides
of the market:

- **Demand.** Load is U-shaped in temperature: lowest around 15–20 °C, higher for both heating
  and cooling. Heating/cooling degree days (HDD/CDD) turn this into features a model can learn.
- **Supply.** Wind, sun and rainfall set renewable and hydro output. High renewables push prices
  down (even below zero); calm, cloudy, dry spells push gas to the margin and prices up.
- **Forecasting.** Tomorrow's grid data is unknown, but tomorrow's weather forecast is not.
  Without weather, a model cannot anticipate a heatwave.
- **Risk.** Stress scenarios such as "heatwave + no wind" (summer 2022) need weather to be defined.

*Limitation:* models here use **observed** weather; a production system would use weather
**forecasts**, whose errors would make live performance somewhat worse than the backtest.

### Data notes

- **Spot price arrives at 15-minute resolution** even when requesting `time_trunc=hour`
  (96 values per day vs. 24 for PVPC). Silver aggregates it to hourly so all series align.
- **History starts in 2018** so the risk models are tested on the 2021–2022 energy crisis,
  with 2018–2020 as a pre-crisis baseline.

### Data quality findings (backfill 2018-01-01 → 2026-11-14)

Profiled the raw landing data before building Silver. Each finding drives a Silver rule:

| Finding | Silver rule |
|---|---|
| Spot price: 3,240 / 3,240 days present. DST days correctly have 23 / 25 hours. | Keep; aggregate 15-min → hourly; never assume 24 h/day |
| Spot price is hourly until 2024, 15-minute from 2025-01-01. | Aggregate to hourly mean |
| PVPC only from 2021-06-01 (start of the 2.0TD tariff). | Risk models use spot price only |
| Spot max 700 €/MWh (2022-03-08 19:00, energy crisis); 5,243 negative and 3,107 zero intervals. | Keep: real market outcomes, not errors |
| Demand minimum and nuclear ≈ 0 on 2025-04-28/29 — the **Iberian blackout**. | Keep; flag as an event day |
| Coal generation has negative values (auxiliary consumption of idle plants). | Clip at 0 for share calculations |
| `Fuel + Gas` appears on 39 days, always 0. | Drop |
| AEMET: 5 stations × 3,237 days. Last 3 days missing (AEMET publishes with a ~3-day lag). | Expected; `daily` re-pulls a 7-day window |
| AEMET: mean temperature (`tmed`) blank on some days (Madrid Retiro 109, Barcelona 38, Sevilla 29). | Fill with (tmin + tmax) / 2; else re-weight over available stations |
| AEMET numbers use a decimal comma (`"8,4"`). | Replace `,` → `.` and cast to double |
| Duplicate days: (a) smoke-test files overlap backfill chunks with different boundaries; (b) REE sometimes returns days just outside the requested range. Values are identical. | Deduplicate on (indicator, timestamp), keep latest `ingested_at` |

*Lesson:* deterministic file names make a re-run of the **same** range idempotent, but runs with
different chunk boundaries can still overlap — so deduplication belongs in Silver, not in landing.

## Quickstart

```bash
git clone https://github.com/<you>/spain-energy-data-platform.git
cd spain-energy-data-platform
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,databricks]"
cp .env.example .env          # add your AEMET_API_KEY

energy-ingest ree --dataset market_prices --start 2025-01-01 --end 2025-01-01   # smoke test
energy-ingest ree   --start 2018-01-01 --end 2026-11-14                         # backfill
energy-ingest aemet --start 2018-01-01 --end 2026-11-14
energy-ingest upload                                                            # → Databricks
```

Then run `databricks/notebooks/00_setup.sql` once and `01_bronze_ingest.py` in Databricks.

## Design decisions

- **Raw first.** Landing and Bronze keep API responses exactly as received; parsing happens in
  Silver. A format change at the source cannot break ingestion, and history can be re-parsed.
- **Idempotent landing.** File names are deterministic per source/dataset/date range, so
  re-running a range overwrites instead of duplicating.
- **Incremental by default.** `energy-ingest daily` re-pulls a trailing 7-day window, because
  sources revise recent data and AEMET publishes with a delay.
- **Resumable and fault-tolerant.** Backfills skip chunks already in landing, so an interrupted
  run resumes where it stopped. A failing chunk (e.g. AEMET rate limit, HTTP 429) is logged and
  skipped instead of aborting the run; the command exits non-zero and lists what to retry.
- **Secrets never land.** API keys live in `.env` (git-ignored) and are excluded from stored
  request metadata — this is unit-tested.

## Repo layout

```
src/energy_platform/     ingestion package (config, HTTP, sources, landing, upload, CLI)
databricks/notebooks/    00_setup.sql, 01_bronze_ingest.py (Silver/Gold to follow)
tests/                   unit tests with mocked HTTP
.github/workflows/       CI: ruff + pytest
```

## Roadmap

- [x] Ingestion: REE + AEMET, retries, idempotent landing
- [x] Bronze: Auto Loader into Delta
- [ ] Silver: typed tables, Europe/Madrid timezone & DST handling, dedupe, weighted temperature
- [ ] Gold: dbt star schema + data tests
- [ ] Daily Databricks Workflow
