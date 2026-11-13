# Kết quả chạy thử trên Colab ngày 13 tháng 11 năm 2026

Đã chạy cài đặt, pytest, thu thập dữ liệu, huấn luyện và tạo dashboard trong Google Colab của chủ dự án. Không huấn luyện trên máy tạo repository. Notebook đã được sao chép vào Drive của người dùng.

## Phiên chạy được quan sát

| Thuộc tính | Giá trị |
|---|---|
| Run ID | `20261113T063801Z-b519b17d2a` |
| Python source commit | `914d5a5a2816d9a6f30604eec30f073ee508e935` |
| Dữ liệu | 2.252 trận, 4.504 dòng team-match, 5 giải, mùa 2025/26 và 2026/27 |
| Khoảng kết quả | 15/08/2025 đến 08/11/2026 |
| Validation bắt đầu | 22/03/2026 |
| Test bắt đầu | 23/08/2026 |
| Số trận validation / test | 415 / 473 |
| Mô hình được chọn | Poisson, vượt baseline trên validation log loss |
| SHA256 dữ liệu chuẩn hóa | `b519b17d2aaab5fb42e8dd770d40fbcb3f59c7d001d4fbf62230e1e6b7939ba9` |
| Python / scikit-learn | 3.13.18 / 1.6.1 |
| pandas / NumPy | 2.2.3 / 2.4.6 |
| Số mô phỏng | 5.000 mỗi giải, seed 42 |

## Metrics trên test

| Chỉ số | Mô hình được chọn | Baseline |
|---|---:|---:|
| Log loss | 1.019781 | 1.063673 |
| Multiclass Brier tổng ba lớp | 0.610889 | 0.643252 |
| MAE bàn thắng mỗi đội | 0.995796 | 1.027903 |
| Accuracy thắng–hòa–thua | 48.84% | 45.45% |

MAE phạt góc: 2.118872; MAE cú sút: 4.159212, mỗi chỉ số đo trên 946 dòng team-match có nhãn ở test. Chưa có kiểm định multi-season, khoảng tin cậy thống kê cho mức cải thiện hoặc hiệu chỉnh calibration. Những con số này mô tả một lần đánh giá cụ thể, không chứng minh hiệu quả toàn cầu.

## Kiểm tra đã hoàn tất

- `12 passed in 1.26s` trong Colab: không rò rỉ kết quả tương lai, cùng ngày dùng cùng trạng thái, tổng xác suất/chiều thắng, nhãn âm và trận trùng, budget download, loại dữ liệu cầu thủ tương lai, từ chối thiếu thành viên giải, giữ nhà vô địch mùa đã kết thúc, tính lặp lại và bảo toàn xác suất mô phỏng.
- Hai workbook được tải và cache; lần chạy lại dùng cùng cache. Không có raw data hoặc trọng số được commit lên GitHub public.
- Dữ liệu dùng trong lần chạy: 0 trận trùng, 0 nhãn bàn thắng thiếu sau chuẩn hóa, 100% coverage cặp nhãn góc/cú sút; trận gần nhất cách ngày chạy 5 ngày.
- Browser QA: chọn giải, chọn Arsenal/Man City, đổi sân, màn hình phân phối tỉ số, bảng đua, MLOps scorecard và trạng thái thiếu dữ liệu cầu thủ.
- Dashboard thực tế chứa run ID và source commit ở trên, được mở trong output Colab. Giao diện có CSS đáp ứng; chưa xác nhận bằng browser ở mọi kích thước/thiết bị.
- Model, JSON metrics, model card, snapshot, HTML và environment lock đã được tạo dưới workspace Colab. Trong phiên v0.1 này, Drive chưa bật; phiên v0.2 bên dưới đã chuyển và xác minh lưu Drive.

MLflow, provider StatsBomb và các mô-đun cầu thủ có code nhưng không được chạy với dữ liệu thật trong lần xác nhận này. Chưa có dịch vụ chạy nền, API production, global player coverage, dự báo MOTM/rating/heatmap hoặc engine cúp quốc tế.

## Xác nhận bản v0.2 với Google Drive và ảnh cầu thủ

- Source commit chức năng: `0848f692b039655a91a623ba771065db91d26058`.
- `USE_DRIVE=True`; workspace thực tế `/content/drive/MyDrive/PitchOps/workspace`. Người dùng hoàn tất xác nhận Drive. Đã chuyển 19 tệp từ workspace cũ và kiểm tra SHA256 cho 19 bản sao. Kiểm tra ghi–đọc Drive đạt.
- `31 passed in 1.36s` trong Colab, gồm cả kiểm thử migration, merge quota ledger, chống ghi đè model, image URL allowlist, ghép alias chính xác, ID cầu thủ có namespace, giữ snapshot huấn luyện bất biến và loại huấn luyện viên/nhân viên khỏi danh mục cầu thủ.
- Kết quả đồng bộ: **5 logo giải, 96/96 logo đội trong 5 giải hỗ trợ, 112 hồ sơ cầu thủ, 97 hồ sơ có URL ảnh nguồn**. 149 ảnh trong tập logo/miniface ưu tiên được cache và nhúng; các ảnh khác có thể cần mạng. Danh sách cầu thủ là một phần theo độ phủ/gói API, không phải toàn bộ đội hình.
- View được tạo và lưu riêng trong `artifacts/views`, không huấn luyện lại hoặc sửa trọng số/model snapshot chỉ để cập nhật ảnh.
- Đã mở lại notebook trong phiên Colab mới sau thời gian ngắt. Chạy setup, nối Drive, mở mục 5 bằng `latest_dashboard`; đọc được view đã lưu và kiểm tra ghi–đọc vẫn đạt. Không chạy thu thập, training hoặc đồng bộ API ảnh trong bước khôi phục này.
- Browser QA trên view khôi phục: logo Arsenal/Man City tải được (`naturalWidth > 0`); miniface Bukayo Saka được nhúng và tải được ở độ rộng gốc 200px; tìm Saka, mở hồ sơ đúng ID `thesportsdb:34169884`, bật theo dõi (`aria-pressed=true`); lọc Arsenal + GK trả David Raya. Danh sách Premier League hiển thị 46 hồ sơ trong số 112 hồ sơ toàn danh mục.
- Favorites được kiểm tra trong phiên trình duyệt; chưa cam kết lưu vào Drive. Chưa xác nhận mọi kích thước/thiết bị. Các giới hạn mô hình của v0.1 vẫn áp dụng.
