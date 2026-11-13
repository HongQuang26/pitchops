# PitchOps

**Dự án MLOps bóng đá chạy trên Google Colab, có dự đoán xác suất và dashboard phong cách sân cỏ.** Đây là bản khởi tạo có pipeline thật và kiểm định theo thời gian; không phải hệ thống đã phủ mọi cầu thủ, mọi giải hoặc chạy nền 24/7.

[Mở notebook trên Colab](https://colab.research.google.com/github/HongQuang26/pitchops/blob/main/notebooks/PitchOps_Colab.ipynb) · [Hướng dẫn chi tiết](docs/HUONG_DAN.md) · [Kiến trúc và lộ trình](docs/ARCHITECTURE.md) · [Nguồn và quyền sử dụng](docs/DATA_SOURCES.md)

Đã chạy trên Colab với **2.252 trận**, **12 kiểm thử đạt**, test log loss **1.0198** so với baseline **1.0637** trên **473 trận test**. Xem [biên bản chạy thử và giới hạn](docs/VALIDATION.md).

## Chạy lần đầu

1. Mở notebook trên Colab, chọn **Sao chép vào Drive** để lưu bản của bạn.
2. Chạy các ô từ trên xuống. CPU đủ cho mô hình đầu tiên, không cần bật GPU.
3. `USE_DRIVE=True` là mặc định. Xác nhận Google khi được hỏi; cache, model, ảnh và dashboard tự lưu vào `MyDrive/PitchOps/workspace`. Dữ liệu từ runtime cũ được chuyển kèm kiểm tra hash.
4. Chạy pipeline rồi mở dashboard ngay trong output. Kết quả có thể xuất JSON/CSV hoặc tải HTML để mở ngoại tuyến.
5. Chạy ô kiểm thử. Ô MLflow và dữ liệu cầu thủ là tùy chọn, không cần tài khoản trả phí.

Mọi lệnh cài đặt, kiểm thử, tải dữ liệu và huấn luyện trong hướng dẫn đều chạy trên Colab của bạn. GitHub lưu code và notebook; dữ liệu thô, API key, model và output riêng không được commit.

Bản v0.2 thêm **lưu Drive mặc định, chuyển checkpoint có kiểm tra hash, logo giải/đội, miniface, tìm cầu thủ, lọc đội/vị trí và hồ sơ nguồn**. [Cách lưu và đồng bộ ảnh](docs/MEDIA_AND_DRIVE.md).

## Phạm vi đã triển khai

| Chức năng | Trạng thái | Cách làm |
|---|---|---|
| Pipeline dữ liệu 5 giải lớn | Đã có | Bulk workbook theo mùa, cache có dấu thời gian, kiểm tra schema/nhãn/trùng trận |
| Thắng–hòa–thua, bàn kỳ vọng, phân phối tỉ số | Đã có | Poisson có regularization, rolling 5 trận, sân nhà, danh tính đội/đối thủ/giải |
| Phạt góc, số cú sút | Thử nghiệm | Mô hình Poisson riêng, chỉ học nhãn có dữ liệu, báo MAE test |
| So sánh với baseline | Đã có | Chọn bằng validation log loss, đánh giá lại trên phần test phía sau |
| Cuộc đua vô địch quốc nội | Kịch bản | 5.000 Monte Carlo, điểm/hiệu số/bàn thắng, kiểm tra đủ thành viên |
| Khả năng top 4, nhóm 3 cuối, khoảng điểm | Kịch bản | Chỉ là nhóm thứ hạng, chưa áp dụng mọi luật suất dự cúp/xuống hạng |
| Dashboard | Đã có | HTML có snapshot/ảnh nhúng, logo giải/đội, miniface, tìm/lọc cầu thủ, hồ sơ nguồn, lưới tỉ số, bảng đua, MLOps panel |
| Scorer projection | Mô-đun tùy chọn | Empirical Bayes Poisson từ log cầu thủ; cần phút dự kiến trước trận |
| XI tuần/tháng/năm | Thống kê lịch sử tùy chọn | Có rating/vị trí thì chọn 4-3-3 theo phong độ; chưa là dự báo giải thưởng |
| Heatmap | Adapter tùy chọn | Lấy vị trí sự kiện StatsBomb; chưa là heatmap tracking/dự báo |
| Possession, ném biên, điểm cầu thủ, MOTM | Chưa huấn luyện | Cần nhãn được cấp quyền, nhất quán nhà cung cấp, đội hình dự kiến |
| Cúp quốc tế/vòng loại trực tiếp | Chưa triển khai | Cần engine thể thức, bốc thăm, hai lượt, hiệp phụ/luân lưu |
| Chạy tự động hằng tuần khi Colab đóng | Chưa triển khai | Colab tương tác không bảo đảm dịch vụ luôn chạy |

## Các bảo đảm trong code

- Không dùng kết quả của ngày đang dự báo làm feature. Các trận cùng ngày cùng nhìn một trạng thái lịch sử.
- Chia theo ngày: 60% phát triển, 20% chọn mô hình, 20% test phía sau. Test là đánh giá dự báo cập nhật theo kết quả đã biết ở những ngày trước, không phải dự báo toàn mùa một lần.
- Mô hình triển khai được refit trên toàn bộ dữ liệu có sẵn sau khi đo test. Điểm test không phải đo trên bản refit này.
- Xác suất chưa được calibration sau huấn luyện; dashboard có reliability bins để chẩn đoán. Không gọi mô hình đã được calibrated.
- Không suy diễn dữ liệu thiếu thành 0. Không tạo heatmap, rating hay tên cầu thủ giả.
- Mỗi lần chạy giữ model, metrics, model card, hash dữ liệu, commit code, phiên bản thư viện và `pip freeze`.
- Baseline gate trong mỗi lần chạy; **chưa** có cơ chế champion/challenger giữa nhiều lần chạy production hoặc rollback tự động.
- Kiểm thử tập trung vào leakage, xác suất, nhãn, cache và coverage. Không có scraping vượt đăng nhập/anti-bot.

## Nguồn mặc định

Football-data.co.uk có bulk workbook cho nhiều giải châu Âu. Bản đầu chọn Premier League, La Liga, Bundesliga, Serie A và Ligue 1, mùa 2025/26 và 2026/27. Các cột possession, throw-ins và player logs không có trong hợp đồng này. Không dùng cột odds làm feature.

Nguồn quy định dữ liệu miễn phí dành cho cá nhân/nghiên cứu học thuật và tối đa tải tự động nhẹ hai lần/tuần. Bộ tải chỉ lấy workbook tổng hợp, cache dài cho mùa cũ và có budget toàn host. **Không xóa cache/ledger hoặc chạy nhiều phiên để vượt hạn mức.** Đọc [chính sách nhà cung cấp](https://football-data.co.uk/contact.php) trước khi mở dịch vụ hoặc chia sẻ dữ liệu/model. Code công khai không đồng nghĩa dữ liệu có giấy phép mở. Repository không chứa dữ liệu thô hay model từ nguồn này.

## Cấu trúc

```text
notebooks/PitchOps_Colab.ipynb  Điểm vào chính, toàn bộ thao tác trên Colab
src/pitchops/data.py           Provider, cache, budget và quality gates
src/pitchops/features.py       Feature trước trận theo thời gian
src/pitchops/models.py         Count models, baseline và đánh giá
src/pitchops/simulation.py     Monte Carlo giải vòng tròn hai lượt
src/pitchops/pipeline.py       Điều phối, artifact lineage, MLflow tùy chọn
src/pitchops/dashboard.*       Renderer và giao diện tự chứa
src/pitchops/players.py        Scorer projection và XI lịch sử
src/pitchops/events.py         StatsBomb Open Data adapter
tests/test_contracts.py        Các bất biến quan trọng
docs/                         Hướng dẫn, kiến trúc, giới hạn, lộ trình
```

## Giới hạn cần nhớ

Không có nguồn miễn phí nào đã được xác minh ở đây cung cấp đầy đủ và cập nhật toàn bộ cầu thủ/thể thức của mọi quốc gia. Mô phỏng giữ cố định sức mạnh đội, suy ra các cặp đấu còn lại từ vòng tròn hai lượt và dùng GD/GF, nên là kịch bản xấp xỉ, đặc biệt với giải dùng đối đầu hoặc playoff. Đội mới hoặc ít dữ liệu sẽ có bất định cao hơn. Một lần test tốt không chứng minh có ích cho mọi mùa hoặc mọi giải; cần backtest nhiều mùa, ablation, calibration riêng và giám sát trước production.

Muốn tự động thu thập và dự đoán hằng tuần hoàn toàn không cần mở Colab: cần thống nhất thêm môi trường chạy nền. Bản khởi tạo ưu tiên đúng yêu cầu Colab; không có cron GitHub giả vờ gọi được phiên Colab đang tắt.
