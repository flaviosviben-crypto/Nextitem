# RevenueOS

**Your advisors have 500 customers each and don't know who to call.
RevenueOS gives them the 10 that matter today.**

One loop, and nothing outside it:

```
Data  →  Decision  →  Action  →  Measurable revenue outcome
```

Sophisticated intelligence underneath. A simple commercial product on top.

---

## The product

Six screens. Everything else was removed on purpose — an advisor reading charts
is an advisor not calling customers.

| Screen | What it is for |
|---|---|
| **Overview** | How much work is waiting today, and whether last month's work paid off. A signpost, not a dashboard. |
| **Today's Opportunities** | The heart of the product. The customers worth a conversation today, each with one reason and one thing to do. |
| **Action Center** | What the advisor committed to: Approved → Scheduled → Contacted → Converted / Ignored, with an audit trail behind every change. |
| **Customers** | The base, filtered by value *or* by buying cycle. Customer Detail answers one question: why is RevenueOS telling me to contact this person? |
| **Performance** | Opportunities detected, customers contacted, conversion rate, and revenue — separated into what was observed and what is estimated. |
| **Data** | Three standard exports in, mapped automatically, with a health score and a plain list of what is missing. |

The analyst tool-runner, campaign builder and scenario modelling are still in the
codebase and still mounted on the API. They are not in the navigation, because
they are not part of the first sale.

---

## Today's Opportunities

Every card answers five questions, in the order an advisor thinks:

1. **Who** — the customer, with their value tier and where they are in their cycle.
2. **Why now** — *"Last bought 37 days ago against a 26-day buying cycle."*
3. **What** — the specific piece to put in front of them.
4. **Why that piece** — *"Leather Goods is 86% of their spend · Size One Size is the size they buy in leather goods · €1,100 sits inside their usual €400–€1,110."*
5. **How to act** — named only in a channel that customer has actually agreed to.

### Detected and prioritized are different numbers

RevenueOS reports two counts everywhere, and they mean different things:

| | What it is |
|---|---|
| **Detected** | Every customer that met the engine's criteria. The opportunity universe. |
| **Prioritized for today** | The subset RevenueOS recommends actually working now. |

> 102 opportunities detected → 20 prioritized for today

The value is not the size of the pile. It is how little of it needs working.

The selection is a rule, not a display limit: an opportunity must clear a
**priority bar** (`PRIORITY_BAR`) *and* have an open contact channel, and the day
has a **capacity cap** (`DAILY_CAP`). Anything that clears the bar but exceeds
capacity is reported as *held back* rather than silently dropped.

The decision is made once per pipeline run and stamped onto every detected
opportunity, so Overview, Opportunities, Action Center and Performance read one
answer instead of each computing its own.

Two rules govern the list:

- **It is never padded.** If seven customers deserve a call today, the advisor
  sees seven. There is a ceiling (nobody makes fifty personal calls in a
  morning) but no floor.
- **Lifecycle does not set priority.** A VIP who has lapsed can outrank a
  Standard customer who is due. Value, timing, money, product fit and
  reachability are combined; no single dimension wins alone.

Match scores, conversion probabilities and priority numbers exist — in the
backend. The card shows evidence the advisor can verify, not a score they have
to trust.

---

## Value and lifecycle are two different things

The old model collapsed *how valuable is this customer* and *where are they in
their buying rhythm* into one label. That produced commercially wrong output: a
VIP one day past their cycle was filed alongside a lapsed bargain-hunter and
quietly demoted to a broadcast campaign.

They are now independent, and a customer is the pair — **"VIP · Due"**.

| Value | Meaning |
|---|---|
| **VIP** | Demonstrated high value — protect the relationship. |
| **Promising** | Rising trajectory — invest now to grow them into a VIP. |
| **Standard** | No strong value signal yet. |

| Lifecycle | Position in their own cycle |
|---|---|
| **Active** | ≤ 100% — inside their normal rhythm. |
| **Due** | 100–150% — the moment to make contact. |
| **At Risk** | 150–250% — meaningfully beyond their rhythm. |
| **Lost** | > 250% — needs a genuine win-back. |

> A customer **107% through their cycle is Due, not Lost.**

Those boundaries are a sensible starting point for premium retail, not a
universal truth, and they are configurable per boutique
(`analytics/segmentation.LIFECYCLE_THRESHOLDS`) — a jeweller and a denim store
do not share a definition of overdue.

### Cycles are only stated when they are known

A confident *"buys every 16 days"* derived from two receipts is worse than an
honest range. The estimate falls back through four levels and always says which
one it used:

