# PitchOps UI v0.5

Dashboard là một tệp HTML tự chứa, sinh từ snapshot đã lưu. Không có framework,
CDN, font ngoài hay dịch vụ UI trả phí. Logo/miniface đã cache được nhúng vào
snapshot; ảnh chưa cache có thể cần mạng và có fallback chữ viết tắt.

## Hướng thiết kế

- Nền giấy ấm `#f3f4ed`, sidebar xanh sân `#102f24`, accent đèn sân `#d6fc51`.
- Sidebar SVG thống nhất, điều hướng ngang trên điện thoại. Trạng thái hiện tại
  thể hiện bằng chữ, `aria-current` hoặc `aria-pressed`, không chỉ bằng màu.
- Nội dung chính đi từ tổng quan → chọn trận → xác suất → giả định. Công thức và
  dấu vết kỹ thuật nằm trong mục giải thích hoặc MLOps.
- Logo giữ tỉ lệ gốc. Chữ hệ thống hỗ trợ tiếng Việt; số liệu dùng độ rộng ổn định.
- Điều khiển chính tối thiểu 44 px, nhãn nhập liệu hiển thị, vòng focus và
  `prefers-reduced-motion`. Bảng rộng chỉ cuộn bên trong vùng bảng.

## Tương tác

- Chọn giải không dựng lại toàn bộ danh mục ảnh. Chọn trận chỉ render vùng trận.
- Tên cầu thủ được chuẩn hóa một lần; tìm kiếm không dấu có debounce 180 ms.
- Bảng đua có tìm đội, sắp xếp xác suất/điểm/tên và trạng thái khi không có kết quả.
- Hồ sơ dùng native dialog, đóng bằng Escape. Tabs Event Lab hỗ trợ trái/phải,
  Home/End, roving tabindex và liên kết đúng panel.
- URL hash lưu màn hình, giải và cặp đấu khi môi trường cho phép history.
  Colab sandbox có thể chặn history/storage; ứng dụng vẫn dùng được.
- Favorites trong iframe Colab chỉ tồn tại trong phiên xem. HTML mở ở trình duyệt
  lưu được localStorage khi trình duyệt cho phép; không nói rằng favorites đã lưu Drive.

## Dữ liệu và độ tin cậy

Event Lab có header/cutoff riêng của World Cup 2022. Không gắn thời gian CLB hiện
tại vào replay. Snapshot, dữ liệu thiếu và mô hình phụ thử nghiệm được ghi rõ.
Bàn kỳ vọng, tổng bàn ≥3 và hai đội cùng ghi bàn có nhãn riêng.

JSON được escape và thay token template một lượt để dữ liệu nguồn không trở thành
mã. Link nguồn chỉ HTTPS với allowlist; CSV bảo vệ tên dạng công thức bảng tính.
HTML/CSS/JS là các asset đóng gói riêng trong Python package để dễ bảo trì.

`refresh_dashboard(WORKSPACE)` chỉ tạo view khi asset UI thay đổi. Tái mở cùng UI
tái dùng view, không nhân bản snapshot/ảnh trong Drive. Chỉ cập nhật pointer sau
khi render và ghi snapshot thành công; model gốc không bị thay đổi.

## Phạm vi rà soát

Kiểm thử Python kiểm tra serialization an toàn, NaN, bảo toàn model/media/research,
render thất bại và tái dùng view. CI kiểm tra cú pháp cả hai JavaScript và build
package. Rà soát trình duyệt tập trung chọn/đổi đội, 49 ô tỉ số, lọc/sắp xếp,
theo dõi/hồ sơ, tabs bàn phím, heatmap, XI, cúp và metrics. Đây không phải chứng
nhận WCAG toàn bộ hay kiểm thử trên mọi thiết bị vật lý.
