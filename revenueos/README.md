# RevenueOS

**AI revenue intelligence for fashion boutiques.**
RevenueOS turns a boutique's customer and inventory data into the next best revenue action:
who to contact today, what to recommend them, and why it matters now.

It is built around one rule: **every number is computed, and every claim is traceable.**
Deterministic Python does the analysis; Claude is the reasoning and explanation layer on top.

---

## What it does

| Area | What you get |
|---|---|
| **Data ingestion** | Drop in any CSV export. Delimiter, encoding, European decimals, preamble junk and header language are detected automatically. Columns are mapped semantically (English/Italian/French/Spanish/German) with a confidence score and a manual override. |
| **Data health** | A 0–100 score, concrete findings, and a capability map: what your data supports today and which column would unlock the next capability. |
| **Customer analytics** | Lifetime value, AOV, cadence, recency, tenure, trajectory, category/brand/colour/size affinity, price band, discount sensitivity — plus adaptive RFM segmentation scored against *your* population, not fixed thresholds. |
| **Inventory intelligence** | Ageing, sell-through, velocity, weeks of cover, margin, and an explainable risk score that classifies Hot → Dead Stock, with a recommended action that never opens with "discount". |
| **Matching engine** | Customer × product scoring across eight signals with dynamic weight redistribution, machine-readable explanations, and a data-confidence rating separate from the match score. |
| **Opportunities** | Ranked commercial plays (overdue VIPs, dead-stock rescue, new-arrival targets, reactivation, cross-sell, category momentum, size gaps) scored by probability × value × urgency × confidence. |
| **AI Analyst** | Ask questions in plain language. Claude selects RevenueOS analytics tools, reads the real results, and explains them. It never computes a number itself. |
| **Campaigns & Scenario Lab** | Build an audience from computed signals with a drafted message; model discounts, outreach and category focus with stated assumptions. |

---

## Architecture

```
revenueos/
├── backend/                 FastAPI + deterministic analytics + Claude
│   ├── app/
│   │   ├── data/            ingestion.py  mapping.py  cleaning.py  validation.py
│   │   │                    schema.py (canonical fields + multilingual aliases)
│   │   │                    values.py (number/date/bool parsing that returns None, never 0)
│   │   ├── analytics/       customer_scoring.py  rfm.py  inventory.py
│   │   │                    matching.py  opportunities.py  forecasting.py  taxonomy.py
│   │   ├── ai/              client.py  prompts.py  context_builder.py  tools.py  analyst.py
│   │   ├── demo/            generator.py (correlated synthetic boutique)
│   │   ├── routers/         data, customers, products, opportunities, analyst, campaigns, scenarios
│   │   ├── workspace.py     pipeline orchestration + caching + persistence
│   │   └── main.py
│   └── tests/               55 tests
└── frontend/                Next.js 14 (App Router) + TypeScript + Tailwind
    ├── app/                 overview, analyst, customers, inventory, opportunities,
    │                        campaigns, scenarios, insights, data
    ├── components/          Shell (nav + ⌘K palette), ui, charts (hand-rolled SVG)
    └── lib/                 api client, formatting
```

**Data flow.** Upload → parse → detect mapping → confirm → clean into typed records →
one pipeline run (profiles → RFM → product stats → quality → opportunities) → cached in the
workspace → every endpoint reads the cache. Recomputation happens on import, not per request.

---

## Running it

### Docker (one command)

```bash
cd revenueos
cp .env.example .env          # optional: add ANTHROPIC_API_KEY
docker compose up
```

Open <http://localhost:3000>.

### Local

```bash
# backend
cd revenueos/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8000

# frontend (second terminal)
cd revenueos/frontend
npm install
npm run dev
```

Open <http://localhost:3000> and choose **Explore demo boutique** — 160 customers,
300 products and 2,200 transactions with realistic correlated behaviour.

### Environment

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Server-side only. Enables the conversational analyst and AI narratives. Everything else works without it. |
| `BACKEND_URL` | Where the frontend proxies `/api` (default `http://127.0.0.1:8000`). |
| `CORS_ORIGINS` | Comma-separated allowed origins for the API. |

### Tests

```bash
cd revenueos/backend && .venv/bin/python -m pytest tests -q
```

---

## Importing your data

Three exports are enough — customers, transactions, products — and **any subset works**.

The importer handles: `,` `;` tab `|` delimiters · UTF-8/UTF-16/CP1252/latin-1 · BOMs ·
`1.234,56` and `1,234.56` · `dd/mm/yyyy` and `yyyy-mm-dd` · `(250)` negatives · currency
symbols · preamble rows above the header · headerless files · ragged rows · duplicate headers.

Mapping combines three signals:

