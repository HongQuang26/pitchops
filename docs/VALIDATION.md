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

## Xác nhận v0.3 / Event Lab trên Colab

- Source commit huấn luyện: `9c62cce29cd9dc36bda9d9411d9ad606abdb89ab`. Event run `events-20261113T142018639134Z`.
- Cache đủ 64 trận StatsBomb FIFA World Cup nam 2022. Parser đối chiếu bàn 90 phút với metadata khi không có hiệp phụ, xác nhận winner của mọi trận knockout; tách luân lưu/ET, thay người và vị trí từ sự kiện của chính cầu thủ. Các quality gate đều qua trên dataset thật.
- Cutoff `2022-12-15`: 62 trận, 1.890 dòng player-match, 32 đội, 665 cầu thủ trong nhóm gần nhất. Không dùng hai trận cuối làm training.
- `51 passed in 2.25s` trên Colab: thêm parser 90 phút/ET/penalty/substitution/own goal, vị trí cầu thủ thay người, spatial bounds, hai lượt/knockout conservation/determinism, journal timing/immutability, loại vị trí tương lai, MOTM probability mass, calendar không lộ entrants chưa biết, giữ analytics view khi migration, retry weekly jobs, API budget/cache/key hygiene, CSV IDs, scorer future exclusion.
- Team temporal test từ 06/12/2022, 8 trận / 16 team-match; validation từ 02/12. Test log loss 1,081612, Brier 0,650267. Tập nhỏ, chỉ là nghiên cứu.

| Target | Lựa chọn validation | Test MAE | Baseline MAE |
|---|---|---:|---:|
| Goals | Regularized Poisson | 1,180314 | 1,201389 |
| Corners | Regularized Poisson | 1,693114 | 2,024306 |
| Shots | Regularized Poisson | 3,085539 | 3,396991 |
| Throw-ins | Mean baseline | 4,788194 | 4,788194 |
| Control proxy (0–1) | Ridge | 0,101544 | 0,103859 |

- PI Ridge: MAE **0,249603**, rolling baseline 0,326809, 238 lượt cầu thủ thực tế ra sân; validation interval radius 0,516361, coverage test **92,44%**. Đây là nhãn dự án tự tính, không phải rating chính thức.
- Scorer backtest: 342 ứng viên gồm người không ra sân; coverage appearance thực tế 96,22%; goal-count MAE 0,108025; count NLL 0,243434; scorer Brier 0,043457; appearance Brier 0,160030. Dự báo score rate trung bình 5,49%, quan sát 4,68%. Số bàn bằng 0 chiếm đa số, MAE nhỏ không chứng minh khả năng chọn người ghi bàn chính xác. Chưa có calibration hoặc kiểm định ngoài cohort.
- Spatial: 35.118 sự kiện heldout, NLL **4,040819** so với uniform **4,564348**, grid 12 × 8. Dự báo vị trí sự kiện, không tracking.
- Journal của run: 2 replay sau cutoff, 0 live; replay log loss 1,126476 / Brier 0,682422 / accuracy 50%. Không tuyên bố đây là live forecast đã được tạo trong 2022. Các phiên bản run được chấm riêng.
- Models, source manifest/hash, player logs, model card, requirements lock, metrics, snapshot và HTML lưu tại Drive; kiểm tra ghi–đọc đạt. Không commit các tệp dữ liệu/ảnh/model vào public repo.

### Kiểm tra snapshot đã lưu

12/12 kiểm tra trên dữ liệu thật đã đạt trong Colab: xác suất 992 cặp đấu tổng 1, control share tổng 1, player goal share giữ đúng 10% reserve, spatial density tổng 1, cup title mass, chỉ hai đội final còn xác suất vô địch, XI đủ 11 ID khác nhau, Lisandro Martínez nhận DF từ sự kiện bản thân, journal 2 replay/0 live, đủ model/manifest/card/environment artifacts, model `joblib` đọc lại cho cùng goal means, và analytics view vẫn là latest sau migration. Chạy Event Research lần tiếp theo phục hồi từ Drive, không huấn luyện lại.

Browser QA v0.3: Event Lab hiển thị đúng 62/64 trận, 665 cầu thủ và 1.890 player-match; chuyển tab match/spatial/XI/cup/audit hoạt động; đổi heatmap observed/predicted; XI 4–3–3 có hai trận cuối đủ điều kiện; cup chính thức chỉ Argentina/France còn title probability 51,0%/49,0%, mỗi đội final 100%; nhánh bốn đội giả định được gắn nhãn riêng; audit hiển thị scorer/appearance/spatial test metrics.

## Xác nhận v0.4 / CI/CD ngày 14/11/2026

- [CI run #3](https://github.com/HongQuang26/pitchops/actions/runs/43564002984) thành công trên GitHub-hosted Ubuntu 24.04 / Python 3.13.18: actionlint, notebook/JS/YAML syntax, **64 passed in 5.32s**, build wheel/sdist. Kiểm thử thêm mã hóa/chống sửa gói, archive path traversal, giữ key qua phiên, delivery/cache/ledger merge, rollback khi render/gate lỗi và chặn bộ tải trùng ở Colab.
- [Weekly MLOps verify](https://github.com/HongQuang26/pitchops/actions/runs/43564205103) thành công: cài đặt, test, đọc registry, kiểm tra public recipient và ghi receipt bằng GITHUB_TOKEN giới hạn của job. Đây là **verify**, không ghi nhầm thành train.
- Đã train thật bằng entry point `train_weekly` trong Colab với **cache Drive có sẵn**, có guard chặn mọi HTTP nguồn mới: run `20261114T060129Z-b519b17d2a`, code `314089878418f6bbf0322c5e3af63efd15e84dde`, 2.252 trận. Quality gate đạt; test log loss 1,019781 / baseline 1,063673.
- Đã mã hóa bundle 7.777.555 byte / 11 file gồm model artifacts và cache, kiểm tra recipient/hash/manifest, giải mã và import về Drive; giữ nguyên dữ liệu Event Lab và ảnh. Private key không rời Drive. Đây là kiểm định chuyển giao **cục bộ**, chưa phải release GitHub được phát hành từ một phiên train theo cron.
- Ledger công khai giữ nguyên hai lần tải nguồn đã thực hiện 13/11; không tải thêm để thử lịch. Lần thu thập chính theo lịch tiếp theo là **20/11/2026 lúc 14:23 giờ Việt Nam**. Check phục hồi 14/11 chỉ cần bỏ qua vì đã có lần train hợp lệ gần đây.
- Trạng thái `promoted_model` để trống cho tới khi một phiên GitHub train đạt gate và upload release thật. Source mặc định không trỏ sang artifact giả hoặc model verify. Sau đó Colab tự nhận model/cache qua `AUTO_SYNC_ACTIONS`.
