# Báo Cáo Cá Nhân - Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trương Hầu Minh Kiệt  
**Vai trò:** Monitoring / Docs / Eval - Grading  
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào?

Trong bài Day 10 này tôi phụ trách phần còn lại sau khi bạn Võ Thành Danh đã hoàn thành Sprint 1 và Sprint 2. Cụ thể tôi làm các file tài liệu và evidence của Sprint 3-4 gồm `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`, `docs/quality_report.md`, `reports/group_report.md`, `reports/individual/truong_hau_minh_kiet.md`, đồng thời bổ sung `data/grading_questions.json`, `.env.example` và chỉnh lại `README.md` để khớp rubric 3 câu grading. Tôi cũng trực tiếp chạy các artifact `after_inject_bad.csv`, `after_fix_final-submit.csv`, `grading_run.jsonl`, `metric_impact.json` và manifest `final-submit`.

Phần việc của tôi nối trực tiếp với phần Danh đã làm ở chỗ tôi không viết lại cleaning rule hay expectation suite, mà dùng chính pipeline đó để chứng minh bằng số liệu rằng các rule/expectation và cơ chế publish hoạt động đúng trong kịch bản xấu rồi khôi phục về kịch bản tốt. Bằng chứng rõ nhất là tôi dùng cùng bộ raw nhưng hai run `inject-bad` và `final-submit` cho ra chất lượng retrieval khác nhau.

---

## 2. Một quyết định kỹ thuật

Quyết định kỹ thuật quan trọng nhất của tôi là giữ nguyên logic freshness `FAIL` thay vì sửa timestamp mẫu để biến báo cáo thành `PASS`. Khi tôi chạy `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_final-submit.json`, kết quả là `FAIL` với `age_hours≈120.163` và `sla_hours=24.0`. Tôi chọn giải thích rõ trong runbook và quality report rằng đây là snapshot mẫu đã cũ hơn SLA, còn publish boundary của pipeline vẫn chạy xong bình thường. Theo tôi, cách này đúng tinh thần observability hơn là "chữa" dữ liệu để đẹp số.

Tôi cũng quyết định dùng thêm grading JSONL làm lớp kiểm cuối. Chỉ nhìn `eval_retrieval.py` là chưa đủ vì grading còn yêu cầu `gq_d10_03` phải đúng cả `contains_expected`, `hits_forbidden=false` và `top1_doc_matches=true`. Nhờ vậy tôi có thể chốt trạng thái index cuối bằng `python instructor_quick_check.py --grading ... --manifest ...` thay vì chỉ đọc tay CSV.

---

## 3. Một lỗi hoặc anomaly đã xử lý

Anomaly rõ nhất tôi xử lý là trường hợp index bị bẩn dù số record không đổi. Ở run `inject-bad`, log cho thấy `raw_records=10`, `cleaned_records=6`, `quarantine_records=4`, gần giống hệt run tốt. Nếu chỉ nhìn volume thì rất dễ kết luận sai rằng pipeline vẫn ổn. Nhưng ngay trong cùng log lại có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`, và vì run đó dùng `--skip-validate` nên dữ liệu xấu vẫn bị publish.

Tôi phát hiện vấn đề bằng `artifacts/eval/after_inject_bad.csv`: dòng `q_refund_window` có `contains_expected=yes` nhưng `hits_forbidden=yes`. Sau đó tôi rerun luồng chuẩn bằng `final-submit`, sinh lại `after_fix_final-submit.csv`, rồi kiểm tra thấy cùng câu hỏi chuyển sang `hits_forbidden=no`. Cuối cùng tôi chạy `grading_run.py` và `instructor_quick_check.py`; cả ba câu `gq_d10_01..03` đều `OK`. Tôi xem đây là anomaly quan trọng nhất vì nó chứng minh data bug có thể không đổi volume nhưng vẫn làm agent đọc nhầm context.

---

## 4. Bằng chứng trước / sau

`run_id` tôi dùng để chốt bài là `inject-bad` và `final-submit`.

- Trước fix: `after_inject_bad.csv` - `q_refund_window` -> `contains_expected=yes`, `hits_forbidden=yes`
- Sau fix: `after_fix_final-submit.csv` - `q_refund_window` -> `contains_expected=yes`, `hits_forbidden=no`

Tôi cũng kiểm lại câu Merit là `q_leave_version`; cả trước và sau đều giữ `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`. Điều này giúp tôi yên tâm rằng khi sửa refund pipeline không làm hỏng policy HR 2026.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ đưa cutoff HR `2026-01-01` ra khỏi code và đọc từ `contracts/data_contract.yaml` hoặc biến môi trường. Phần này vừa giảm hard-code, vừa tạo được một bằng chứng Distinction tốt hơn vì có thể inject cutoff khác nhau để chứng minh quyết định clean đổi theo contract chứ không bị đóng cứng trong source.
