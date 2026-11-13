# Hướng dẫn chạy và phát triển trên Colab

## Lần đầu

Mở [PitchOps_Colab.ipynb](https://colab.research.google.com/github/HongQuang26/pitchops/blob/main/notebooks/PitchOps_Colab.ipynb), bấm **Sao chép vào Drive**, rồi chạy từng ô bằng nút tam giác. Mỗi ô có mô tả trước lệnh. Dùng CPU; mô hình hiện tại không cần GPU.

Ô setup clone repository về `/content/pitchops`. Đây là code đang chỉnh sửa, khác `/content/pitchops_workspace` là cache và output. Bạn có thể mở thư mục code từ thanh Tệp của Colab hoặc dùng `%%writefile` trong một ô để sửa một module. Notebook được lưu trong Drive, còn `/content` sẽ mất khi runtime bị thu hồi.

`USE_DRIVE=True` đã được bật mặc định; Google có thể yêu cầu bạn tự xác nhận quyền Drive. Workspace được lưu tại `/content/drive/MyDrive/PitchOps/workspace`. Cache/ledger phải được giữ giữa các phiên để tôn trọng quota. Nếu không gắn Drive, hãy tải backup trước khi đóng runtime và khôi phục backup trước khi tải dữ liệu lại. Không chạy nhiều notebook đồng thời trên cùng workspace; cache hiện tại dành cho một pipeline writer.

## Chạy pipeline

`SEASONS=["2526","2627"]` lấy hai workbook, không cào từng đội/cầu thủ. Mặc định học năm giải. Chọn `LEAGUES=["E0"]` nếu muốn thử Premier League trước; cùng workbook đã được cache nên đổi league không cần tải lại.

`AS_OF=None` nghĩa là dùng các trận đã hoàn tất trước ngày hôm nay. Muốn replay một mốc, đặt ví dụ `AS_OF="2026-10-01"`; training và feature sẽ loại mọi trận từ ngày đó trở đi. Các workbook đã được tải hôm nay có thể chứa sửa lỗi hồi tố, nên replay này chưa phải historical publication-time backtest hoàn hảo.

Không có file mẫu giả trong chế độ thật. Nếu nguồn lỗi hoặc schema thay đổi, pipeline dừng với thông báo thay vì tạo kết quả. Có thể tải file thủ công theo điều khoản rồi truyền `local_files={"2526":"/content/your-season.xlsx", ...}`. Không sửa code để quay proxy hoặc bypass anti-bot.

## Đọc dashboard

- **Tổng quan:** số trận, coverage giải, test log loss, kịch bản đua vô địch.
- **Phòng dự đoán:** chọn giải và hai đội khác nhau; đội trái chủ nhà, dùng nút đổi sân để so sánh.
- **Bàn kỳ vọng:** trung bình phân phối số bàn dự báo, khác xG shot-based. 1.4 bàn không có nghĩa trận sẽ kết thúc với 1.4 bàn.
- **Lưới tỉ số:** xác suất từng cặp 0–6; còn xác suất ngoài vùng hiển thị.
- **Cuộc đua vô địch:** mô phỏng cặp đấu còn lại; sức mạnh giữ cố định. P10/P90 là khoảng kết quả theo mô hình, chưa bao gồm toàn bộ bất định do model/data.
- **MLOps:** model được chọn, baseline, log loss/Brier/MAE, reliability, độ phủ và standardized mean shift.
- **Cầu thủ:** giải thích đầu vào cần thêm và trạng thái thật, không hiển thị dự báo giả.

Nhấn xuất JSON hoặc CSV để lấy bảng số liệu. `dashboard.html` tự chứa cả giao diện và snapshot, có thể mở ngoại tuyến; chỉ chia sẻ khi quyền dữ liệu của bạn cho phép. Mặc định không đưa raw data, model hoặc dashboard chứa dữ liệu nguồn lên repo public.

## Sử dụng mô-đun cầu thủ

Nhập CSV có `player_id,player,team,date,minutes,goals`. Trước trận, tự cung cấp dictionary số phút dự kiến `{player_id: minutes}`. Gọi `scorer_projection(logs, as_of, expected_minutes)`. Kết quả là statistical projection có prior shrinkage, có xác suất ghi ≥1 và ≥2 bàn; chưa học injury/appearance/opponent. Không truyền phút thi đấu thực tế của trận cần đoán.

Nếu có thêm `rating,position` (GK/DF/MF/FW), gọi `select_form_xi(logs, as_of, period="week")`, hoặc `month`, `year`. Hàm chọn XI 4-3-3 từ phong độ đã quan sát; chưa dự đoán giải thưởng chính thức hoặc điểm tương lai.

StatsBomb adapter có `competitions()`, `matches(competition_id,season_id)` và `player_locations(match_id,player_id)`. ID phải đến từ provider; không đoán ID hoặc coi mọi giải đều có dữ liệu. Khi công bố phân tích cần tuân thủ license/credit/logo của nguồn.

## Cập nhật code lên GitHub

Ô cuối hỗ trợ commit/push **chỉ code đã chọn**. Thêm secret `GITHUB_TOKEN` trong Colab Secrets và bật quyền truy cập notebook, dùng token fine-grained giới hạn repository `HongQuang26/pitchops` với Contents write. Token chỉ ở bộ nhớ và askpass tạm, không nằm trong remote URL/commit/output. Chỉ dùng ô này khi muốn push thay đổi. Bạn cũng có thể sửa qua GitHub UI và chạy `git pull --ff-only` trong Colab khi working tree sạch.

## Cập nhật tuần sau

Mở lại notebook, nối runtime, restore cùng workspace/cache, kéo code nếu cần rồi chạy pipeline. Snapshot mới có run ID mới; snapshot cũ giữ nguyên. Tự chạy không cần mở Colab sẽ cần môi trường scheduler riêng, chưa cấu hình ở bản này. Không có phiên huấn luyện chạy nền sau khi Colab đã tắt.
