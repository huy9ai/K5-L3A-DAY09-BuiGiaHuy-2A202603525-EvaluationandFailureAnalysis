# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có (`tp=24, fp=4, fn=6, tn=66`; observed fail `0.28` → Rogan-Gladen `0.30`) | dùng (chỉ cho văn phong/giọng điệu, kiểm tra thêm theo rubric mới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (`tp=9, fp=0, fn=21, tn=70`; observed fail `0.09` → Rogan-Gladen `0.30`) | **loại** (không dùng làm gate) |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | `H-008` (tone) | PASS | FAIL | Người đúng | Xưng `"em"` + `"nha"` quá suồng sã; sửa rubric: cấm đại từ thân mật (`em/nha/bạn`) khi CSKH. |
| 2 | `H-017` (tone) | PASS | FAIL | Người đúng | `"Dạ, bạn ơi ... rồi nha"`: dùng `"bạn"` với khách hàng; sửa rubric: bắt buộc xưng `"anh/chị"`. |
| 3 | `H-029` (tone) | PASS | FAIL | Người đúng | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."`: judge bị đánh lừa bởi `"Dạ, vui lòng"`, bỏ sót vế ra lệnh `"không cần nhắn thêm"`. |
| 4 | `H-042` (tone) | FAIL | PASS | Người đúng | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."`: ngắn gọn đủ ý; sửa rubric: không bắt buộc câu xin lỗi khi không cần thiết. |
| 5 | `H-051` (tone) | FAIL | PASS | Người đúng | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."`: từ `"refund"` được CS LogiX cho phép; thêm ngoại lệ thuật ngữ vào rubric. |
| 6 | `H-081` (tone) | FAIL | PASS | Judge đúng | `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."`: lịch sự đúng chuẩn; nhãn người bị gán nhầm do đọc nhầm ticket → sửa lại nhãn vàng. |
| 7 | `HL-015` (helpful) | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."` nhưng ledger ghi `40.000đ`: judge không thấy ledger nên chấm PASS dựa trên câu chữ lịch sự. |
| 8 | `HL-020` (helpful) | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-303 ạ."` nhưng ledger ghi `120.000đ`: sai tiền (FM-08), phải chấm bằng code (`ReplyMatchesLedger`), không dùng judge. |
| 9 | `HL-047` (helpful) | PASS | FAIL | Người đúng | `"Ok bạn, đơn O-515 xử lý rồi nhé."`: sai xưng hô và thiếu thông tin số tiền/trạng thái cụ thể nhưng judge vẫn chấm PASS. |
| 10 | `HL-091` (helpful) | PASS | FAIL | Người đúng | `"Ok bạn, đơn O-233 xử lý rồi nhé."`: lặp lại lỗi `fn` về xưng hô thân mật/cụt thông tin mà judge bỏ sót. |

## Kết luận
- **Tiêu chí bị loại:** `helpful` bị loại vì `κ = 0.375 < 0.6` và `Recall = 0.300 < 0.7` (ma trận nhầm lẫn: `tp=9, fp=0, fn=21, tn=70`). Trong 21 ca bỏ sót (`fn=21`), có **18/21 ca** là lỗi `sai tiền` (reply nói khác ledger) và **3/21 ca** là lỗi `sai xưng hô`. Vì judge chỉ đọc văn bản reply mà không đối chiếu được SQLite ledger, nó dễ bị câu chữ xin lỗi lịch sự đánh lừa (observed fail chỉ `0.09`, trong khi tỷ lệ lỗi thật sau hiệu chỉnh Rogan-Gladen là `0.30`). Kiểm tra đúng số tiền phải làm bằng **code** (`RefundAmountCorrect` + `ReplyMatchesLedger`).
- **Hành động với `tone_ok`:** Có thể dùng hỗ trợ theo dõi văn phong (`κ=0.757, P=0.857, R=0.800`), nhưng cần cập nhật rubric: cấm đại từ suồng sã (`em/nha/bạn`), cấm câu ra lệnh, cấm hứa ngoài hệ thống/emoji/tiếng Việt không dấu; đồng thời cho phép từ `"refund"` và câu trả lời ngắn đủ ý, và rà lại nhãn vàng các ca như `H-081`.
- **Rủi ro còn lại:** Judge chỉ được kiểm trên dữ liệu replay đã công khai (`n=100`); cần thu thập thêm nhãn người độc lập để có tập held-out thật trước khi dùng judge cho dữ liệu sản xuất.
