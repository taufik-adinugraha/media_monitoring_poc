# Media Monitoring Repo (Metadata Lake + LLM Enrichment + Sonar Deep Analytics)

This repository implements a **metadata-first media monitoring pipeline**:

- **Ingest (periodic):**
  - GDELT Doc API (news discovery)
  - MediaStack (aggregated news API)
  - Publisher RSS feeds (ground-truth, source-cited)
  - YouTube channel RSS (social / broadcast signals)
- **Preprocess/enrich (periodic):**
  - Normalize fields to a common schema
  - De-duplicate by URL fingerprint
  - LLM enrichment using **Gemini** (cheap small model) to produce structured tags:
    - topics, actors, locations, language, is_editorial
- **Store:**
  - SQLite via SQLAlchemy (portable; swap DB by changing `DATABASE_URL`)
- **Deep analytics (on-demand):**
  - Select relevant URLs from the DB
  - Run **Sonar** (Perplexity) to generate a narrative report for a dashboard

## Why metadata-first?

- Cheap and scalable to ingest frequently
- Clear provenance: you always keep the original URLs
- Deep reading is expensive -> do it **only on demand** (Sonar)

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy env template:

```bash
cp .env.example .env
# then edit values (keys, DB url, etc.)
```

### 1) Run one cycle (ingest + store + enrich)

```bash
python scripts/run_once.py --config monitor_config.json
```

### 2) Run as a periodic worker

```bash
python scripts/run_worker.py --config monitor_config.json --interval-min 30
```

### 3) Generate deep analytics report (Sonar)

```bash
python scripts/generate_report.py --config monitor_config.json --since-days 7
```

Output:
- `reports/report_latest.md`
- `reports/report_<timestamp>.md`

---

## Configuration (`monitor_config.json`)

- `sources.*.enabled`: turn sources on/off
- `taxonomy.topics`: customizable topics (keywords + optional locations hints)
- `taxonomy.actors`: list of actors you care about
- `preprocess.gemini_model`: default Gemini model to use
- `report.sonar_model`: default Sonar model to use

**Note on MediaStack languages**
MediaStack supports a limited language list (e.g., en, fr, de, etc.). Indonesian (`id`) is typically not in the supported list.
In this repo, `languages` is optional and validated — if you set an unsupported language code, it will be dropped with a warning.

---

## Data model (DB)

Each record stores:
- `platform`: gdelt | mediastack | rss | youtube
- `source_type`: news | social
- `publisher_or_author`
- `url`, `title`, `summary`
- `published_at`, `ingested_at`
- `tags_json` (topics/actors/locations/language/is_editorial)
- `raw_json` (original payload)

SQLite is used by default, but you can point `DATABASE_URL` at Postgres later:
```bash
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname"
```

---

## Repo layout

