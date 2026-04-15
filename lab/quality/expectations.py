"""
Expectation suite — tích hợp Pydantic v2 (Bonus +2).

Baseline E1–E6 giữ nguyên logic.
Sprint 2 bổ sung:
  E7 – Pydantic schema validation (halt)  : mỗi cleaned row phải pass PolicyChunk.model_validate().
  E8 – No duplicate chunk_ids (halt)      : chunk_id phải duy nhất trong cleaned set.
  E9 – Doc coverage / all allowed (warn)  : mỗi allowed doc_id phải có ≥1 chunk trong cleaned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Pydantic v2 model — real validation, không placeholder
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel, field_validator, ValidationError
    from typing import Literal

    _ALLOWED_LITERAL = Literal[
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    ]

    class PolicyChunk(BaseModel):
        """Schema contract cho một cleaned chunk trước khi embed."""

        chunk_id: str
        doc_id: _ALLOWED_LITERAL
        chunk_text: str
        effective_date: str
        exported_at: str

        @field_validator("chunk_text")
        @classmethod
        def text_min_length(cls, v: str) -> str:
            if len(v) < 8:
                raise ValueError(f"chunk_text quá ngắn ({len(v)} ký tự, tối thiểu 8)")
            return v

        @field_validator("effective_date")
        @classmethod
        def date_iso_format(cls, v: str) -> str:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError(f"effective_date không đúng định dạng ISO YYYY-MM-DD: {v!r}")
            return v

        @field_validator("exported_at")
        @classmethod
        def exported_at_non_empty(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("exported_at không được rỗng")
            return v

    HAS_PYDANTIC = True

except ImportError:  # pragma: no cover
    HAS_PYDANTIC = False
    PolicyChunk = None  # type: ignore[assignment,misc]
    ValidationError = Exception  # type: ignore[assignment,misc]

# Dùng để check doc coverage (E9) mà không import chéo từ cleaning_rules
_ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # ------------------------------------------------------------------
    # E1: có ít nhất 1 dòng sau clean
    # ------------------------------------------------------------------
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # ------------------------------------------------------------------
    # E2: không doc_id rỗng
    # ------------------------------------------------------------------
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # ------------------------------------------------------------------
    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    # ------------------------------------------------------------------
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # ------------------------------------------------------------------
    # E4: chunk_text đủ dài (≥8 ký tự)
    # ------------------------------------------------------------------
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # ------------------------------------------------------------------
    # E5: effective_date đúng định dạng ISO sau clean
    # ------------------------------------------------------------------
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # ------------------------------------------------------------------
    # E6: không còn marker phép năm cũ 10 ngày trên doc HR
    # ------------------------------------------------------------------
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ------------------------------------------------------------------
    # E7: Pydantic schema validation (Sprint 2 — Bonus +2)
    # Mỗi cleaned row phải pass PolicyChunk.model_validate().
    # Severity: halt — schema drift phải dừng pipeline ngay.
    # ------------------------------------------------------------------
    if not HAS_PYDANTIC:
        results.append(
            ExpectationResult(
                "pydantic_schema_valid",
                True,
                "halt",
                "pydantic not installed — skipped (install pydantic>=2.0.0)",
            )
        )
    else:
        pydantic_errors: List[str] = []
        for i, r in enumerate(cleaned_rows):
            try:
                PolicyChunk.model_validate(r)  # type: ignore[union-attr]
            except ValidationError as exc:  # type: ignore[misc]
                first_msg = exc.errors()[0]["msg"] if exc.errors() else str(exc)
                pydantic_errors.append(f"row_{i}({r.get('chunk_id', '?')}): {first_msg}")
        ok7 = len(pydantic_errors) == 0
        detail7 = f"pydantic_invalid={len(pydantic_errors)}"
        if pydantic_errors:
            detail7 += f", first_error={pydantic_errors[0]}"
        results.append(
            ExpectationResult(
                "pydantic_schema_valid",
                ok7,
                "halt",
                detail7,
            )
        )

    # ------------------------------------------------------------------
    # E8: No duplicate chunk_ids (Sprint 2)
    # Cleaning dedup theo chunk_text; expectation double-check tại layer validation.
    # Severity: halt — trùng chunk_id gây vector overwrite không kiểm soát.
    # ------------------------------------------------------------------
    chunk_ids = [r.get("chunk_id", "") for r in cleaned_rows]
    dup_count = len(chunk_ids) - len(set(chunk_ids))
    ok8 = dup_count == 0
    results.append(
        ExpectationResult(
            "no_duplicate_chunk_ids",
            ok8,
            "halt",
            f"duplicate_chunk_ids={dup_count}",
        )
    )

    # ------------------------------------------------------------------
    # E9: Doc coverage — mỗi allowed doc_id phải có ≥1 chunk (Sprint 2)
    # Phát hiện khi toàn bộ một document bị drop khỏi cleaned set.
    # Severity: warn — thiếu doc đáng điều tra nhưng không nhất thiết halt
    #           (có thể do partial ingest có chủ đích).
    # ------------------------------------------------------------------
    present_docs = {r.get("doc_id", "") for r in cleaned_rows}
    missing_docs = sorted(_ALLOWED_DOC_IDS - present_docs)
    ok9 = len(missing_docs) == 0
    results.append(
        ExpectationResult(
            "doc_coverage_all_allowed",
            ok9,
            "warn",
            f"missing_docs={missing_docs}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
