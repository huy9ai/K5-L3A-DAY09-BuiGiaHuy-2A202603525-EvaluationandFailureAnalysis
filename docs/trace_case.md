# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, thuộc report `E-seeded_regression-20261117-c81c` (`src/reports/eval_seeded_regression.json`) |
| Triệu chứng | Grader Lab 8 (`trial_pass`) FAIL với `status resolved != denied`; `RefundAmountCorrect` & `DbFactKept` FAIL. Ledger ghi `refund_vnd=20000`, `refund_count=1` (nhãn: `0` / `0`), reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."`. |
| Bước sai đầu tiên | Event `#3` · `model_override` · `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event `#1 handoff` (`REQ-C-002`, allowlist chỉ có tool chỉ đọc) và event `#2 investigator` (`lookup_order` trả về chính xác dữ liệu DB: `order_id="O-202", status="delivered", delay_days=2`) đều đúng. Từ event `#3`, agent tin số `5` ngày trong ticket để ghi đè `delay_days=2` của DB, kéo theo `#4 quote` tính nhầm `20.000đ` và `#6 reply` báo đã hoàn. |
| Failure mode | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md` |
| Đối chứng | Trên shape `fixed C-002@11`: sau `#1 handoff` và `#2 investigator` (`delay_days=2`), không có `model_override`; bước `#3` là `quote {"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}` và `#4` là `reply` từ chối (`denied`, ledger `0`). |
| Regression test | `src/tests/test_lab9_trace_case.py::test_c002_seed11_trace_regression_caught_on_seeded_and_passes_on_fixed` (dùng `DbFactKept` + `RefundAmountCorrect`): đã chạy thấy FAIL trên `seeded_regression C-002@11` (bị hai grader bắt) và PASS trên `fixed C-002@11`. |
| Chưa chắc chắn | Trace trên `MockLLM` không chứng minh được trong production model thật có sinh event tường minh `model_override` hay thực hiện ngầm trong suy luận (như `quiet_override` không để lại event, chỉ bắt được bằng outcome grader `RefundAmountCorrect`). |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
