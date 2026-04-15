# Design Spec: Sprint 1 & Sprint 2 + Full Bonus — Lab Day 10

**Date:** 2026-04-15  
**Scope:** `etl_pipeline.py`, `transform/cleaning_rules.py`, `quality/expectations.py`, `requirements.txt`  
**Goal:** Complete Sprint 1 (ingest + schema + ingest-boundary timestamp) and Sprint 2 (3 new cleaning rules + Pydantic validation + 2 new expectations + publish-boundary timestamp) for full +3 bonus.

---

## Baseline State

- `etl_pipeline.py`: Working pipeline. Logs `run_id`, `raw_records`, `cleaned_records`, `quarantine_records`. Missing: ingest/publish boundary timestamps.
- `transform/cleaning_rules.py`: 6 baseline rules. Missing: ≥3 new rules.
- `quality/expectations.py`: 6 expectations using custom `@dataclass`, no Pydantic. Missing: ≥2 new expectations + real validation library.
- Current sample output: 10 raw → 6 cleaned, 4 quarantine.

---

## Architecture

Three files modified, one file updated (requirements). No new files created. Changes are additive; existing entrypoints and function signatures preserved.

```
etl_pipeline.py
  cmd_run()
    load_raw_csv()           ← ingest_boundary_ts logged here (SPRINT 1 BONUS)
    clean_rows()
    run_expectations()
    cmd_embed_internal()
      col.upsert()           ← publish_boundary_ts logged here (SPRINT 2 BONUS)
  manifest.json              ← both timestamps added as fields
```

---

## Sprint 1: `etl_pipeline.py` changes

### Ingest boundary timestamp (Bonus +1)

**Where:** In `cmd_run()`, immediately after `rows = load_raw_csv(raw_path)` succeeds (line 64).

**What:**
```python
ingest_ts = datetime.now(timezone.utc).isoformat()
log(f"ingest_boundary_ts={ingest_ts}")
```

**Manifest field:** `"ingest_boundary_ts": ingest_ts` added to the manifest dict.

---

## Sprint 2: `transform/cleaning_rules.py` — 3 New Rules

Rules are applied in sequence, inside the `clean_rows()` loop, before the existing `clean_rows` logic inserts into `cleaned`. Each has a clear docstring and `# RULE N:` comment.

### Rule 7 — BOM Strip

```
Location: First check inside the loop, before the allowlist check.
Logic: Strip \ufeff (UTF-8 BOM) from doc_id and chunk_text.
       If stripped doc_id is in allowlist → proceed normally.
       If stripped doc_id is still unknown → quarantine with reason "bom_invalid_doc_id".
Metric impact (inject scenario): Add row with "\ufeffpolicy_refund_v4" as doc_id.
  - Without R7: quarantined as unknown_doc_id.
  - With R7: BOM stripped, recognized as valid, passes to cleaned.
  → quarantine_records decreases by 1 vs no-rule baseline.
```

### Rule 8 — Exported-at Validation

```
Location: After effective_date normalization block.
Logic: If exported_at is empty string → quarantine reason "missing_exported_at".
       If exported_at is non-empty but cannot be parsed as ISO datetime
       (regex: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) → quarantine reason "invalid_exported_at_format".
Metric impact (inject scenario): Add row with exported_at="" but valid chunk_text.
  - Without R8: row passes to cleaned.
  - With R8: row is quarantined.
  → quarantine_records increases by 1 vs no-rule baseline.
```

### Rule 9 — HR Stale Content Filter (content-based)

```
Location: After the date-based HR stale filter (existing Rule 3).
Logic: If doc_id == "hr_leave_policy" AND chunk_text contains "10 ngày phép năm"
       → quarantine reason "stale_hr_content_10d_annual", regardless of effective_date.
Metric impact (inject scenario): Add row with effective_date=2026-01-01 (passes date filter)
       but chunk_text containing "10 ngày phép năm".
  - Without R9: row passes to cleaned; E6 expectation FAILS → pipeline halts.
  - With R9: row is quarantined at cleaning; E6 always PASSES.
  → quarantine_records increases by 1; pipeline no longer halts on E6.
```