| Source | When | Confidence |
|---|---|---|
| The customer's own median gap | 4+ purchases | High |
| Their gaps, pulled toward their cohort | 3 purchases | Medium |
| A cohort median (category × store → category → store → the whole base) | fewer | Low |
| Absolute recency, with no cycle claimed | no usable history | — |

Customer Detail prints the basis verbatim: *"Typical for customers buying the
same category — too few purchases to be sure."*

---

## Compliance is invisible and absolute

RevenueOS must never say *"WhatsApp this customer today"* about someone who has
not agreed to WhatsApp. Eligibility is therefore resolved **before** an
opportunity is written, not checked afterwards in the UI.

Every customer resolves to one of two states:

- **Actionable** — an outreach channel is open, and the action names it.
- **Suppressed** — with a plain reason, plus whatever remains possible
  (*"You can still speak to them in the boutique."*).

The rules, all failing closed:

- Consent is per channel; a specific *no* beats a general *yes*.
- Unknown consent is not consent.
- A channel needs the contact detail it requires — WhatsApp consent without a
  phone number opens nothing.
- A 21-day frequency cap holds outreach after a recorded contact.
- `do_not_contact` is absolute: no channel, no workaround.
- Every advisor decision is written to an audit log (`GET /api/audit`).

---

## Honest measurement

Performance reports revenue in layers, because the honest answer has layers:

| Figure | What it actually proves |
|---|---|
| **Revenue from contacted customers** | All their spend in the window. Observed — not evidence the contact caused it. |
| **Revenue after contact** | Spend within 30 days *after* a recorded contact. Observed and time-linked. Still not proof of cause. |
| **Sales recorded by advisors** | What advisors entered against converted opportunities. Observed, and often ahead of the till export. |
| **Estimated incremental revenue** | Converted opportunities, discounted by how likely that purchase was anyway. **Modelled, not measured.** |

Conversion rate is measured from advisor outcomes. Conversion *probabilities* on
opportunity cards are conservative retail priors, labelled as modelled, and will
be wrong in the specific until this boutique's own outcomes accumulate.

Without a holdout group, incremental revenue is an estimate — and the page says
so, every time.

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

Only applicable signals contribute, and their weights are renormalised to sum to
1. A boutique with no colour data gets the same scale with fewer inputs — and a
lower **data confidence**, reported separately from the match score. Missing
information is never a negative signal.

Three further guarantees:

- **Hard gates, not silent penalties.** Out of stock or a gender mismatch removes
  a product; unknown stock does *not* count as zero stock.
- **Category coherence.** Price, stock and timing can never carry an unrelated
  category to the top — weak category fit caps the whole match.
- **Customer-specific.** A match needs at least one customer-derived signal;
  inventory priority and newness cannot produce a "match" on their own.

Signal impacts sum exactly to the reported score, so Customer Detail can show
precisely why a piece was recommended — and which signals were missing.

Inventory intelligence still runs (ageing, sell-through, velocity, weeks of
cover, risk class) but is surfaced *inside* recommendations — "Only 2 left",
"has been sitting 180 days" — rather than as a page of its own.

---

## Architecture

```
revenueos/
├── backend/                 FastAPI + deterministic analytics + Claude
│   ├── app/
│   │   ├── data/            ingestion.py  mapping.py  cleaning.py  validation.py
│   │   │                    schema.py (canonical fields + multilingual aliases)
│   │   │                    values.py (parsing that returns None, never 0)
│   │   ├── analytics/       customer_scoring.py  segmentation.py  compliance.py
│   │   │                    opportunities.py  performance.py  matching.py
│   │   │                    inventory.py  forecasting.py  taxonomy.py
│   │   ├── ai/              client.py  prompts.py  context_builder.py  tools.py  analyst.py
│   │   ├── demo/            generator.py (correlated synthetic boutique)
│   │   ├── routers/         data, overview, customers, products, opportunities,
│   │   │                    performance  (+ analyst, campaigns, scenarios: API only)
│   │   ├── workspace.py     pipeline orchestration + caching + persistence + audit log
│   │   └── main.py
│   └── tests/               71 tests
└── frontend/                Next.js 14 (App Router) + TypeScript + Tailwind
    ├── app/                 overview, opportunities, actions, customers, performance, data
    ├── components/          Shell (nav + ⌘K palette), ui, charts (hand-rolled SVG)
    └── lib/                 api client, formatting
```

**Data flow.** Upload → parse → detect mapping → confirm → clean into typed
records → one pipeline run (profiles → value & lifecycle → eligibility → product
stats → quality → opportunities → performance) → cached in the workspace → every
endpoint reads the cache. Recomputation happens on import, not per request.

