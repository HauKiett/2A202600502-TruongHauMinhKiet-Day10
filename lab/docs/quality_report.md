# Quality report - Lab Day 10

**run_id:** `final-submit`  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước fix (`inject-bad`) | Sau fix (`final-submit`) | Ghi chú |
|--------|---------------------------|------------------------------|---------|
| `raw_records` | 10 | 10 | Cùng một raw snapshot |
| `cleaned_records` | 6 | 6 | Volume không đổi; khác biệt nằm ở content |
| `quarantine_records` | 4 | 4 | Quarantine không đổi trong kịch bản này |
| Expectation halt? | Có | Không | `refund_no_stale_14d_window` fail ở bản inject |

Điểm quan trọng của Sprint 3 là số record không đổi nhưng retrieval vẫn xấu đi nếu content stale lọt vào index. Vì vậy nhóm không chỉ nhìn volume mà còn dùng eval CSV và grading JSONL để chứng minh chất lượng thật.

---

## 2. Before / after retrieval

**Artifact chính**

- `artifacts/logs/run_inject-bad.log`
- `artifacts/eval/after_fix_final-submit.csv`
- `artifacts/eval/grading_run.jsonl`

**Câu hỏi then chốt: `q_refund_window`**

- Trước fix (`inject-bad`): log cho thấy `refund_no_stale_14d_window` fail với `violations=1`
- Sau fix (`final-submit`): `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_id=policy_refund_v4`

Diễn giải: bản inject cố ý bỏ rule sửa refund `14 -> 7`, nên expectation suite phát hiện stale refund ngay trước publish. Sau khi khôi phục snapshot sạch ở `final-submit`, eval cho thấy câu refund không còn dính forbidden content trong top-k.

**Merit: `q_leave_version`**

- Sau fix (`final-submit`): `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`
- `grading_run.jsonl`: `gq_d10_03` có `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`

Diễn giải: rule stale HR theo date + content giúp giữ index đúng với canonical 2026, nên câu HR đạt điều kiện Merit ở run cuối.

---

## 3. Freshness & monitor

Kết quả từ `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_final-submit.json`:

- `FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 120.581, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`

Nhóm giữ nguyên `FAIL` này thay vì chỉnh tay timestamp vì đây là đặc tính của bộ snapshot mẫu: dữ liệu nguồn cũ hơn SLA 24 giờ. Trong runbook nhóm ghi rõ đây là fail hợp lệ của nguồn dữ liệu, không phải lỗi ở bước publish.

---

## 4. Corruption inject (Sprint 3)

Nhóm dùng đúng cờ demo trong README:

```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

Kịch bản này cố ý bỏ rule sửa refund `14 -> 7` rồi vẫn publish lên Chroma để quan sát tác động. Log `run_inject-bad.log` cho thấy:

- `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`
- `WARN: expectation failed but --skip-validate -> tiep tuc embed`

Sau đó nhóm chạy lại luồng chuẩn `final-submit` để khôi phục snapshot sạch và sinh grading JSONL.

---

## 5. Hạn chế & việc chưa làm

- Freshness mới kiểm tra snapshot age qua manifest, chưa đọc watermark từ hệ nguồn thật.
- Ranh giới HR cutoff `2026-01-01` vẫn hard-code trong code thay vì lấy từ contract/env.
- Eval hiện dùng retrieval + keyword; nếu có thêm thời gian nhóm sẽ thêm một lớp judge cho câu trả lời tổng hợp.