---

## Sprint 2: `quality/expectations.py` — Pydantic + 2 New Expectations

### Pydantic model (Bonus +2)

```python
from pydantic import BaseModel, field_validator
from typing import Literal

ALLOWED_DOC_IDS_LITERAL = Literal[
    "policy_refund_v4", "sla_p1_2026",
    "it_helpdesk_faq", "hr_leave_policy"
]

class PolicyChunk(BaseModel):
    chunk_id: str
    doc_id: ALLOWED_DOC_IDS_LITERAL
    chunk_text: str          # min length enforced by field_validator
    effective_date: str      # ISO YYYY-MM-DD enforced by field_validator
    exported_at: str         # non-empty enforced by field_validator

    @field_validator("chunk_text")
    def text_min_length(cls, v):
        if len(v) < 8:
            raise ValueError(f"chunk_text too short ({len(v)} chars)")
        return v

    @field_validator("effective_date")
    def date_iso_format(cls, v):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"Not ISO YYYY-MM-DD: {v!r}")
        return v
```

### E7 — Pydantic Schema Validation (severity: halt)

```
Logic: Validate every row in cleaned_rows against PolicyChunk.model_validate().
       Collect all ValidationError messages.
       If any row fails → passed=False, severity="halt".
Detail: f"pydantic_invalid={count}, first_error={first_msg}"
Why new: Uses real Pydantic v2 validation (doc_id as Literal enum, min_length,
         ISO date regex) — not a placeholder. Catches schema drift that cleaning
         rules might miss.
```

### E8 — No Duplicate chunk_ids (severity: halt)

```
Logic: Collect all chunk_id values. If len(set) != len(list) → fail.
Detail: f"duplicate_chunk_ids={count_duplicates}"
Why new: Cleaning deduplicates by chunk_text content, but two different texts
         could theoretically hash-collide into the same chunk_id. This
         expectation catches that at the validation layer.
```

### E9 — Doc Coverage (severity: warn)

```
Logic: For each doc_id in ALLOWED_DOC_IDS, check at least 1 row exists
       in cleaned_rows with that doc_id.
       Collect missing doc_ids.
Detail: f"missing_docs={list_of_missing}"
Why new: Detects when an entire document is silently dropped from the
         cleaned set (e.g., all rows quarantined).
Severity: warn (not halt) — a missing doc triggers investigation but
          may be intentional during partial ingests.
```

---

## Sprint 2: `etl_pipeline.py` — Publish boundary timestamp (Bonus +1)

**Where:** In `cmd_embed_internal()`, immediately after `col.upsert(...)` succeeds.

**What:** Return `publish_ts` string from `cmd_embed_internal()` (change return type from `bool` to `tuple[bool, str]`). In `cmd_run()`, unpack and log `publish_boundary_ts`.

**Manifest field:** `"publish_boundary_ts": publish_ts` added to manifest dict.

---

## `requirements.txt` — Add Pydantic v2

Add line: `pydantic>=2.0.0`

---

## Constraints

- All existing function signatures in `clean_rows`, `run_expectations`, `load_raw_csv`, `write_cleaned_csv`, `write_quarantine_csv` remain unchanged externally.
- `cmd_embed_internal` signature unchanged; only return value extended to `tuple[bool, str]` (publish_ts empty string on failure).
- `python etl_pipeline.py run` must exit 0 on clean data.
- `python etl_pipeline.py run --no-refund-fix --skip-validate` must also complete without crash (Sprint 3 inject mode).

---

## Non-Goals

- No new CLI arguments or entrypoints.
- No changes to `eval_retrieval.py`, `grading_run.py`, or monitoring.
- No LLM-judge or Great Expectations integration (Pydantic covers Bonus +2).
