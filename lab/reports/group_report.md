# Báo Cáo Nhóm - Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** 2A202600502-Trương Hầu Minh Kiệt, 2A202600503-Trương Hầu Minh Kiệt
**Thành viên:**

| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Võ Thành Danh | Ingestion, Cleaning, Expectation, Embed baseline (Sprint 1-2) | vothanhdanh8208@gmail.com |
| Trương Hầu Minh Kiệt | Monitoring, eval/grading, docs, reports (Sprint 3-4) | truonghaukiet@gmai.com |

**Ngày nộp:** 2026-04-15  


---

## 1. Pipeline tổng quan

Nhóm dùng một entrypoint duy nhất là `python etl_pipeline.py run --run-id final-submit` để chạy toàn bộ luồng ingest -> clean -> validate -> embed. Raw đầu vào là `data/raw/policy_export_dirty.csv`, sau đó pipeline sinh `cleaned CSV`, `quarantine CSV`, log, manifest và publish vào Chroma collection `day10_kb`. `run_id` xuất hiện ngay đầu log, đồng thời được gắn vào manifest và metadata lúc embed nên nhóm có thể nối toàn bộ trace của một lần chạy từ raw cho đến retrieval.

Võ Thành Danh phụ trách Sprint 1-2: ingest, log `raw_records/cleaned_records/quarantine_records`, R7-R9, Pydantic v2, E7-E9 và embed idempotent `upsert + prune`. Trương Hầu Minh Kiệt phụ trách Sprint 3-4: inject xấu, before/after eval, `grading_questions.json`, `grading_run.py`, runbook, quality report và các báo cáo nộp bài.

---

## 2. Cleaning & expectation

Baseline của lab đã có allowlist `doc_id`, chuẩn hóa `effective_date`, filter HR stale theo date, dedupe và sửa refund stale. Trên nền đó, Danh mở rộng thêm R7-R9 và E7-E9. Nhóm đặc biệt ghi rõ metric impact để tránh bị xem là trivial. Artifact `artifacts/eval/metric_impact.json` được tạo riêng để mô tả từng inject nhỏ và tác động quan sát được.

### 2a. Bảng `metric_impact`

| Rule / Expectation mới | Trước | Sau / khi inject | Chứng cứ |
|------------------------|-------|------------------|----------|
| R7 - BOM strip | Không có rule: `cleaned=0`, `quarantine=1`, reason `unknown_doc_id` | Có rule: `cleaned=1`, `quarantine=0` | `artifacts/eval/metric_impact.json` |
| R8 - Validate `exported_at` | Không có rule: `cleaned=1`, `quarantine=0` | Có rule: `cleaned=0`, `quarantine=1`, reason `missing_exported_at` | `artifacts/eval/metric_impact.json` |
| R9 - HR stale content | Không có rule: `cleaned=1`, expectation halt `true`, `violations=1` | Có rule: `cleaned=0`, `quarantine=1`, reason `stale_hr_content_10d_annual` | `artifacts/eval/metric_impact.json` |
| E7 - Pydantic schema valid | Row cleaned giả lập với `exported_at=''` | `pydantic_invalid=1`, severity `halt`, pipeline dừng | `artifacts/eval/metric_impact.json` |
| E8 - No duplicate chunk IDs | Hai row cleaned giả lập trùng `chunk_id` | `duplicate_chunk_ids=1`, severity `halt` | `artifacts/eval/metric_impact.json` |
| E9 - Doc coverage | Bỏ toàn bộ `hr_leave_policy` khỏi cleaned giả lập | `missing_docs=['hr_leave_policy']`, severity `warn` | `artifacts/eval/metric_impact.json` |

Ví dụ expectation fail thực tế trong pipeline là run `inject-bad`: log có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`. Đây là fail có chủ đích để chứng minh nếu vẫn ép publish bằng `--skip-validate`, retrieval sẽ nhìn có vẻ đúng nhưng top-k vẫn bị bẩn.

---

## 3. Before / after ảnh hưởng retrieval

Kịch bản inject của nhóm là:

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
python etl_pipeline.py run --run-id final-submit
python eval_retrieval.py --out artifacts/eval/after_fix_final-submit.csv
```

Điểm quan trọng là volume của hai run gần như không đổi: cả `inject-bad` và `final-submit` đều có `raw_records=10`, `cleaned_records=6`, `quarantine_records=4`. Sự khác biệt thật nằm ở chất lượng content trong top-k retrieval.

Ở câu `q_refund_window`, file `after_inject_bad.csv` cho kết quả `contains_expected=yes` nhưng `hits_forbidden=yes`, nghĩa là top-k vẫn còn chunk stale `14 ngày làm việc`. Sau khi chạy lại luồng chuẩn, `after_fix_final-submit.csv` đổi thành `contains_expected=yes`, `hits_forbidden=no`. Đây là bằng chứng before/after mạnh nhất của nhóm vì nó cho thấy một regression ở tầng data có thể không làm sai top-1 ngay lập tức nhưng vẫn làm index không an toàn cho agent.

Ở câu `q_leave_version`, cả trước và sau đều có `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`. Điều này chứng minh bộ rule HR hiện tại giữ được đúng version 2026 của chính sách nghỉ phép và đạt điều kiện Merit cho `gq_d10_03`.

---

## 4. Freshness & monitoring

Manifest cuối cùng của nhóm là `artifacts/manifests/manifest_final-submit.json`, trong đó có cả `ingest_boundary_ts` và `publish_boundary_ts`. Freshness vẫn `FAIL` vì `latest_exported_at=2026-04-10T08:00:00` cũ hơn SLA 24 giờ (`age_hours≈120.163`). Nhóm giữ nguyên fail này và giải thích trong runbook rằng đây là đặc tính của dữ liệu mẫu, không phải lỗi publish. Việc log cả hai boundary giúp nhóm tách được chuyện pipeline publish xong với chuyện snapshot nguồn còn tươi hay không.

---

## 5. Liên hệ Day 09

Day 10 nối trực tiếp với Day 09 ở chỗ cùng dùng domain CS + IT Helpdesk. Collection `day10_kb` là bản corpus đã clean, validate và publish có kiểm soát. Nếu dùng collection này trong Day 09, agent sẽ giảm nguy cơ trả lời theo policy cũ. Nhóm giữ collection riêng cho Day 10 để việc inject corruption và grading không ảnh hưởng bài multi-agent đã làm trước đó.

---

## 6. Rủi ro còn lại & việc chưa làm

- Cutoff versioning HR vẫn hard-code trong code, chưa lấy động từ contract/env.
- Freshness chưa đọc watermark hệ nguồn thật.
- Eval mới dừng ở retrieval + keyword, chưa mở rộng sang LLM judge.

---

## 7. Peer review 3 câu

- **Rerun có duplicate vector không?** Không. `chunk_id` ổn định, `upsert` theo id và có `prune`; collection cuối được kiểm là `6` vector.
- **Freshness đo ở đâu?** Nhóm log cả ingest và publish boundary, nhưng SLA được tính từ `latest_exported_at` để phản ánh độ tươi của snapshot nguồn.
- **Flagged rows đi đâu?** Tất cả đi vào `artifacts/quarantine/quarantine_<run_id>.csv`; nhóm không drop im lặng.
