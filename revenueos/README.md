# RevenueOS

**AI Revenue Intelligence for independent fashion boutiques.**

RevenueOS turns boutique customer and inventory data into the next best revenue
action. It reads whatever exports your POS produces, works out who is worth
contacting today, what to recommend them and why, which stock is quietly turning
into dead money, and what that is all worth — then lets you ask questions about
any of it in plain language.

The product's guiding constraint: **every number is computed, never generated.**
The analytics engine is deterministic Python. Claude is the reasoning and
narration layer on top of it, and it reaches your data only through a fixed set
of analytics functions — so there is no path by which it can invent a customer,
a product or a figure and present it as fact.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Installation](#installation)
- [Environment variables](#environment-variables)
- [Running it](#running-it)
- [Importing your data](#importing-your-data)
- [How the AI works](#how-the-ai-works)
- [How product matching works](#how-product-matching-works)
- [Demo mode](#demo-mode)
- [Testing](#testing)
- [Privacy and GDPR](#privacy-and-gdpr)
- [Known limitations](#known-limitations)
- [Next production steps](#next-production-steps)

---

## What it does

| Question a boutique owner actually asks | Where RevenueOS answers it |
| --- | --- |
| Who should I contact today? | Overview → Today's priorities; Opportunities |
| What do I recommend to this client? | Customer 360; Recommendations → For a customer |
| Who would buy this new arrival? | Product detail; Recommendations → For a product |
| Who is about to churn? | Customers (filter: overdue); churn risk per profile |
| Which stock is turning into dead money? | Inventory; risk score with its drivers |
| What should I push this week? | Opportunities; Insights → Recommended actions |
| Who should I invite to a private sale? | Campaigns → VIP private sale |
| What if I discount these 15%? | Scenario Lab |
| Why did sales fall this month? | AI Analyst; Insights |

Eleven sections: Overview, AI Analyst, Customers, Recommendations, Inventory,
Opportunities, Campaigns, Scenario Lab, Insights, Data, Settings.

---

## Architecture

```
revenueos/
├── backend/                    FastAPI + pandas. All intelligence lives here.
│   ├── app/
│   │   ├── main.py             App wiring, error handling, CORS
│   │   ├── config.py           Env-driven settings; secrets never leave here
│   │   ├── store.py            Workspace state, analytics cache, SQLite persistence
│   │   ├── serialisation.py    DataFrame → JSON, preserving null ≠ 0
│   │   ├── data/               Ingestion and understanding
│   │   │   ├── ingestion.py      Encodings, delimiters, EU decimals, preamble rows
│   │   │   ├── schema.py         Canonical model + multilingual alias registry
│   │   │   ├── mapping.py        Fuzzy + semantic column mapping with confidence
│   │   │   ├── parsing.py        Dates, sizes, colours, gender normalisation
│   │   │   ├── cleaning.py       Typed canonical tables; absence stays absence
│   │   │   └── validation.py     Data Health Score + capability map
│   │   ├── analytics/          Deterministic. No LLM touches these numbers.
│   │   │   ├── customer_scoring.py  Metrics, affinities, churn, predicted value
│   │   │   ├── rfm.py               Adaptive RFM segmentation
│   │   │   ├── inventory.py         Ageing, sell-through, risk, action
│   │   │   ├── matching.py          Customer × product with weight redistribution
│   │   │   ├── opportunities.py     Opportunity discovery and scoring
│   │   │   └── forecasting.py       Trends, breakdowns, scenario models
│   │   ├── ai/                 Claude integration
│   │   │   ├── client.py            Anthropic wrapper; graceful degradation
│   │   │   ├── prompts.py           System prompts, all anti-hallucination
│   │   │   ├── context_builder.py   PII-minimised payload construction
│   │   │   ├── tools.py             The only functions Claude may call
│   │   │   └── analyst.py           Intent → analytics → interpretation
│   │   ├── demo/generator.py   Correlated synthetic boutique
│   │   └── routers/            11 API routers
│   └── tests/                  190 tests
└── frontend/                   Next.js 15 · React 19 · TypeScript · Tailwind 4
    ├── app/                    App Router pages
    ├── components/             Shell, command palette, UI primitives, charts
    └── lib/                    API client, formatters, design tokens
```

### Data flow

```
CSV/XLSX  →  ingestion  →  mapping  →  cleaning  →  canonical tables
                                                          ↓
                        ┌─────────────────────────────────┤
                        ↓                                 ↓
              customer metrics + RFM              inventory metrics
                        ↓                                 ↓
                        └──────────→ matching ←───────────┘
                                        ↓
                                 opportunities
                                        ↓
                         API  →  UI  ·  AI Analyst (narration)
```

The whole pipeline runs once per data change and is cached on the workspace, so
page loads are reads rather than recomputations.

---

## Installation

Requires **Python 3.11+** and **Node 20+**.

```bash
git clone <this repo>
cd revenueos
cp .env.example .env          # optional: add your Anthropic key

make install                  # backend deps + frontend deps
```

Or manually:

```bash
cd backend  && pip install -r requirements.txt
cd frontend && npm install
```

---

## Environment variables

All read by the **backend**. Nothing here reaches the browser.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | *(unset)* | Enables written AI narration. Everything analytical works without it. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5-20250929` | Model used for narration and the analyst. |
| `ANTHROPIC_MAX_TOKENS` | `2000` | Response cap. |
| `REVENUEOS_DATA_DIR` | `backend/var` | SQLite database and cached tables. |
| `REVENUEOS_CURRENCY` | `EUR` | Display currency. |
| `REVENUEOS_MINIMISE_PII` | `true` | Strip emails, phones and notes before any LLM call. |
| `REVENUEOS_CORS_ORIGINS` | `localhost:3000` | Comma-separated allowed origins. |
| `API_URL` | `http://127.0.0.1:8000` | Where the **Next.js server** proxies `/api/*`. |

**Without an API key the product is fully functional.** Scores, segments,
matches, risk, opportunities and scenarios are all deterministic. What you lose
is prose: the analyst answers with computed tables instead of written analysis,
and briefings are composed from the same figures rather than written. Every
screen says which mode it is in.

---

## Running it

### One command

```bash
docker compose up --build
```

→ web on <http://localhost:3000>, API on <http://localhost:8000>
(interactive API docs at `/docs`).

### Locally

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev
```

Then open <http://localhost:3000> and click **Load demo boutique**.

The browser only ever calls same-origin `/api/*`; Next.js proxies to FastAPI.
The API host — and any credential you later add — stays out of the client bundle.

---

## Importing your data

RevenueOS accepts **arbitrary CSV, TSV and Excel exports**. There is no template.

### What it handles without being told

- Encodings: UTF-8, UTF-8 with BOM, Windows cp1252, latin-1
- Delimiters: `,` `;` tab `|` — detected by parse consistency, not guesswork
- European decimals (`1.234,56`), US decimals, currency symbols, spaces as
  thousands separators, accounting negatives `(120)`
- Dates in any common order, with day-first vs month-first decided **per column**
  from the evidence in that column (so `03/04` and `04/03` never get read with
  different meanings)
- Preamble junk above the real header row
- Duplicate and blank column names
- Fully empty rows and columns

### The mapping step

Column mapping blends three independent evidence sources:

1. **Lexical** — exact alias matches, token overlap and fuzzy string similarity,
   against a registry covering English, Italian, French, Spanish and German
   (`Nome Cliente`, `Codice Articolo`, `Kundennummer`, `Giacenza`, `Ultimo
   Acquisto`, …).
2. **Value archetype** — what the cells actually contain: do they parse as dates,
   as money, as emails; how unique are they; what magnitude are they.
3. **Structural** — uniqueness for identifiers, cardinality for categories.

These blend into a 0–1 confidence, and a greedy one-to-one assignment resolves
competition between columns. The UI shows every decision:

```
Nome Cliente     →  Customer Name       98%   header matches a known name
Ultimo Acquisto  →  Last Purchase Date  94%   97% of values parse as dates
Totale           →  Lifetime Spend      88%   values are numeric (median 1,240)
```

Anything below the confidence bar is **left for you to confirm** rather than
silently guessed, and you can override any mapping before importing.

Value evidence can override a misleading header: a column called `Codice` full of
valid email addresses is mapped as email, whatever it is named.

### Partial data

The system works with whatever it gets. Upload only customers and you get
segmentation and prioritisation. Add transactions and you get real affinities,
purchase rhythms and trends. Add inventory and matching switches on. The **Data
health** tab shows exactly which capabilities are live, which are partial, and
what each missing one would need.

**A missing value is never a zero.** A product with no price has `null`, not €0,
and every metric derived from it reports "Not enough information" rather than
inventing a number.

---

## How the AI works

```
USER QUESTION
     ↓
Claude selects an analytics tool          ← it cannot query the data any other way
     ↓
Deterministic Python/pandas computation   ← every number originates here
     ↓
Result dataset (PII-minimised)
     ↓
Claude interprets and writes the answer
     ↓
Answer + the table it came from
```

Nine tools are exposed: `find_customers`, `recommend_products_for_customer`,
`recommend_customers_for_product`, `find_products`, `get_opportunities`,
`get_performance`, `get_segments`, `get_inventory_summary`, `simulate`. The model
chooses which to call and how to interpret what comes back. It never computes.

The system prompts are explicit: every figure must come from a tool result;
"not enough information" is the required answer when the data cannot support one;
and arithmetic the tools can do must be delegated rather than performed. The UI
shows which analyses were run for each answer.

### Without a key

The analyst still answers. A deterministic intent router picks the same tools and
the response is composed from the returned figures as a table. It is not a
degraded imitation — it runs the identical analytics — it simply does not write
prose. The mode is always labelled.

---

## How product matching works

Ten weighted signals:

| Signal | Weight | What it measures |
| --- | --- | --- |
| Category preference | 22% | Share of this customer's spend in the product's category |
| Price affinity | 15% | Fit against their observed price band |
| Brand affinity | 14% | Whether they buy this brand, and how much |
| Size compatibility | 13% | Distance from the sizes they actually buy |
| Purchase pattern | 10% | Repeat-vs-considered category, readiness, already owned |
| Colour preference | 9% | Their palette, including neutral bias |
| Gender fit | 5% | Catalogue line against their profile |
| Inventory priority | 5% | Stock risk and margin |
| Seasonal relevance | 4% | Whether the season is current |
| Newness | 3% | How recently it arrived |

### The rule that matters

> **Missing information is not a negative signal.**

A signal that cannot be computed — no colour data, no size history, no cost — is
**removed from the calculation and its weight redistributed** across the signals
that can be computed. The score therefore always means *"how good a fit is this,
given what we actually know"*. A boutique that never exports colours does not see
every recommendation collapse to 0%.

This is the specific defect the previous version had, and it is covered by an
explicit regression test: a catalogue containing nothing but an id, a name and a
stock count still produces ranked recommendations with non-zero scores.

### Not disguising thin evidence

Two mechanisms keep the score honest:

1. **Affinity shares are Bayesian-smoothed** towards the base rate by the volume
   of evidence behind them. One purchase of a coat is not a 100% preference for
   coats; it is pulled towards neutral until repeat behaviour confirms it.
2. **Score and confidence are separate outputs.** A match built on two signals
   and one receipt is reported as `71% · low confidence`, not as certainty.

### Explainability

Every match returns machine-readable reasoning:

```json
{
  "score": 0.87,
  "dataConfidence": "high",
  "signalCoverage": 0.92,
  "signals": [
    { "name": "Category preference", "impact": 0.24, "direction": "positive",
      "reason": "45% of their spend is in Coats" },
    { "name": "Price affinity", "impact": 0.18, "direction": "positive",
      "reason": "€890 sits inside their usual €400–€1,200 range" }
  ],
  "missingSignals": ["Colour preference"]
}
```

The signal impacts sum to the score, so the arithmetic is auditable. The UI
renders this as a bar breakdown with plain-language reasons, and names the
signals that were not used and why.

### Both directions, one implementation

"Products for a customer" and "customers for a product" run the same signal
maths on numpy arrays. Ranking the whole customer base against one product takes
~50ms for 165 customers.

---

## Demo mode

**Load demo boutique** populates everything from a simulated Milan boutique:
165 customers, 320 products, 1,650+ transactions.

The data is not random. Customers are drawn from ten behavioural personas — a
brand devotee, a dormant VIP, a markdown hunter, a lapsed one-timer, an emerging
high-potential — and every transaction is generated from that persona's own
brand, category, palette, price ceiling, purchase rhythm and discount appetite.
Stock levels are derived from what actually sold, so some products genuinely
become dead stock.

The persona labels are then **discarded**. The analytics rediscover the patterns
from the transaction ledger alone, which is the point: the demo demonstrates the
engine rather than faking it. The demo also loads through the real import
pipeline — the same mapping and cleaning your files go through.

---

## Testing

```bash
cd backend && python -m pytest tests/ -q
```

190 tests covering:

| File | What it protects |
| --- | --- |
| `test_ingestion.py` | Number formats, delimiters, encodings, dates, sizes, colours, malformed files |
| `test_mapping.py` | Multilingual headers, value-over-header evidence, entity detection, partial data |
| `test_matching.py` | **Missing data never produces 0%**, weight redistribution, explainability, both directions |
| `test_analytics.py` | Customer metrics, adaptive RFM, inventory ageing, opportunity scoring |
| `test_quality.py` | Health score, issue detection, capability map |
| `test_api.py` | Every endpoint, the upload → map → commit flow, GDPR deletion |

The load-bearing tests:

- `test_score_survives_when_every_optional_field_is_missing` — the 0% regression
- `test_dropping_any_single_dimension_keeps_scores_meaningful` — per-signal
- `test_segmentation_adapts_to_the_datasets_own_distribution` — identical
  relative behaviour segments identically at any price level
- `test_a_new_arrival_that_has_not_sold_is_not_at_risk` — stock maturity
- `test_uncomputable_metrics_stay_null_rather_than_zero` — no fake zeros
- `test_demo_behaviour_is_correlated_not_random` — the demo proves the engine

---

## Privacy and GDPR

- **Local by default.** Files are parsed and stored by the backend you run.
  Nothing goes to a third-party analytics service.
- **PII minimisation.** With `REVENUEOS_MINIMISE_PII=true` (the default), emails,
  phone numbers, birth dates and free-text notes are stripped before any payload
  reaches Claude. Customers are identified by internal ID and display name — what
  an owner needs to know who to call, and nothing beyond it.
- **Aggregation first.** The analyst receives computed *results*, not raw tables.
- **No key in the browser.** The API key is read server-side. The browser calls
  same-origin `/api/*` and never sees a credential.
- **Right to erasure.** Data → Privacy → *Erase all data* removes every table and
  derived artefact from disk and memory immediately.
- **Consent respected.** Campaign audiences exclude customers whose consent field
  says no, and the exclusion is stated in the campaign's selection criteria.
- **No sending.** RevenueOS drafts outreach; it does not transmit it. Sending
  requires an integration you configure yourself.

---

## Known limitations

1. **Single workspace, no authentication.** The store supports multiple
   workspaces internally but the API serves one, and there are no user accounts.
   This is a local-first tool today, not a multi-tenant SaaS.
2. **Scenario elasticity is an assumption, not a measurement.** The discount
   model uses a stated constant elasticity (1.6) because most boutiques lack the
   discount history to estimate their own. The assumption is displayed with every
   result, and scenarios are labelled estimates throughout.
3. **Analytics are in-process pandas.** Comfortable to roughly 100k customers and
   1m transactions on a normal machine. Beyond that the pipeline should move to
   DuckDB queries over Parquet rather than in-memory frames.
4. **The full pipeline recomputes on every data change** (~4s for the demo).
   There is no incremental update path yet.
5. **Cross-sell adjacencies are a hand-written table.** They work for standard
   fashion categories but do not learn from co-purchase data.
6. **Prediction is heuristic, not learned.** Churn risk and 12-month value use
   explicit formulas over observed behaviour, not a trained model. This is a
   deliberate trade for explainability with small datasets, but a boutique with
   years of history could do better.
7. **Excel import needs `openpyxl`**, which is not in `requirements.txt` — CSV is
   the tested path.
8. **No seasonality decomposition.** Trends are period-over-period comparisons;
   a genuinely seasonal business will see swings that are not really changes.
9. **The AI Analyst has no memory across sessions.** Conversation history is
   passed within a session only.

---

## Next production steps

**Before customers:**

1. **Authentication and multi-tenancy** — accounts, per-workspace isolation, and
   moving the store to Postgres/Supabase (the persistence layer is already
   confined to `store.py` for exactly this).
2. **Background job queue** for the analytics pipeline so large imports do not
   block a request.
3. **Rate limiting and cost controls** on the analyst endpoint.
4. **Audit log** of every recommendation shown and every action taken.

**To make it stickier:**

5. **Outcome tracking.** The pipeline already records contacted/won/lost. Feeding
   those outcomes back to calibrate match weights per boutique turns a good
   heuristic into a learning system — the single highest-value next step.
6. **POS connectors** (Lightspeed, Shopify, Retail Pro) so data arrives
   continuously instead of by upload.
7. **Outreach integrations** — WhatsApp Business, Klaviyo, Mailchimp — to close
   the loop from recommendation to sent message.
8. **Mobile view for the shop floor.** The associate holding a phone next to a
   client is the real user of Customer 360.

**Analytical depth:**

9. **Learned co-purchase affinities** replacing the hand-written adjacency table.
10. **Proper survival modelling** for churn, once a boutique has enough history.
11. **Size-curve and buying recommendations** — what to re-order, not just what
    to sell.