```text
media_monitor_repo/
├─ media_monitor/
│  ├─ settings.py
│  ├─ config.py
│  ├─ utils.py
│  ├─ pipeline.py
│  ├─ db/
│  │  ├─ models.py
│  │  └─ store.py
│  ├─ sources/
│  │  ├─ gdelt.py
│  │  ├─ mediastack.py
│  │  ├─ rss.py
│  │  └─ youtube.py
│  ├─ preprocess/
│  │  ├─ schema.py
│  │  ├─ gemini_client.py
│  │  └─ enrich.py
│  └─ analytics/
│     ├─ sonar_client.py
│     └─ report.py
├─ scripts/
│  ├─ run_once.py
│  ├─ run_worker.py
│  ├─ generate_report.py
│  └─ list_mediastack_sources.py
├─ tests/fixtures/
│  ├─ gdelt_sample.json
│  ├─ mediastack_sample.json
│  ├─ rss_sample.json
│  └─ youtube_sample.json
├─ monitor_config.json
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## Offline smoke test

This repo includes fixtures so you can validate the pipeline without any API keys:

```bash
python scripts/run_once.py --config monitor_config.json --offline-fixtures
```

This will ingest from `tests/fixtures/*` instead of calling external APIs.

---

## Notes / operational tips

- **GDELT**: great for discovery, but often returns URL + metadata, not full content.
- **RSS**: best for provenance and stability; but can be flaky and should degrade gracefully.
- **YouTube**: channel RSS is stable; stats require YouTube Data API.
- **Gemini enrichment**: store only structured tags; avoid storing full copyrighted text.
- **Sonar deep report**: run it on-demand for a dashboard query; keep the prompt scoped to selected URLs.

---

## High-level pipeline

```
            ┌──────────────┐
            │  DATA SOURCES│
            │              │
            │  GDELT       │
            │  RSS         │
            │  MediaStack  │
            │  YouTube RSS │
            └──────┬───────┘
                   │
                   ▼
        ┌─────────────────────┐
        │ INGESTION (periodic)│
        │ - fetch metadata    │
        │ - keep provenance   │
        └──────┬──────────────┘
               │
               ▼
     ┌──────────────────────────┐
     │ NORMALIZATION + DEDUP    │
     │ - unified schema         │
     │ - hash-based dedup       │
     └──────┬───────────────────┘
            │
            ▼
 ┌────────────────────────────────┐
 │ METADATA LAKE (SQLite / DB)    │
 │ - URLs                         │
 │ - title / summary              │
 │ - publisher / platform         │
 │ - raw payload (JSON)           │
 │ - enrichment status            │
 └──────┬─────────────────────────┘
        │
        ▼
 ┌────────────────────────────────┐
 │ PREPROCESS / ENRICH (Gemini)   │
 │ - topics                       │
 │ - actors                       │
 │ - locations                    │
 │ - language                     │
 │ - editorial vs reporting       │
 └──────┬─────────────────────────┘
        │
        ▼
 ┌────────────────────────────────┐
 │ ENRICHED METADATA STORE        │
 │ (same DB, enriched fields)     │
 └──────┬─────────────────────────┘
        │
        ▼
 ┌────────────────────────────────┐
 │ ANALYTICS QUERY (on demand)    │
 │ - select topics / time range   │
 │ - pick relevant URLs           │
 └──────┬─────────────────────────┘
        │
        ▼
 ┌────────────────────────────────┐
 │ DEEP DIVE (Sonar)              │
 │ - reads full articles          │
 │ - compares framing             │
 │ - synthesizes narrative        │
 └──────┬─────────────────────────┘
        │
        ▼
 ┌────────────────────────────────┐
 │ REPORT / DASHBOARD             │
 │ - trends                       │
 │ - bias signals                 │
 │ - citations                    │
 └────────────────────────────────┘
```

---

## Pipeline components

### A. Ingestion layer

**Location:** `media_monitor/sources/`

```
├─ gdelt.py        → discovery (URLs + metadata)
├─ rss.py          → canonical publisher feeds
├─ mediastack.py   → optional aggregator
└─ youtube.py      → channel RSS (+ optional stats)
```

**Triggered by:**

```bash
python scripts/run_once.py
# or
python scripts/run_worker.py
```

**Orchestrated in:**

`media_monitor/pipeline.py` → `ingest_once()`

### B. Normalization + dedup

**What happens:**

- Convert all sources → one schema
- Generate:
  - `id = sha256(platform|url)`
  - `content_hash = sha256(title+summary)`
- Prevent duplicates across sources (e.g. RSS + GDELT pointing to same URL)

**Code:**

```python
pipeline.normalize_gdelt()
pipeline.normalize_rss()
pipeline.normalize_mediastack()
pipeline.normalize_youtube()
```

**Stored via:**

```python
Store.upsert_items()
```

### C. Metadata lake (DB)

**Schema (simplified):**

```
media_items
├─ id (hash)
├─ platform (gdelt|rss|youtube|...)
├─ source_type (news|social)
├─ publisher_or_author
├─ url
├─ title
├─ summary
├─ published_at
├─ ingested_at
├─ topics / actors / locations
├─ language / is_editorial
├─ raw_json
└─ enrichment status
```

**Implementation:**

```
media_monitor/db/
├─ models.py
└─ store.py
```

**Why SQLite first:**

- Zero infra
- Deterministic
- Swappable later (`DATABASE_URL=postgresql://...`)

### D. Preprocessing / enrichment (Gemini)

**Location:** `media_monitor/preprocess/`

```
├─ gemini_client.py   → Gemini REST calls
├─ enrich.py          → batch enrichment logic
└─ schema.py          → strict JSON output
```

**Input:**

- `title`
- `summary`
- `publisher`
- `platform`
- `allowed taxonomy`

**Output:**

```json
{
  "topics": [...],
  "actors": [...],
  "locations": [...],
  "language": "id",
  "is_editorial": false
}
```

**Design choice:**

- Small Gemini model
- JSON-only output
- Retry + fallback keyword tagging if API unavailable

### E. Analytics query layer

```python
store.query_items(
  since_iso="2026-01-01",
  topics_any=["national_politics"]
)
```

This is what your dashboard backend will call.

### F. Deep analytics (Sonar)

**Location:** `media_monitor/analytics/`

```
├─ sonar_client.py
└─ report.py
```

**Triggered by:**

```bash
python scripts/generate_report.py
```

**Flow:**

1. Select URLs from DB
2. Group by topic
3. Ask Sonar:
   - summarize developments
   - compare framing
   - cite sources
4. Render Markdown report