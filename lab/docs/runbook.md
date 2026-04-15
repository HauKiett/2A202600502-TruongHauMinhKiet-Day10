# Runbook - Lab Day 10

---

## Symptom

User hoặc agent trả lời sai version nghiệp vụ dù pipeline vẫn có vẻ "chạy xong". Ví dụ rõ nhất trong lab là câu hoàn tiền bị kéo theo chunk stale `14 ngày làm việc` thay vì `7 ngày làm việc`, hoặc freshness bị `FAIL` vì snapshot đã quá cũ.

---

## Detection

- Log pipeline có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`.
- Log `artifacts/logs/run_inject-bad.log` cho `q_refund_window` có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`.
- Grading sẽ fail ở `gq_d10_01` nếu top-k còn chứa chunk stale refund.
- Freshness check trả về `FAIL` nếu `age_hours > 24`, như run `final-submit` có `age_hours≈120.581`.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/manifests/manifest_<run_id>.json` | Xác nhận `run_id`, số record và boundary timestamps |
| 2 | Mở `artifacts/logs/run_<run_id>.log` | Thấy expectation nào fail, có `embed_prune_removed` hay không |
| 3 | So sánh `artifacts/logs/run_inject-bad.log` với `artifacts/eval/after_fix_final-submit.csv` | Xác nhận run inject bị fail ở stale refund và run cuối không còn forbidden content |
| 4 | Nếu nghi stale content | Kiểm cleaned CSV và quarantine CSV để xem row sai nằm ở đâu, đã bị giữ lại hay đã được cô lập |

---

## Mitigation

- Nếu đang ở bản inject hoặc publish lỗi, chạy lại luồng chuẩn:

```bash
python etl_pipeline.py run --run-id final-submit
python eval_retrieval.py --out artifacts/eval/after_fix_final-submit.csv
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

- Không dùng `--skip-validate` ngoài kịch bản demo Sprint 3.
- Sau rerun, kiểm tra lại `grading_run.jsonl` bằng `python instructor_quick_check.py --grading ...`.
- Nếu freshness vẫn `FAIL` nhưng đây là snapshot mẫu cũ, ghi rõ trong báo cáo rằng fail xuất phát từ dữ liệu nguồn chứ không phải do publish boundary bị chậm.

---

## Prevention

- Giữ expectation refund stale là `halt`, không hạ xuống `warn`.
- Dùng `run_id` cho mọi artifact để truy vết before/after.
- Không publish bản test vào collection cuối trước khi nộp grading; nếu đã inject, bắt buộc rerun luồng chuẩn.
- Dùng `metric_impact.json` để chứng minh R7/R8/R9 và E7/E8/E9 thật sự làm thay đổi số liệu hoặc trạng thái halt/warn.
- Nếu có thêm thời gian, đọc cutoff HR từ contract/env thay vì hard-code trong rule.

---

## Peer Review 3 câu

1. **Rerun có bị duplicate vector không?**  
   Không. Pipeline dùng `chunk_id` ổn định, `upsert` theo `chunk_id` và `prune` id không còn trong cleaned snapshot. Sau run cuối collection còn đúng `6` vector.

2. **Freshness đo ở đâu?**  
   Nhóm log cả `ingest_boundary_ts` và `publish_boundary_ts`, nhưng SLA được so với `latest_exported_at` trong manifest để phản ánh độ tươi của snapshot nguồn.

3. **Flagged rows đi đâu?**  
   Tất cả row lỗi đi vào `artifacts/quarantine/quarantine_<run_id>.csv`; không có silent drop.