---

## Running it

### Deployed

RevenueOS deploys to Render from `render.yaml`; see [DEPLOYMENT.md](DEPLOYMENT.md)
for the setup, the environment variables and how to verify a release.

### Docker (one command)

```bash
cd revenueos
cp .env.example .env          # optional: add ANTHROPIC_API_KEY
docker compose up
```

Open <http://localhost:3000>.

### Local

```bash
cd revenueos && ./dev.sh     # starts both, and refuses to start on a busy port
```

Or by hand:

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

Open <http://localhost:3000> and choose **Explore demo boutique** — 160
customers, 300 products and 2,200 transactions with realistic correlated
behaviour, including messy per-channel consent and opt-outs.

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

## Getting your data in

**Send us your standard exports and we'll set RevenueOS up for you.** Three
files, and any subset works:

| File | What it is |
|---|---|
| **Customers** | Your CRM export: ID, name, contact details, consent. |
| **Transactions** | Your sales export, one row per line item or per order. |
| **Products & Inventory** | Your catalogue export: SKU, category, brand, price, stock. |

The importer handles: `,` `;` tab `|` delimiters · UTF-8/UTF-16/CP1252/latin-1 ·
BOMs · `1.234,56` and `1,234.56` · `dd/mm/yyyy` and `yyyy-mm-dd` · `(250)`
negatives · currency symbols · preamble rows above the header · headerless files
· ragged rows · duplicate headers.

Column mapping combines three signals — the header text against a multilingual
alias list, a profile of the actual values, and arbitration so each canonical
field is claimed by exactly one column. Values can veto a misleading header: a
column called `Date` containing email addresses will not be mapped as a date.
Anything below the confidence threshold is flagged for review, and every column
can be remapped by hand.

---

## How the AI is used

Deterministic Python computes every number. Claude explains them and never
produces one.

- **Model:** `claude-opus-5` with adaptive thinking, via the official `anthropic` SDK.
- **Tools:** read-only analytics functions. Claude can query and interpret; it
  cannot calculate.
- **Grounding:** the system prompt forbids stating any figure that did not come
  from a tool result, and forbids inventing customers or products.
- **Privacy:** email, phone, address and birth date are stripped before anything
  reaches the API (`ai/context_builder.minimise`). Claude sees internal IDs and
  computed metrics.
- **No key, no problem:** without `ANTHROPIC_API_KEY` every surface falls back to
  a deterministic, data-derived summary labelled `engine: "computed"`. Nothing
  ever pretends to be model reasoning.

---

## Design principles

1. **Never fake a number.** Unknown renders as "—" with a tooltip, never as `0` or `0%`.
2. **Every claim carries its basis.** A figure that cannot say where it came from does not ship.
3. **Observed and estimated are different words.** They are never blended into one metric.
4. **Consent gates outreach.** Unknown consent is not consent.
5. **Targeted selling before markdown.** No recommended action opens with a discount.
6. **A short list is an honest list.** Never pad to a quota.

---

## Known limitations

- **Single workspace.** State is one in-process workspace persisted to a JSON
  snapshot. There is no auth or multi-tenancy.
- **Conversion rates are priors, not learned.** They come from conservative
  retail defaults, not from this boutique's measured response, and will be wrong
  in the specific until outcome data accumulates.
- **No incrementality measurement.** Revenue attributed to an action is not proof
  the action caused it. A treatment/control holdout is the honest next step.
- **Cohort cycles need a population.** A boutique with fewer than ~4 customers
  per cohort falls back to the whole base, or to plain recency.
- **Recomputation is full, not incremental.** Fine to ~100k customers in-process;
  beyond that the pipeline should move to DuckDB/Postgres.

## Recommended next steps for production

1. **Persistence & multi-tenancy** — Postgres (or Supabase) per boutique, with
   auth and row-level isolation; DuckDB for the analytical queries.
2. **Outcome loop** — replace the prior conversion rates with rates measured from
   the Action Center, per trigger and per value tier.
3. **Holdout experiments** — a control group per week, so "incremental revenue"
   becomes measured rather than modelled.
4. **Background jobs** — move the pipeline to a worker with incremental
   recomputation on import instead of a synchronous rebuild.
5. **Native connectors** — Shopify, Lightspeed and common Italian POS systems, so
   the CSV path becomes the fallback rather than the default.
6. **Outreach integrations** — WhatsApp Business and email, with the existing
   consent, frequency-cap and audit-trail enforcement wired into the send path.
