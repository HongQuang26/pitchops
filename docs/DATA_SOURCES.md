# Nguồn dữ liệu và hợp đồng

Đã kiểm tra trang nguồn ngày 13/11/2026. Quyền truy cập, độ phủ và điều khoản có thể thay đổi; kiểm tra lại trước khi vận hành dịch vụ.

| Nguồn | Dùng cho | Giới hạn |
|---|---|---|
| [Football-data.co.uk downloads](https://football-data.co.uk/downloadm.php) | Kết quả, bàn thắng, góc, cú sút của các giải được chọn | Dành cho cá nhân/học thuật theo [fair usage](https://football-data.co.uk/contact.php), tối đa tải tự động nhẹ hai lần/tuần; không phải dữ liệu toàn bộ cầu thủ |
| [Định nghĩa các cột](https://football-data.co.uk/notes.txt) | Schema của workbook | Chỉ dùng thống kê có nhãn thật; không dùng odds/closing odds làm feature |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | Sự kiện, lineup, tọa độ ở giải/mùa được mở | Chọn lọc, không phủ toàn cầu; đọc LICENSE.pdf; công bố phân tích cần credit StatsBomb và logo theo README |
| [football-data.org](https://www.football-data.org/documentation/quickstart) | Provider tiềm năng cho lịch thi đấu/đội hình/competition | Chưa tích hợp trong bản đầu, cần token và kiểm tra gói/độ phủ; không mặc định có throw-ins/heatmap |
| Provider được cấp phép | Lộ trình dữ liệu cầu thủ, rating, MOTM, possession, throw-ins | Chỉ thêm sau khi kiểm tra quyền lưu/training/redistribution và định nghĩa nhãn |

Không dùng FBref/Opta scraping làm phụ thuộc bắt buộc. Không xoay proxy, giả đăng nhập hoặc bypass 403/429. Không có API key nào được nhúng trong notebook hoặc frontend.

## Các lớp dữ liệu

Bronze: response gốc, SHA256, thời gian truy xuất, request ledger. Silver: match rows chuẩn hóa theo league, season, ngày, home, away; giữ missing cho nhãn phụ. Gold: rolling features trước trận và forecasts theo snapshot. Tên đội chỉ là khóa trong provider hiện tại; khi nối nhiều provider cần bảng canonical ID và mapping được xác minh, không fuzzy-join tên rồi coi là chắc chắn.

## Tính sẵn sàng trước trận

Chỉ trận có `date < as_of` được đưa vào training/feature. Nguồn workbook có thể sửa hồi tố: backtest từ file tải hôm nay không tái hiện hoàn hảo dữ liệu từng tồn tại tại thời điểm lịch sử. Cần archived snapshots theo thời điểm phát hành để có backtest point-in-time đầy đủ. Snapshot này ghi thời gian lấy dữ liệu và checksum nhưng chưa có kho lịch sử theo publication-time.

Giờ trận không được dùng trong bản đầu; tất cả trận cùng ngày bị loại khỏi feature của nhau để bảo thủ. Đội hình chính thức công bố sát trận không được dùng khi dự báo một tuần trước trận. Phút thi đấu thực tế của trận mục tiêu không được dùng cho scorer projection.

## Nguồn bổ sung trong v0.3

World Cup 2022 được chọn từ metadata thật của StatsBomb (43/106), 64 trận. Dashboard hiển thị credit và logo StatsBomb lấy từ [kho ảnh công khai chính thức](https://github.com/hudl/public-images). Không commit sự kiện, ảnh hoặc model vào repository này.

[API-Football documentation](https://www.api-football.com/documentation-v3) là hợp đồng của adapter tùy chọn. Coverage khác nhau theo giải/mùa/gói; chưa cung cấp key hoặc mua gói. Không mặc định nguồn có throw-ins, tracking hay official MOTM. Dữ liệu trả về cần canonical mapping/normalization trước khi dùng trong model.
