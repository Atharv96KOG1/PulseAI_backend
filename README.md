# Loom — Source of Truth: Technical Design & Architecture

> Loom (formerly PulseAI) is the single source of truth for design, schema, and implementation decisions. Where code and this document disagree, this document wins unless a decision is explicitly revised here.

---

## Executive Summary

Loom is an AI-powered customer feedback analysis platform. It converts raw, free-text customer feedback into structured, consistent, business-ready insight: per-ticket classification, sentiment and urgency scoring, theme classification, aggregate analytics, a grounded narrative summary, and an interactive dashboard.

The architecture deliberately separates deterministic software from AI reasoning. Python performs validation, cleaning, aggregation, and all numeric computation. The LLM is used only where genuine language understanding is required: classifying each ticket, and narrating pre-computed numbers into a readable summary. This keeps the system consistent, cost-efficient, testable, and extensible.

---

## Core Principles

These are governing constraints. Every implementation decision must be consistent with them.

1. **The LLM classifies and phrases; Python computes everything numeric.** The model never counts, sums, or calculates percentages. All arithmetic is deterministic Python over validated data.
2. **Structured output only.** Every LLM response conforms to a fixed schema and is validated before use. No free-text parsing.
3. **Closed vocabularies.** Categories, themes, sentiment, and urgency are fixed enumerations. The model selects from known values; it never invents labels.
4. **Determinism by construction.** Temperature 0, discrete outputs, and closed lists make the same input produce the same output — without relying on a cache.
5. **Validate before AI.** Deterministic checks reject or repair bad input before any token reaches the model.
6. **Never crash the batch.** Every enrichment is validated, repaired once, and falls back to a valid schema shape on failure. One bad ticket must not fail the run.
7. **The dashboard never calls the LLM.** AI runs once during processing and writes structured results. The dashboard reads processed data only.
8. **Simplicity over speculative production complexity.** Build what the scope needs; document deferred capability as a clean extension path.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React + TypeScript | Modular, type-safe UI |
| UI system | Tailwind CSS + shadcn/ui | Consistent design primitives |
| Charts | Recharts | Declarative dashboard visualizations |
| Backend | FastAPI | Async APIs, automatic OpenAPI |
| Validation | Pydantic | Type-safe schema enforcement and repair |
| Data handling | Pandas | CSV parsing and tabular processing |
| AI | LLM API | Semantic classification and narration only |

---

## High-Level Architecture

```text
                         +----------------------+
                         |   React Dashboard    |
                         +----------+-----------+
                                    |
                               REST API
                                    |
                    +---------------v---------------+
                    |        FastAPI Backend        |
                    +---------------+---------------+
                                    |
     +------------------+-----------+-----------+------------------+
     |                  |                       |                  |
     v                  v                       v                  v
+-----------+   +----------------+     +----------------+   +-------------+
| Validation|-->| Preprocessing  |---->|  AI Pipeline   |-->| Analytics   |
| Layer     |   | (clean + PII)  |     | (batch LLM)    |   | Engine      |
+-----------+   +----------------+     +-------+--------+   +------+------+
                                               |                   |
                                               +---------+---------+
                                                         |
                                                  Structured JSON
                                                         |
                                              Executive Summary (LLM)
                                                         |
                                                 Dashboard Response
```

---

## End-to-End Flow

```text
CSV Upload
   │
   ▼
Validation            reject invalid file; skip empty/null rows (counted)
   │
   ▼
Normalization         strip HTML/markdown, unicode + whitespace cleanup
   │
   ▼
PII Redaction         regex redaction before any text reaches the model
   │
   ▼
Long-Ticket Routing   > 300 words → summarization prompt → classification
   │                  otherwise   → classification directly
   ▼
Batch Builder         group items; respect concurrency cap
   │
   ▼
LLM Classification    temp 0, one call per ticket, structured JSON
   │                  validate → repair once → fallback shape on failure
   ▼
Python Analytics      counts, distributions, theme frequency, KPIs
   │
   ▼
Executive Summary     Python builds number-facts → one LLM call narrates
   │
   ▼
API Response          structured items + analytics + summary + report
   │
   ▼
Dashboard             KPI cards, charts, feedback explorer (reads only)
```