1. **Lexical** — normalised header vs. a multilingual alias list (exact, containment, token overlap, fuzzy).
2. **Semantic** — a profile of the actual values (emails? dates? money? near-unique IDs?).
3. **Arbitration** — each canonical field is claimed by at most one column; the strongest wins.

Values can veto a misleading header: a column called `Date` containing email addresses will
not be mapped as a date. Anything below the confidence threshold is flagged for review, and
every column can be remapped by hand.

---

## How the AI works

```
question → Claude → picks RevenueOS analytics tools → deterministic Python runs
        → real results → Claude interprets → answer + the queries behind it
```

- **Model:** `claude-opus-5` with adaptive thinking, via the official `anthropic` SDK.
- **Tools:** twelve read-only analytics functions (customers, matching, inventory,
  opportunities, trends, data health). Claude cannot compute — it can only query and explain.
- **Grounding:** the system prompt forbids stating any figure that did not come from a tool
  result, and forbids inventing customers or products.
- **Privacy:** email, phone, address and birth date are stripped before anything reaches the
  API (`ai/context_builder.minimise`). Claude sees internal IDs and computed metrics.
- **No key, no problem:** without `ANTHROPIC_API_KEY` every surface falls back to a
  deterministic, data-derived summary labelled `engine: "computed"`. Nothing ever pretends
  to be model reasoning.

---

## How product matching works

Eight signals, each scored 0–1 and each declaring whether it is **applicable**:

| Signal | Nominal weight |
|---|---|
| Category fit | 25% |
| Brand fit | 15% |
| Price fit | 15% |
| Size availability | 15% |
| Colour fit | 10% |
| Buying pattern | 10% |
| Inventory priority | 5% |
| Newness | 5% |

**The rule that fixes the old engine's 0% matches:**

> A signal we cannot measure is *excluded from the average*, not scored zero.

Only applicable signals contribute, and their weights are renormalised to sum to 1. A boutique
with no colour data gets the same scale with fewer inputs — and a lower **data confidence**,
which is reported separately from the match score. Missing information is never a negative signal.

Three further guarantees:

- **Hard gates, not silent penalties.** Out of stock or a gender mismatch removes a product
  from consideration; unknown stock does *not* count as zero stock.
- **Category coherence.** Price, stock and timing can never carry an unrelated category to the
  top — weak category fit caps the whole match.
- **Customer-specific.** A match needs at least one customer-derived signal; product-only
  signals (inventory priority, newness) cannot produce a "match" on their own.

Every match returns machine-readable signals whose impacts sum exactly to the reported score,
so the UI can show precisely why a recommendation was made — and which signals were missing.

---

## Design principles

1. **Never fake a number.** Unknown renders as "—" with a tooltip, never as `0` or `0%`.
2. **Every metric answers "so what?"** — each surfaces an action, not a statistic.
3. **Best case and expected value are different.** Headline figures are probability-weighted;
   the optimistic number is shown beside it, labelled.
4. **Consent gates outreach.** Unknown consent is not consent; those customers are excluded
   from campaign forecasts and flagged in the UI.
5. **Targeted selling before markdown.** No recommended action opens with a discount.

---

## Known limitations

- **Single workspace.** State is one in-process workspace persisted to a JSON snapshot. There
  is no auth or multi-tenancy — see next steps.
- **Conversion rates are priors, not learned.** Opportunity probabilities come from
  conservative retail defaults, not from this boutique's measured response. They will be
  wrong in the specific until outcome data accumulates.
- **Scenario Lab elasticity is an assumption.** Discount modelling uses a fixed elasticity,
  stated in the output. It compares options; it does not forecast.
- **No incrementality measurement.** Revenue attributed to an action is not proof the action
  caused it. A treatment/control holdout is the honest next step.
- **Recomputation is full, not incremental.** Fine to ~100k customers in-process; beyond that
  the pipeline should move to DuckDB/Postgres with incremental updates.
- **Analyst history is client-side** and not persisted between sessions.

## Recommended next steps for production

1. **Persistence & multi-tenancy** — Postgres (or Supabase) per boutique, with auth and
   row-level isolation; DuckDB for the analytical queries.
2. **Outcome loop** — record what the advisor did and what happened, then replace the prior
   conversion rates with measured ones per segment and play.
3. **Holdout experiments** — a control group per campaign so "incremental revenue" becomes
   measured rather than modelled.
4. **Background jobs** — move the pipeline to a worker (Celery/RQ) with incremental
   recomputation on import instead of a synchronous rebuild.
5. **Native connectors** — Shopify, Lightspeed and common Italian POS systems, so the CSV
   path becomes the fallback rather than the default.
6. **Outreach integrations** — WhatsApp Business and email, with consent and frequency caps
   enforced server-side and every send written to an audit log.
