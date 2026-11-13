# Google Drive logo và miniface

## Lưu tự động

Notebook mặc định `USE_DRIVE=True`. Workspace: `MyDrive/PitchOps/workspace`. Người dùng xác nhận bước cấp quyền Google khi được yêu cầu. Nếu mount lỗi, chương trình dừng; không âm thầm coi `/content` là nơi lưu bền vững.

`migrate_workspace` chuyển cache và artifacts từ workspace tạm cũ sang Drive bằng bản sao đã kiểm tra SHA256. Giữ nguyên nguồn, bỏ qua file giống nhau, giữ cache mới hơn và gộp request ledger để không làm mất quota đã dùng. File model/snapshot có xung đột bị từ chối ghi đè. Giữ một writer cho workspace.

Mọi lần chạy tiếp theo ghi trực tiếp vào workspace Drive. `verify_persistence` kiểm tra ghi và đọc một file thật; `latest_run` tìm artifact theo workspace mới thay vì tin đường dẫn tuyệt đối của runtime cũ.

| Thư mục | Nội dung |
|---|---|
| `data/bronze` | Workbook cache và request ledger |
| `data/silver` | Match history chuẩn hóa |
| `data/media/api` | Metadata logo và cầu thủ, không chứa API key |
| `data/media/images` | Ảnh đã cache và thông tin nguồn/hash |
| `artifacts/runs` | Model và snapshot huấn luyện |
| `artifacts/views` | Các view dashboard có logo/miniface, giữ tách phiên bản khỏi model |
| `artifacts/latest.json` | Run huấn luyện mới nhất |
| `artifacts/latest_view.json` | View ảnh mới nhất của run hiện tại |

## Logo và ảnh cầu thủ

Nguồn chính là [TheSportsDB API](https://www.thesportsdb.com/docs_api_guide). Dùng API key phát triển công khai mặc định, tối đa khoảng 28 requests/phút, cache một tuần; không scraping giao diện web hoặc vượt quota. Metadata giải cache 30 ngày. [Điều khoản nguồn](https://www.thesportsdb.com/docs_terms_of_use.php) cho phép lookup dữ liệu/artwork cho dự án phát triển nhưng không cấp quyền blanket cho mọi ảnh/nhãn hiệu bên thứ ba.

Free API giới hạn số đội/cầu thủ trả về cho mỗi call. Dashboard ghi rõ danh mục một phần, số đội có logo, số hồ sơ và số ảnh. Có thể đồng bộ tối đa 50 đội có ID khớp ở mỗi lần chạy; không đoán ID để tạo cầu thủ hoặc ghép ảnh nhầm người. Key trả phí riêng nếu có được đọc từ Colab Secrets, không lưu trong URL của frontend, catalog hoặc commit.

Logo dự phòng lấy từ [Football Logos by luukhopman](https://github.com/luukhopman/football-logos) qua index GitHub. Chỉ khớp filename/alias chính xác duy nhất; URL được pin theo commit nguồn. Không có ảnh nào được commit vào repository này. Tên gần giống không đủ để coi là cùng một đội.

Miniface ưu tiên `strCutout`, sau đó `strThumb`, sử dụng ID cầu thủ có namespace `thesportsdb:`. Có hồ sơ tên, đội, vị trí, số áo và link/credit nguồn. Không lấy thuộc tính tài chính hoặc thông tin riêng không cần cho dashboard. Không dùng danh mục ảnh làm roster lịch sử hay nhãn training: danh sách có thể thiếu hoặc chưa phản ánh chuyển nhượng.

Logo và 48 ảnh cầu thủ đầu tiên được thử cache/nhúng trực tiếp. Ảnh còn lại tải lười bằng URL có nguồn và cần mạng. Chỉ nhận HTTPS ở allowlist, chấp nhận PNG/JPEG/WebP có kích thước giới hạn; thiếu hoặc tải lỗi sẽ hiện initials. Không tạo khuôn mặt bằng AI.

## Sử dụng

Trong notebook, `SYNC_MEDIA=True` sẽ đồng bộ ảnh sau pipeline. Muốn chỉ cập nhật ảnh/giao diện mà không training: `RETRAIN=False`. Hàm `enrich_dashboard(WORKSPACE)` tạo view mới; không ghi đè snapshot/model của run huấn luyện.

Trong dashboard, chọn giải ở hàng logo, xem logo cạnh hai đội và trong bảng đua. Mục **Cầu thủ & bản đồ** có tìm tên, lọc đội/vị trí, mở hồ sơ và đánh dấu theo dõi. Favorites ở trong bộ nhớ trình duyệt; iframe sandbox có thể chặn localStorage, nên không cam kết favorites đã được lưu vào Drive. Model/cache/ảnh/metrics mới là dữ liệu ghi trực tiếp vào Drive trong phiên Colab.

Các bước này không tạo scheduler chạy khi Colab tắt. Mô hình rating/MOTM, possession/throw-ins, spatial forecast và engine cúp vẫn cần nguồn nhãn và kiểm định riêng.