The shape to keep in mind: **AI at the two ends, deterministic Python in the middle, every countable value closed-list or computed.**

---

## Processing Pipeline

**Pipeline invariant:** every ticket that enters classification must leave with a valid schema object, even if AI processing fails. There is no code path that emits a partial, null, or malformed classification — failure produces the fallback shape (below), never an exception that halts the run.

**Skipped-row invariant:** rows rejected during validation are reported separately and are **never** included in KPI calculations, distributions, or any dashboard metric. Skipped rows count toward the upload total and the processing-success rate only.

### Stage 1 — Validation

Reject invalid uploads before any AI processing. Skip bad rows without failing the run.

**File-level errors (reject upload):**
- Missing `feedback` column
- Empty file / zero data rows

**Row-level (skip row, increment skipped count):**
- Empty feedback
- Null / NaN feedback

**Warnings (process, but flag):**
- HTML detected
- Markdown detected
- Very long feedback (> 300 words → routed to long-ticket handling)
- Duplicate feedback (processed independently; flagged only)

### Stage 2 — Normalization

Deterministic Python cleanup:
- HTML stripping and entity decoding
- Markdown cleanup
- Unicode normalization
- Whitespace normalization
- Optional URL removal

### Stage 3 — PII Redaction

Regex-based redaction applied **before any text reaches the model**. This is a required stage, enabled by default: no raw customer-identifying data is sent to the LLM. It is a genuine production and data-minimization requirement, not cosmetic cleanup.

Redact: email addresses, phone numbers, card-like numeric sequences, and common ID patterns. Replace with typed placeholders (e.g. `[EMAIL]`, `[PHONE]`, `[CARD]`) so the model retains context that *a* value was present without seeing it.

### Stage 4 — Long-Ticket Routing

If a ticket exceeds **300 words**, it is first passed through a **summarization prompt**, and the summary is then classified. Otherwise it is classified directly.

```text
Long ticket ( >300 words )  → Summarization Prompt → Classification Prompt
Normal ticket               → Classification Prompt
```

Only long tickets incur the extra call. Rationale: reduce context, keep the classification prompt focused, improve handling of long narratives.

**Mandatory guardrail for the summarization prompt:** the summarizer must be instructed to **preserve every distinct issue and its key specifics**, not to produce a single-topic abstract. Summarization is the one place a secondary issue can silently disappear, which would defeat multi-issue detection (below). The summarization prompt explicitly states: *"Retain all distinct problems, requests, and complaints mentioned; do not merge or drop any issue."*

### Stage 5 — Batch Building & Classification

Tickets are grouped into batches for throughput management and classified with **one LLM call per ticket** at **temperature 0**. Batching improves execution efficiency only; each ticket is still classified independently. Each response passes through the bounded validate → coerce → single re-prompt → fallback sequence defined under *LLM Contract → Validation & Repair*. A configurable **concurrency cap** limits parallel in-flight calls to stay within provider rate limits.

**Batch independence:** the failure, timeout, or malformed response of one ticket must not prevent classification of any other ticket in the same batch. Each ticket succeeds or falls back on its own; there is no shared failure path across a batch.

### Stage 6 — Analytics

Pure Python. No LLM. Computes counts, distributions, theme frequency, urgency distribution, actionable counts, and KPIs.

### Stage 7 — Executive Summary

Python assembles the aggregate facts (distributions, top themes, top categories, notable counts). A **single LLM call** turns those numbers into a coherent, prioritized narrative. The model narrates pre-computed figures; it does not compute them.

