# Kiến trúc pipeline - Lab Day 10

**Nhóm:** Truong Hau Minh Kiet + Vo Thanh Danh  
**Cập nhật:** 2026-04-15

---

## 1. Sơ đồ luồng

```mermaid
flowchart LR
    A[data/raw/policy_export_dirty.csv]
    B[Ingest\nload_raw_csv()]
    C[Clean rules\nallowlist, date normalize,\nR7-R9, dedupe, refund fix]
    D[cleaned CSV]
    E[quarantine CSV]
    F[Expectation suite\nE1-E9]
    G[Chroma publish\nupsert + prune]
    H[Eval / grading]
    I[Day 09 retrieval]

    A --> B
    B --> C
    C --> D
    C --> E
    D --> F
    F --> G
    G --> H
    G --> I
```

**Boundary quan sát chính**

- `ingest_boundary_ts`: ghi ngay sau khi đọc raw thành công.
- `publish_boundary_ts`: ghi ngay sau khi `col.upsert(...)` hoàn tất.
- `run_id`: nối log, cleaned CSV, quarantine CSV, manifest, eval và grading JSONL.
- `quarantine`: không drop im lặng; mọi record lỗi đều đi vào `artifacts/quarantine/*.csv`.

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner nhóm |
|------------|-------|--------|------------|
| Ingest | `data/raw/policy_export_dirty.csv` | `raw_records`, `ingest_boundary_ts`, log đầu run | Võ Thành Danh |
| Transform | raw rows | cleaned rows + quarantine rows | Võ Thành Danh |
| Quality | cleaned rows | expectation results E1-E9, halt/warn | Võ Thành Danh |
| Embed | cleaned CSV | collection `day10_kb`, `publish_boundary_ts`, `embed_prune_removed` | Võ Thành Danh + Trương Hậu Minh Kiệt |
| Monitor / Docs | manifest, eval CSV, grading JSONL | `quality_report.md`, runbook, group report | Trương Hậu Minh Kiệt |

---

## 3. Idempotency và rerun

Pipeline dùng `chunk_id` ổn định từ `doc_id + chunk_text + seq`, sau đó publish bằng `col.upsert(ids=chunk_id)`. Điều này giúp rerun không tạo vector mới cho cùng một chunk. Để tránh "mồi cũ" còn sót sau khi từng publish dữ liệu xấu, bước embed còn có `prune`: xóa những vector id không còn nằm trong cleaned snapshot hiện tại.

Chứng cứ thực tế:

- `artifacts/logs/run_inject-bad.log` có `embed_prune_removed=1` khi chuyển từ index sạch sang publish bản inject.
- `artifacts/logs/run_final-good-rerun.log` tiếp tục có `embed_prune_removed=1` khi khôi phục snapshot tốt sau inject.
- Sau run cuối `final-submit`, collection đếm được `collection_count=6`, đúng bằng `cleaned_records=6` trong `manifest_final-submit.json`.

Nhờ thiết kế này, snapshot trong Chroma luôn khớp cleaned CSV của run gần nhất thay vì tích lũy rác qua nhiều lần chạy.

---

## 4. Liên hệ Day 09

Lab Day 10 dùng cùng domain CS + IT Helpdesk với Day 09, nhưng tập trung vào tầng dữ liệu trước retrieval. Collection `day10_kb` có thể được agent Day 09 dùng lại trực tiếp nếu muốn kiểm thử câu trả lời trên corpus đã clean. Nhóm giữ collection riêng cho Day 10 để dễ chứng minh before/after và grading mà không làm nhiễu collection của bài Day 09.

---

## 5. Rủi ro đã biết

- `freshness_check` hiện dựa trên `latest_exported_at` trong manifest, nên bộ dữ liệu mẫu cố ý bị `FAIL` với SLA 24 giờ.
- Ranh giới versioning HR vẫn hard-code cutoff `2026-01-01` trong code; đây là chỗ nên đưa về contract/env nếu có thêm thời gian.
- Eval hiện là retrieval + keyword, chưa có LLM judge cho các câu trả lời tổng hợp dài.
