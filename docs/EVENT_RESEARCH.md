# Event Research v0.3

Mô-đun mới có dữ liệu, huấn luyện, kiểm định và giao diện thực tế trên Colab. Domain mặc định là **FIFA World Cup nam 2022, StatsBomb competition 43 / season 106**, replay tại đầu ngày **15/12/2022**. Không nối thống kê đội tuyển 2022 vào dự báo CLB 2026.

## Cách chạy

Trong notebook, sau bước lưu Drive và pipeline CLB, chạy phần **Event Research**. Lần đầu tự huấn luyện nếu chưa có research; những lần sau đọc dashboard đã lưu. Đặt `TRAIN_EVENT_RESEARCH=True` khi muốn tạo phiên mới. CPU đủ; cache 64 file sự kiện nằm trên Drive, không tải lại khi còn hạn. Provider giới hạn 80 lần thử tải/tuần trong cache này; giữ ledger, không xóa để vượt giới hạn.

Mở dashboard và chọn **Event Lab**. Có năm mục:

1. **Trước trận:** chọn hai đội tuyển trong cohort, xem bàn/cú sút/góc/ném biên, control proxy, xác suất ghi ≥1/≥2 bàn và bàn kỳ vọng của từng cầu thủ, khoảng PitchOps Index và ứng viên đứng đầu chỉ số.
2. **Heatmap:** đổi đội, cầu thủ, xem số sự kiện đã quan sát hoặc mật độ vị trí sự kiện kế tiếp. Grid 12 × 8 theo tọa độ nguồn 120 × 80. Không phải tracking.
3. **Đội hình:** 4–3–3 theo PI × xác suất ra sân trên lịch tương lai đủ điều kiện ở các cửa sổ 7/30/365 ngày. Lịch ngắn của World Cup khiến ba cửa sổ có thể giống nhau; không phải dự báo toàn bộ năm hoặc giải thưởng chính thức.
4. **Giải cúp:** engine 8 bảng → R16 → QF → SF → Final của World Cup 2022, kết quả trước cutoff được đóng băng. Kịch bản nhánh bốn đội khác hiển thị riêng. API `simulate_knockout` hỗ trợ 2ⁿ đội, một/hai lượt; hai lượt bắt buộc có mean của cặp đảo sân. Không luật bàn thắng sân khách.
5. **Kiểm định:** MAE từng target, baseline gate, kiểm định PI/spatial, journal live/replay và lineage.

## Định nghĩa không được đánh tráo

| Hiển thị | Định nghĩa | Chưa phải |
|---|---|---|
| Control proxy | Tỷ trọng tổng duration các sự kiện Pass/Carry/Dribble, mỗi duration chặn 0–15 giây | Possession chính thức hoặc thời gian kiểm soát đo bằng tracking |
| PI / PitchOps Index v1 | Nhãn do dự án tính từ sự kiện thật | Điểm Opta/SofaScore hoặc rating do StatsBomb cung cấp |
| Ứng viên MOTM | Xác suất có PI mô phỏng cao nhất | Xác suất thắng giải cầu thủ xuất sắc chính thức |
| Heatmap dự báo | Posterior Dirichlet từ vị trí sự kiện cầu thủ + prior vị trí | Bản đồ di chuyển liên tục hoặc mô phỏng chiến thuật tương lai |
| XI 7/30/365 ngày | Tổng PI kỳ vọng có xét ra sân, trên lịch biết được tại cutoff | Toàn bộ lịch chưa biết, giải thưởng của cả năm |
| Replay | Refit trên dữ liệu lịch sử có trước cutoff, dữ liệu được tải hiện tại | Dự báo thực sự đã được công bố trong năm 2022 |

PI có công thức công khai trong `event_data.pitchops_rating`: khởi điểm 6, cộng bàn thắng/kiến tạo/key pass/chuyền thành công/tackle/interception/save, trừ mất bóng/thẻ; một số count chuẩn hóa phút, mẫu phút tối thiểu 20; clip [3,10]. Đây là lựa chọn thiết kế nghiên cứu, cần đánh giá thêm theo vị trí.

## Quy trình mô hình