**Summary grounding contract.** The summary generator:
- must **not invent statistics** — every number in the narrative must come from the Python-computed aggregate it was given;
- must **not contradict** the computed metrics;
- must **only reference Python-computed values**, never figures it derives or estimates itself.

This is what makes the summary trustworthy: the numbers are guaranteed correct because the model never produced them, only phrased them.

---

## Classification Taxonomy

The taxonomy and theme lists defined in this section are the **canonical enumerations** for the entire system. Prompt templates, Pydantic schemas, analytics, and frontend types must all derive from these values. No component may define its own category or theme strings independently — this is what prevents schema drift across the backend, model, and UI.

Eight fixed top-level categories. `Other` is the escape hatch — the model routes here rather than forcing a poor fit.

| Category | Scope |
|----------|-------|
| Billing & Payments | Charges, refunds, failed/duplicate payments, invoices, subscription/pricing |
| Account & Access | Login, passwords, OTP/2FA, lockouts, profile/permission settings |
| Performance & Reliability | Crashes, slowness, freezes, downtime, timeouts (app fails to run properly) |
| Functional Issues | App runs but behaves wrong — broken feature, incorrect data, sync/validation errors |
| Feature Requests & Enhancements | Requests for new capability or improvements to existing capability |
| Usability & User Experience | Works, but confusing, awkward, hard to navigate; also positive UX feedback |
| Support Experience | Feedback about the support process itself — response time, agent quality, resolution |
| Other | Uncategorized, unclear, or general feedback |

**Category design note (Performance vs Functional Issues):** Performance = the app fails to *run properly* (slow, crashing, down). Functional Issues = the app runs but does the *wrong thing* (a feature misbehaves, data is incorrect). This mirrors real triage boundaries and is the pair most prone to confusion; keep the definitions sharp in the prompt.

### Category-Owned Themes

