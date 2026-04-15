# Data contract - Lab Day 10

> File này cụ thể hóa `contracts/data_contract.yaml` cho nhóm Minh Kiệt - Thành Danh.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|--------------------|--------------------|----------------|
| `data/raw/policy_export_dirty.csv` | Batch CSV export từ hệ nguồn mô phỏng | duplicate, `doc_id` lạ, thiếu `effective_date`, `exported_at` rỗng, stale content | `raw_records`, `cleaned_records`, `quarantine_records`, expectation halt |
| `data/docs/*.txt` | Canonical reference do nhóm giữ trong repo | canonical thay đổi nhưng export chưa sync lại, version HR/refund lệch | eval `q_refund_window`, `q_leave_version`, grading JSONL |

**Owner nhóm:** `team_minhkiet_danh`  
**SLA freshness:** 24 giờ, đo ở boundary publish nhưng so sánh với `latest_exported_at` của snapshot.

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | ID ổn định dùng cho idempotent upsert vào Chroma |
| `doc_id` | string | Có | Một trong `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy` |
| `chunk_text` | string | Có | Nội dung chunk sau clean; refund stale 14 ngày được sửa về 7 ngày nếu chạy luồng chuẩn |
| `effective_date` | date | Có | Chuẩn ISO `YYYY-MM-DD` sau clean |
| `exported_at` | datetime | Có | ISO datetime; rule R8 quarantine nếu thiếu hoặc sai format |

Schema này được validate thêm bằng Pydantic v2 trong expectation `pydantic_schema_valid`.

---

## 3. Quy tắc quarantine vs drop

- Nhóm không drop im lặng record lỗi. Mọi record vi phạm allowlist, sai format ngày, stale policy hoặc duplicate đều được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv`.
- `cleaned_records` chỉ chứa các row đủ điều kiện để embed và qua expectation suite.
- Record bị quarantine chỉ được "merge lại" sau khi sửa ở nguồn hoặc điều chỉnh cleaning rule có chủ đích, rồi rerun toàn bộ pipeline với `run_id` mới.
- Duplicate chunk không được giữ cả hai phía vì sẽ làm sai volume và có thể nhiễu retrieval.

---

## 4. Phiên bản và canonical

- Source of truth cho refund là `data/docs/policy_refund_v4.txt`, trong đó cửa sổ hoàn tiền hiện hành là **7 ngày làm việc**.
- Source of truth cho HR leave là `data/docs/hr_leave_policy.txt`, trong đó chính sách 2026 cho nhân viên dưới 3 năm là **12 ngày phép năm**.
- Raw export chỉ là snapshot vận hành, có thể chứa bản cũ hoặc lỗi migration; vì vậy pipeline phải có cả clean rule lẫn eval retrieval để chứng minh index cuối cùng bám canonical.
- Với P1 SLA, canonical là `data/docs/sla_p1_2026.txt`, dùng để kiểm lại câu `15 phút`.