- Parser phân biệt 90 phút (period 1/2), hiệp phụ, luân lưu; phản lưới tính cho đối phương; phút cầu thủ dựa trên đội hình đầu và thay người/thẻ đỏ, clip 0–90.
- Features theo batch ngày, chỉ nhìn ngày trước. Team và player đều chia ngày 60/20/20. Validation chọn regularized model hoặc baseline; test không dùng để chọn. Sau đo test mới refit trên tất cả dữ liệu trước cutoff.
- Poisson cho goals/corners/shots/throw-ins, Ridge cho control share. Control hai đội được chuẩn hóa về tổng 1. Team goal model báo thêm log loss/Brier trên test.
- PI dùng Ridge theo lịch sử và vị trí hoặc rolling baseline. Khoảng sai số dùng quantile 90% absolute residual validation; báo coverage thực tế trên test, không khẳng định bảo đảm 90% khi distribution thay đổi.
- Khả năng ra sân dùng tần suất Beta-smoothed trong 5 trận gần nhất; phút kỳ vọng là xác suất ra sân × phút trung bình có điều kiện. Chưa có injury/suspension/đội hình xác nhận.
- Goal share dùng xG/90 co rút prior × phút kỳ vọng; phân bổ 90% bàn kỳ vọng đội, giữ 10% cho phần chưa mô hình hóa. Các xác suất ghi bàn trộn trạng thái không ra sân với Poisson có điều kiện. Scorer backtest dùng team mean của model trước test và lịch sử cầu thủ trước từng ngày test, chấm cả trường hợp không ra sân trong nhóm ứng viên gần nhất; báo coverage cầu thủ mới, goal-count NLL/MAE, scorer và appearance Brier. Chưa fit calibration hoặc kiểm định ngoài giải này.
- MOTM-index mô phỏng rating Normal và ra sân độc lập, không mô phỏng tương quan hay giới hạn đúng 11 người. Chỉ dùng như chỉ báo nghiên cứu.
- Spatial validation tách ngày; báo negative log likelihood trên sự kiện heldout và uniform baseline. Không dùng sự kiện sau cutoff để fit.
- Cúp giữ cố định sức mạnh, hiệp phụ rate 1/3, penalty 50/50; tie nhóm tuyệt đối được ngẫu nhiên hóa sau điểm/GD/GF, chưa fair-play. Chỉ hỗ trợ thể thức được khai báo, chưa engine mọi luật FIFA/UEFA hiện hành.

## Artifacts và journal

`data/statsbomb/` giữ response cache, ledger, event manifest SHA256. `artifacts/event_research/runs/<run>/` giữ models, metrics, model card, player logs và snapshot/dashboard; chỉ trên Drive. `artifacts/views/` là dashboard dẫn xuất; `latest_view.json` trỏ view mới. Nâng ảnh không sửa model snapshot hoặc bỏ mất research.

`forecast_store.record_forecasts` ghi tệp dự báo theo fixture/model/as_of/mode, không ghi đè xác suất cùng identity. `evaluate_forecasts` nối kết quả trễ và tách live/replay. Một forecast live tạo sau kickoff bị loại. Journal dựa trên filesystem người dùng có thể sửa, không phải chứng thực timestamp độc lập. Chỉ số replay sau cutoff ở cohort này rất ít trận, không là bằng chứng hiệu năng production. Publication-time của dữ liệu tải hôm nay chưa được tái dựng đầy đủ.

## Mở rộng dữ liệu

`providers.APIFootball` là adapter tùy chọn có cache, daily budget lưu Drive, endpoint allowlist, header key không ghi vào cache, coverage theo league/season và pagination cầu thủ do người dùng chọn. Không mua gói hoặc gọi API khi chưa bật cờ và cấp key trong Colab Secrets. Các response còn ở schema nhà cung cấp; cần mapping ID, chuẩn hóa nhãn và một model run kiểm định riêng trước khi hiển thị trong dashboard hiện tại. Không coi có adapter là đã có dữ liệu toàn cầu. Ảnh giải/đội/cầu thủ tùy nguồn và quyền sử dụng.

`providers.import_player_logs` nhận CSV có ID namespace, date, minutes, goals, rating, rating_source, position; giữ nguồn rating và kiểm tra trùng. Dùng được cho các hàm scorer/XI nhập tay. Không tự fuzzy-join cầu thủ khác nguồn.

`schedule.run_if_due` lưu receipt thành công/lỗi và kiểm tra chu kỳ khi Colab gọi. Lỗi vẫn cho thử lại, thành công chưa đến hạn thì bỏ qua. Colab đóng không có tiến trình chạy. Workspace chỉ có một writer; không phải distributed job lock/queue.

Từ v0.4, mô hình CLB có lịch GitHub Actions chạy độc lập với Colab; Event Lab vẫn là cohort lịch sử được giữ riêng. Xem [CI/CD](CICD.md).