Themes are **not global** — each category owns its own fixed theme list. The classification prompt must guarantee the selected theme belongs to the selected category (structurally enforced two-tier selection: pick category, then pick theme from that category's list only).

**Billing & Payments:** Failed Payment · Duplicate Charge · Refund Delay · Unexpected Charge · Subscription/Renewal Issue

**Account & Access:** Login Failure · Password Reset · OTP/2FA Problem · Account Locked · Profile Settings Issue

**Performance & Reliability:** App Crash · Slow Performance · Downtime/Outage · Timeout Error · High Resource Usage

**Functional Issues:** Function Not Working · Incorrect Data Displayed · UI Element Broken · Sync Issue · Validation Error

**Feature Requests & Enhancements:** New Feature Request · Enhancement Request · Integration Request · Workflow Improvement

**Usability & User Experience:** Confusing Navigation · Poor Layout · Hard to Find Feature · Accessibility Issue · Positive Experience

**Support Experience:** Slow Response · Unhelpful Agent · Issue Unresolved · Difficult to Reach Support

**Other:** General Feedback · Unclear

> Themes are a starting set and should be trimmed to match the dataset. A theme that no ticket ever maps to is dead weight and should be removed. `Positive Experience` and `General Feedback` exist so that praise and non-complaint feedback have a valid home rather than being mis-filed.

---

## Sentiment, Urgency & Actionable

All three are discrete, closed enumerations — chosen for consistency (they survive the identical-input test) and actionability (no one acts on a decimal).

**Sentiment:** `Positive` · `Neutral` · `Negative`
- No `Mixed` value. A ticket with both praise and complaint is classified by its **dominant overall sentiment**.
- **Revision (2026-07-22):** a numeric `sentiment_score` (-1.0 to 1.0) now accompanies the label, by
  explicit product decision — superseding the "no continuous score" rule this section originally
  specified. It is validated to stay sign-consistent with `sentiment` (`Positive` > 0.1, `Negative` <
  -0.1, `Neutral` in [-0.1, 0.1]) so the two fields can never contradict each other. The tradeoff the
  original rule was guarding against (a model-produced number wobbling between runs) still applies to
  the *per-ticket* score; what stays fully deterministic is any aggregate built from it (e.g. an average
  sentiment score), which is computed in Python like every other statistic — never by the model.

**Urgency:** `High` · `Medium` · `Low` — defined by impact, independent of tone:
- `High` — blocks core functionality: severe outage, payment failure, or a security/access issue.
- `Medium` — an important issue that has a workaround or limited impact.
- `Low` — minor inconvenience, cosmetic issue, suggestion, or praise.

Urgency is impact-based, not tone-based: a calmly worded "I can't log in and have tried everything" is `High`; an angrily worded complaint about button color is `Low`. This keeps priority honest and consistent regardless of how the customer phrased it.

**Actionable:** `true` · `false` — whether the ticket requires follow-up or intervention by a product, engineering, support, or business team. Praise or purely informational feedback with no required action is `false`. This makes the field an objective "does someone need to do something" test rather than a subjective judgment.

---

## Multi-Issue Handling

A ticket may contain more than one issue. This is handled in the **single classification call** — never an additional LLM call. The model identifies all issues, selects one primary, and returns the rest as `additional_issues`.

- **Primary** carries full enrichment: category, theme, sentiment, urgency, actionable.
- **Additional issues** carry category, theme, and **urgency**. (Urgency is included so a mild primary issue paired with an urgent secondary issue is not lost. Sentiment is intentionally omitted from secondary issues — dominant sentiment is a per-ticket property.)
- **Analytics use the primary issue** for headline distributions. Additional issues are preserved for detailed inspection and urgency-aware views but are intentionally excluded from headline metrics to avoid double-counting tickets.

**Data model note:** the output is structured to allow multiple issues from day one. First release aggregates on the primary; promoting additional issues into headline analytics later is a scope expansion, not a schema rewrite. When that expansion happens, the denominator shifts from *tickets* to *issues* and the dashboard must state which it is counting.

---

## LLM Contract

### Input
- Cleaned, PII-redacted feedback (a summary, for long tickets).
- Instructions to select category, then a theme from that category, determine sentiment and urgency, identify additional issues, mark actionable, and return valid JSON only.

### Classification Prompt Requirements

The classification prompt must:
- Select exactly one primary category.
- Select exactly one theme from that category.
- Determine dominant overall sentiment.
- Determine urgency.
- Determine actionable status.
- Preserve additional issues.
- Never invent categories or themes.
- Return valid JSON only.

### Summarization Prompt Requirements

The summarization prompt must:
- Preserve every distinct issue, request, and complaint.
- Preserve important entities and chronology when relevant.
- Remove repetition, greetings, and filler.
- Never merge or omit separate issues.

### Prompt ownership
Prompt templates are implementation artifacts. This document defines their **required behavior** — the constraints above — not their exact wording. Prompt text may be refined or rewritten freely as long as it satisfies these requirements and produces the defined schema. Improving a prompt is not an architectural change.

### Output requirements
- Strict JSON, one object per ticket.
- No markdown, no prose outside the JSON.
- Category and theme drawn only from the fixed taxonomy; theme must belong to the chosen category.
- Schema-validated before analytics; repaired once; replaced with a valid fallback on failure.

### Output Schema

```json
{
  "ticket_id": "string",
  "primary_category": "Account & Access",
  "primary_theme": "Login Failure",
  "sentiment": "Negative",
  "sentiment_score": -0.7,
  "urgency": "High",
  "actionable": true,
  "additional_issues": [
    {
      "category": "Performance & Reliability",
      "theme": "App Crash",
      "urgency": "Medium"
    }
  ]
}
```

**Output is a pure enumeration block by design.** No free-text field is included. A prose rationale drives nothing in the first release (it does not condition classification and is not aggregated), costs output tokens on every call, and is the one field a model can waffle in — occasionally destabilizing the structured fields around it. Keeping the output pure-enum maximizes consistency, which is the primary correctness goal. If evaluation later shows accuracy is weak specifically on ambiguous multi-issue tickets, the targeted fix is a reasoning-first field (rationale produced *before* the labels so it conditions them) — added only if the confusion data justifies it, and constrained to a short quoted trigger phrase rather than open prose.

### Validation & Repair

Every LLM response passes through a fixed, bounded recovery sequence. The contract is **repair at most once, never loop, always end in a valid object** — one bad ticket never crashes the batch.

1. **Validate.** Parse the response and validate it against the Pydantic schema. Enums are closed sets, so an invented category/theme or a wrong-cased value (`negative` instead of `Negative`) fails validation rather than silently poisoning the data. If it passes, done.

2. **Coerce (free, deterministic).** On failure, first attempt a cheap Python fix with no model call: strip markdown code fences (```` ```json ````), trim whitespace, extract the outermost JSON object, and re-parse. Formatting noise — the most common cause of a malformed response — is fixed here for zero cost and zero latency. Re-validate. If it now passes, done.

3. **Re-prompt (one LLM retry).** If coercion still fails, retry the model **exactly once** with the validation error appended as a nudge (e.g. *"Your previous output failed validation: {error}. Return ONLY valid JSON matching the schema."*). Validate the result.

4. **Fallback.** If the retry still fails, emit the fallback shape (below). Never a third attempt, never an exception to the caller.

**Why coercion before re-prompt.** At batch scale a re-prompt is a whole extra LLM call; a stray code fence does not warrant one. The free Python pass resolves the common case, so the paid retry is reserved for genuinely malformed output. This preserves the exact "repair once → fallback" reliability contract while cutting repair cost on large batches.

**Transient API errors** (429 / 5xx / timeout) are handled separately from validation: retry with a short backoff. Auth errors are **not** retried. Every unrecovered error path — validation or API — ends in the fallback shape, never a crash. This is distinct from the one validation re-prompt above and does not count against it.

### Fallback Shape

On unrecoverable failure for a ticket, emit a valid object that never breaks analytics:

```json
{
  "ticket_id": "string",
  "primary_category": "Other",
  "primary_theme": "Unclear",
  "sentiment": "Neutral",
  "sentiment_score": 0.0,
  "urgency": "Low",
  "actionable": false,
  "additional_issues": []
}
```

The same graceful path handles out-of-scope inputs (non-English, spam/junk): they route to `Other / Unclear` rather than raising an exception. Not handling a case well is acceptable in scope; crashing on it is not.

---

## Analytics Specification

Computed in Python over validated results:

- Total feedback processed
- Total skipped rows (with reasons)
- Category distribution (by primary category)
- Sentiment distribution
- Average sentiment score (mean of per-ticket `sentiment_score`, computed in Python)
- Theme frequency (by primary theme)
- Urgency distribution (primary; optional urgency roll-up including `additional_issues`)
- Actionable feedback count
- Top recurring themes
- Top categories

---

## Dashboard KPI Definitions

| KPI | Definition |
|-----|-----------|
| Total Feedback | Count of valid processed rows |
| Skipped Rows | Invalid rows rejected during validation |
| Positive % | Positive / Total × 100 |
| Negative % | Negative / Total × 100 |
| Avg. Sentiment Score | Mean of per-ticket `sentiment_score`, computed in Python |
| Top Category | Highest-frequency primary category |
| Top Theme | Highest-frequency primary theme |
| High Urgency | Count of High-urgency tickets |
| Actionable | Count of tickets marked actionable |
| Processing Success Rate | Processed rows / Total uploaded rows × 100 |

**Denominator rule:** all dashboard percentages use **processed (valid) tickets** as the denominator, unless the metric explicitly states otherwise. Processing Success Rate is the one deliberate exception — it divides by *total uploaded* rows, because its whole purpose is to measure how many uploads survived validation. Skipped rows never enter any other percentage.

---

## Dashboard Specification

| Widget | Source |
|--------|--------|
| KPI Cards | Analytics engine |
| Category Distribution (chart) | Category counts |
| Sentiment Distribution (chart) | Sentiment aggregation |
| Theme Frequency (chart) | Theme aggregation |
| Urgency Breakdown (chart) | Urgency aggregation |
| Executive Summary (text) | Summary generator |
| Feedback Explorer (table) | Structured feedback objects with search, sorting, and filtering |

Every chart must be self-explanatory: titled, axis-labeled, and interpretable by a stakeholder without a walkthrough. The dashboard consumes processed API data only and issues no LLM calls.

---

## API Endpoints

The system is **stateless** with no database, so the entire pipeline runs in a **single request**. The CSV is uploaded and fully processed in one call that returns everything the dashboard needs. The frontend holds the response in memory and renders from it; the dashboard issues no further calls.

| Endpoint | Purpose |
|----------|---------|
| `POST /analyze` | Upload a CSV and run the full pipeline; returns the complete result payload |

### `POST /analyze`

**Request:** multipart CSV file.

**Response:**
```json
{
  "validation_report": { "total_rows": 100, "processed": 97, "skipped": 3, "skip_reasons": {} },
  "items": [ /* structured feedback objects, one per processed ticket */ ],
  "analytics": { /* category, sentiment, theme, urgency distributions and KPIs */ },
  "summary": "Executive summary narrative..."
}
```

**Why a single call, not upload → analyze → dashboard.** With no database, a two-step flow would require holding uploaded data in server-side memory between requests, keyed by an `upload_id`. That temporary state is fragile (lost on restart, absent on a second worker) and is session management the MVP does not need. A single stateless call matches the no-DB design honestly. The multi-request shape (`POST /upload` → `upload_id` → `POST /analyze` → `GET /dashboard`, `GET /summary`) becomes the natural design **once persistence is added** — it is listed with that deferred extension, not built now.

---

## Input Dataset Schema

| Column | Required | Description |
|--------|----------|-------------|
| feedback | Yes | Customer feedback text |
| id | No | Caller-supplied identifier, if the source system has one |
| source | No | Survey, App Store, Support, etc. |
| date | No | Feedback timestamp |

**Only `feedback` is required.** The uploaded CSV is expected to contain feedback text and nothing more; all other columns are optional. Extra columns are ignored unless used by analytics.

**Identifier handling.** The system assigns each processed ticket a `ticket_id` internally: it uses the caller-supplied `id` when present, otherwise it generates a stable one (row index or UUID). Callers never have to provide an identifier. The output `ticket_id` therefore always exists even though the input `id` column is optional — this is the mapping between the optional input `id` and the guaranteed output `ticket_id`.

---

## Logical Data Model

```text
Feedback
├── ticket_id
├── original_text
├── cleaned_text
├── was_truncated_or_summarized   (bool)
├── primary_category
├── primary_theme
├── sentiment
├── sentiment_score        (float, -1.0 to 1.0; sign-consistent with sentiment)
├── urgency
├── actionable
└── additional_issues[]           (category, theme, urgency)
```

---

## Configuration

Runtime parameters via environment variables. No secrets in code.

| Variable | Purpose | Default |
|----------|---------|---------|
| LLM_MODEL | Model used for classification inference | — (required) |
| API_KEY | LLM provider key (env / secrets manager only) | — (required) |
| BATCH_SIZE | Tickets per batch | 10 |
| MAX_CONCURRENCY | Cap on parallel in-flight LLM calls | 5 |
| LONG_TICKET_WORD_LIMIT | Word count triggering summarization | 300 |
| MAX_UPLOAD_SIZE | Maximum CSV upload size | implementation-defined |
| REQUEST_TIMEOUT | Per-call timeout | implementation-defined |
| SUMMARY_MODEL | Optional model for executive summary generation | falls back to LLM_MODEL |
| LOG_LEVEL | Logging verbosity | INFO |

---

## Error Handling & Reliability

- Skip invalid rows; report processed/skipped counts with reasons.
- Validate every LLM response against the schema; recover via the bounded validate → coerce → single re-prompt → fallback sequence (see *Validation & Repair*); never crash.
- Cap concurrency to respect provider rate limits.
- Log latency and failures per batch.
- **Idempotency:** re-running the same upload must not double-count. Key processing by upload/run identity so re-runs are safe.
- No hardcoded secrets; keys in environment or a secrets manager.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 4001 | Missing feedback column |
| 4002 | Empty CSV |
| 4003 | No valid feedback found |
| 4004 | Invalid LLM response (post-repair) |
| 5001 | AI provider unavailable |

---

## Evaluation Strategy

Accuracy must be measured, not asserted.

- **Golden set:** the demo dataset is hand-labeled (category, theme, sentiment) as it is built, so it doubles as a trusted answer key.
- **Hold-out discipline:** the tickets used as few-shot examples in the prompt are **excluded** from the tickets used to measure accuracy. Measuring against examples the model was shown inflates the result.
- **Metric:** run the held-out set through the pipeline and report accuracy (correct / total), overall accuracy, per-category accuracy, and per-theme accuracy.
- **Confusion matrix:** deferred. Add it if a single accuracy number proves insufficient for locating error clusters (e.g. Performance vs Functional Issues confusion). It is an inexpensive follow-up, not a first-release requirement.
- **Data honesty:** if tickets are LLM-generated, hand-write or heavily edit a portion so the evaluation is not merely the model recognizing its own style.

---

## Dataset Specification

Approximately **100 tickets**, deliberately varied so the pipeline's behavior is demonstrable. Include:

- Normal single-issue tickets
- Multi-issue tickets
- Long tickets (> 300 words) to exercise summarization routing
- Duplicate tickets (for later optimization discussion)
- HTML / Markdown-formatted feedback (to exercise normalization)
- Invalid / empty rows (to exercise validation)
- A realistic mix of Positive, Neutral, and Negative — including genuine praise, not only complaints
- Coverage across all categories so none is permanently empty

The dataset is both the demo input and the evaluation bench. Each edge case the system claims to handle should have representative rows.

---

## Scope & Extensions

### In scope (first release)
- CSV upload → validation → normalization → PII redaction → classification → analytics → summary → dashboard
- Fixed taxonomy, category-owned themes, discrete sentiment/urgency
- Single-call multi-issue with `primary` + `additional_issues` (urgency-bearing)
- Long-ticket summarization routing with issue-preserving summaries
- Golden-set accuracy evaluation
- Single-period (current batch) analysis

### Deferred — documented, not built
Each is a clean extension that does not require reworking the AI pipeline.

| Deferred capability | Why deferred / trigger to build |
|---------------------|--------------------------------|
| Duplicate-result caching | Consistency already achieved via temp 0 + discrete + closed lists. Arrives naturally with persistence (storage acts as cache). Build if repeated re-processing becomes costly. |
| Multi-period trends & persistence | Requires storage (SQLite is sufficient). The fixed taxonomy is already a stable-id vocabulary, so week-over-week deltas and new-theme detection drop in without touching the pipeline. The multi-request API shape (`POST /upload` → `upload_id` → `POST /analyze` → `GET /dashboard`/`GET /summary`) is adopted here, replacing the stateless single call, since results now persist and can be re-queried. |
| Non-English support | Currently routed to `Other` gracefully. Build language detection + translation step when the dataset warrants it. |
| Spam / junk filtering | Currently routed to `Other` gracefully. Add a pre-classification gate to protect analytics when real streams introduce noise. |
| Emergent-theme detection | Fixed themes are blind to new issues, which pool in `Other`. Monitor the `Other` rate as the signal; the automated version is embedding-based clustering. |
| Chunking for extremely large tickets | Beyond the summarization threshold; build if inputs regularly exceed summarization limits. |
| Aspect-based sentiment | Correct answer for mixed-sentiment tickets (sentiment per issue). Scoped out; dominant sentiment used instead. |
| Human review workflow | For low-confidence classifications; build when a confidence signal is added. |

---

## Project Structure

```text
backend/
├── api/                 HTTP endpoints and orchestration
├── pipeline/
│   ├── validate.py
│   ├── preprocess.py    normalization + PII redaction
│   ├── classify.py      batch classification, validation, repair, fallback
│   ├── summarize.py     long-ticket + executive summary prompts
├── analytics/           deterministic KPI/aggregation
├── prompts/             prompt templates and output contracts
├── schemas/             Pydantic models
├── services/            LLM client, file handling
├── utils/               shared helpers
└── main.py

frontend/
├── components/
├── pages/
├── hooks/
├── api/
├── types/
├── utils/
└── assets/
```

| Module | Responsibility |
|--------|----------------|
| api | Endpoints and request orchestration |
| pipeline | Validation, preprocessing, PII redaction, batching, LLM execution |
| analytics | Deterministic aggregation and KPIs |
| prompts | Prompt templates and output contracts |
| schemas | Pydantic models and validation |
| services | External integrations (LLM, files) |
| utils | Shared helpers |

---

## Implementation Phases

1. Scaffold — FastAPI, React, folder structure, config.
2. Ingestion — CSV upload, validation, normalization, PII redaction.
3. Classification — prompt, schema, batching, validation/repair/fallback, long-ticket routing.
4. Analytics — deterministic aggregation and dashboard APIs.
5. Summary — number-facts assembly + narration call.
6. Frontend — dashboard, charts, feedback explorer, filters.
7. Evaluation & polish — golden-set accuracy, edge-case verification, error handling.

---

## Development Checklist

- [ ] Project scaffold and configuration
- [ ] CSV upload endpoint
- [ ] Validation layer (file + row)
- [ ] Normalization + PII redaction
- [ ] Long-ticket routing (issue-preserving summarization)
- [ ] Batch builder with concurrency cap
- [ ] Classification prompt (two-tier category→theme, multi-issue)
- [ ] Output schema, validation, single repair, fallback shape
- [ ] Analytics engine
- [ ] Executive summary generation
- [ ] Dashboard APIs
- [ ] Frontend charts and feedback explorer
- [ ] Idempotent re-run handling
- [ ] Golden-set accuracy evaluation
- [ ] Edge-case verification against dataset

---

## Example

**Input tickets:**

| id | feedback |
|----|----------|
| 1 | Payment failed after checkout. |
| 2 | The app crashes every time I open Settings. |
| 3 | I love the new dashboard design! |

**Example classification output:**

```json
{
  "ticket_id": "2",
  "primary_category": "Performance & Reliability",
  "primary_theme": "App Crash",
  "sentiment": "Negative",
  "sentiment_score": -0.8,
  "urgency": "High",
  "actionable": true,
  "additional_issues": []
}
```

**Example dashboard snapshot:**

```text
Total Feedback : 100
Processed      : 97
Skipped        : 3

Top Category   : Billing & Payments
Top Theme      : Failed Payment
Positive       : 28%
Neutral        : 17%
Negative       : 55%
High Urgency   : 14
```

**Example executive summary (narrated from pre-computed numbers):**

> Most feedback concerns payment reliability and application stability. Billing & Payments is the largest category and the dominant source of negative sentiment, driven primarily by failed payments — checkout reliability is the clearest priority. Performance & Reliability is the second most frequent category, concentrated in app crashes. Feedback on the redesigned dashboard is predominantly positive.
