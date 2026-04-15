"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).

Rules mới (Sprint 2):
  R7 – BOM Strip        : strip \\ufeff khỏi doc_id / chunk_text trước mọi check.
  R8 – Exported-at      : quarantine nếu exported_at rỗng hoặc không parse ISO datetime.
  R9 – HR stale content : quarantine hr_leave_policy chunk chứa "10 ngày phép năm"
                          bất kể effective_date (content-based, độc lập với date filter).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


# ---------------------------------------------------------------------------
# RULE 7: Strip UTF-8 BOM
# ---------------------------------------------------------------------------
def _strip_bom(s: str) -> str:
    """
    Strip UTF-8 BOM prefix (\\ufeff) từ bất kỳ trường string nào.

    metric_impact (inject): Thêm row với doc_id = "\\ufeffpolicy_refund_v4".
      - Không có R7 → quarantine reason="unknown_doc_id".
      - Có R7       → BOM stripped, doc_id hợp lệ → cleaned.
      Kết quả: quarantine_records giảm 1, cleaned_records tăng 1 so với no-rule baseline.
    """
    return s.lstrip("\ufeff")


# ---------------------------------------------------------------------------
# RULE 8: Validate exported_at field
# ---------------------------------------------------------------------------
def _validate_exported_at(raw: str) -> str:
    """
    Kiểm tra trường exported_at.
    Trả về error_reason (string) nếu không hợp lệ, chuỗi rỗng nếu OK.

    Hợp lệ: non-empty và khớp pattern ISO datetime YYYY-MM-DDTHH:MM:SS...

    metric_impact (inject): Thêm row với exported_at="" (hoặc "April 10 2026").
      - Không có R8 → row được cleaned (exported_at field chỉ pass-through).
      - Có R8       → row bị quarantine reason="missing_exported_at" /
                      "invalid_exported_at_format".
      Kết quả: quarantine_records tăng 1 so với no-rule baseline.
    """
    s = (raw or "").strip()
    if not s:
        return "missing_exported_at"
    if not _ISO_DATETIME.match(s):
        return "invalid_exported_at_format"
    return ""


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) Loại trùng nội dung chunk_text (giữ bản đầu).
    6) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.

    Sprint 2 — Rules mới:
    R7) Strip UTF-8 BOM khỏi doc_id và chunk_text trước mọi kiểm tra.
    R8) Quarantine nếu exported_at rỗng hoặc không parse ISO datetime.
    R9) Quarantine hr_leave_policy chunk chứa "10 ngày phép năm" (content-based stale).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # ----------------------------------------------------------------
        # RULE 7: Strip UTF-8 BOM từ doc_id và chunk_text
        # Phải đứng trước allowlist check để BOM-prefixed ID được nhận diện đúng.
        # ----------------------------------------------------------------
        doc_id = _strip_bom(doc_id)
        text = _strip_bom(text)

        # Baseline rule 1: allowlist doc_id
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # Baseline rule 2: chuẩn hoá effective_date
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # ----------------------------------------------------------------
        # RULE 8: Kiểm tra exported_at — phải có và đúng ISO datetime
        # ----------------------------------------------------------------
        exp_err = _validate_exported_at(exported_at)
        if exp_err:
            quarantine.append({**raw, "reason": exp_err})
            continue

        # Baseline rule 3: HR stale version theo date
        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        # ----------------------------------------------------------------
        # RULE 9: HR stale content filter — content-based, độc lập với date.
        # Bắt trường hợp doc có effective_date hợp lệ nhưng nội dung vẫn còn
        # nhắc đến "10 ngày phép năm" (policy cũ xung đột với 12 ngày hiện tại).
        # metric_impact: xem docstring _validate_exported_at pattern tương tự.
        # inject: row effective_date=2026-01-01 + text "10 ngày phép năm"
        #   → không có R9: cleaned (vượt date filter), E6 FAIL → pipeline halt.
        #   → có R9: quarantined, E6 luôn PASS.
        # ----------------------------------------------------------------
        if doc_id == "hr_leave_policy" and "10 ngày phép năm" in text:
            quarantine.append({**raw, "reason": "stale_hr_content_10d_annual"})
            continue

        # Baseline rule 4: chunk_text rỗng
        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # Baseline rule 5: dedup theo nội dung
        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # Baseline rule 6: fix stale refund window 14→7 ngày
        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
