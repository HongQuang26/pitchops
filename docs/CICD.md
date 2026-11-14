# CI/CD tự động hằng tuần

Từ v0.4, GitHub Actions chịu trách nhiệm chạy nền. Colab dùng để thử nghiệm, giải mã model mới và mở dashboard. Job GitHub chạy ngay cả khi máy/Colab của bạn tắt. Không cần thủ thuật giữ Colab sống, Google OAuth token trong GitHub hay tạo tài khoản tính phí.

## Lịch và điều kiện chạy

- **Lịch chính: thứ Sáu 14:23 giờ Việt Nam**, tương ứng cron `23 7 * * 5` UTC.
- **Kiểm tra phục hồi: thứ Bảy 14:53**, chỉ chạy khi không có phiên huấn luyện thành công gần đây.
- Push/PR chạy CI: actionlint, kiểm tra cú pháp notebook/JS/YAML, pytest và build package.
- Nút Actions → Weekly MLOps → Run workflow có hai chế độ: `verify` chỉ kiểm tra cấu hình/quyền ghi, `train` thu thập → train → kiểm định → release model.
- Chỉ nhánh `main` của `HongQuang26/pitchops` được chạy job huấn luyện có quyền ghi; các fork không tự thu thập hoặc phát hành. Không chạy mã pull request với quyền ghi/secrets.

GitHub cron có thể trễ hoặc bị gián đoạn khi dịch vụ có sự cố, không có bảo đảm tuyệt đối chạy đúng phút. Repository công khai không có hoạt động 60 ngày có thể bị GitHub tắt lịch. Phiên chạy thật ghi budget và trạng thái vào `automation/state.json`, vừa giữ dấu vết vừa tạo hoạt động có mục đích. Kiểm tra Actions nếu lâu không có model mới; không tạo commit rỗng để giả hoạt động.

## Luồng chạy

1. Checkout code main, cài môi trường và kiểm thử trước khi tải dữ liệu.
2. Tính hai mùa theo ngày thực tế, ví dụ 2026-11 → `2526`, `2627`; không khóa cứng mã mùa cho những năm sau.
3. Đọc ledger dùng chung; ghi nhận **trước** mỗi lần thử HTTP, bằng compare-and-swap SHA của GitHub Contents API. Tối đa hai lần thử tải Football-data trong 7 ngày trượt. Đã nhập ledger từ phiên Colab 13/11/2026 để không đặt lại hạn mức.
4. Tải hai bulk workbook, kiểm tra schema, nhãn, trùng trận; không cào từng đội/cầu thủ hoặc bypass 403/429. Retry phần tính toán tái dùng cache trong cùng job; không dùng retry vô hạn để vượt hạn mức nguồn.
5. Feature theo thời gian, train/validation/test, refit và mô phỏng 5.000 lượt/giải. CPU và BLAS một luồng cho workload bảng nhỏ, tránh oversubscription.
6. Quality gate: metrics hữu hạn, ít nhất 100 trận test, đủ 5 giải/thành viên, xác suất hợp lệ, không thiếu/nhãn trùng, độ mới dữ liệu và test log loss không vượt baseline quá 5%. Đây là ngưỡng triển khai, không chứng minh độ chính xác toàn cầu.
7. Chỉ khi đạt gate: đóng gói model, metrics, dashboard, environment lock và cache nguồn; mã hóa rồi phát hành một GitHub Release bất biến. Lỗi giữ release/model cũ, không trỏ sang model tạo dở.
8. Chỉ receipt và số liệu tổng hợp được để ở Actions artifacts/logs. Không upload raw workbook, model rõ, dữ liệu cầu thủ hoặc khóa riêng vào cache/artifact công khai. Pip cache chỉ chứa dependency công khai.

## Chuyển model về Drive

Model dùng RSA-3072 OAEP để bọc khóa AES-256-GCM ngẫu nhiên. Public key nằm trong `config/artifact-recipient.pem`; private key tại `MyDrive/PitchOps/workspace/.keys/artifact-private.pem`. **Giữ bản sao riêng của thư mục khóa**; mất khóa thì không giải mã được release cũ. Không commit private key hoặc đưa vào GitHub Secrets.

`artifact_sync.sync_and_manage(WORKSPACE)` đọc registry công khai, tải đúng asset `model.enc` trong repository này, kiểm tra SHA256/fingerprint, giải mã và kiểm tra manifest từng tệp. Archive từ chối đường dẫn vượt thư mục, symlink và kích thước quá giới hạn. Model run cũ được giữ; view mới giữ danh mục ảnh và Event Lab lịch sử, có timestamp riêng.

Cache workbook và quota ledger cũng đi trong gói mã hóa. Khi đã dùng CI làm nguồn thu thập, Colab dùng cache đồng bộ và chặn thêm HTTP Football-data để không có hai bộ tải chạy chồng hạn mức. Muốn thử file riêng hãy nhập workbook tải thủ công. StatsBomb/nguồn tùy chọn có chính sách và budget riêng.

**Drive đồng bộ khi bạn chạy/mở notebook**, không có tiến trình GitHub truy cập tài khoản Google. Model đã được phát hành trên GitHub ngay sau job đạt gate; Colab nhận nó khi chạy ô đồng bộ. Nếu GitHub tạm thời không truy cập được, vẫn giữ model/dashboard trên Drive.

## Xem lỗi, thử lại và rollback

- Xem [CI](https://github.com/HongQuang26/pitchops/actions/workflows/ci.yml) và [Weekly MLOps](https://github.com/HongQuang26/pitchops/actions/workflows/weekly.yml).
- `automation/state.json` phân biệt `last_attempt_at`, `last_success_at`, `verification` và `promoted_model`. Verify thành công không được ghi là đã train.
- Không reset `provider_attempts` để retry nguồn. Nếu hai lần thử đã dùng hết, giữ model cũ đến cửa sổ tiếp theo; có thể thử lại tính toán trong job đang còn cache.
- Các release/run cũ không bị xóa tự động. Rollback chọn một receipt/release cũ, xác minh/giải mã trước; không dùng trọng số lạ hoặc joblib từ repository khác.
- `requirements-lock.txt` của từng run ghi môi trường thật. Khi cần nạp lại model Python cho inference/training, dùng môi trường tương ứng; việc xem HTML/JSON không cần unpickle model từ phiên bản khác.

## Phạm vi tự động hóa

Job hằng tuần cập nhật **mô hình CLB ở 5 giải hỗ trợ**. Event Lab World Cup 2022 là cohort nghiên cứu lịch sử được giữ riêng, không giả thành dữ liệu cầu thủ hiện tại hay tự mở rộng toàn thế giới. Nguồn thương mại/API key vẫn cần quyền truy cập và mapping dữ liệu phù hợp.
