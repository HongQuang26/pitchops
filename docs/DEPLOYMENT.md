# PitchOps trên Vercel

Vercel phục vụ frontend và backend Node.js 24 trong cùng project. Pipeline Python
vẫn chạy GitHub Actions mỗi **thứ Sáu 14:23**, phục hồi thứ Bảy 14:53 giờ Việt Nam.
Không chạy train trong HTTP request hoặc giữ Colab mở để web hoạt động.

## Luồng dữ liệu

1. Pipeline thu thập theo budget, tạo features, train và kiểm định.
2. Gate đạt: upload `model.enc` và `web.json.gz` vào draft GitHub Release.
3. Chỉ sau khi cả hai upload thành công mới công bố release và cập nhật đồng thời
   `promoted_model`/`promoted_web` trong `automation/state.json`.
4. Backend Vercel đọc registry, kiểm tra repository/URL/hash/kích thước/gate rồi
   nhận projection mới. Không phải deploy lại code để có dự báo mới.
5. Frontend báo khi có phiên bản mới. Các cache có thể làm cập nhật trễ vài phút;
   cron GitHub cũng không bảo đảm chạy đúng từng giây khi dịch vụ bận.

`model.enc` chứa model/cache riêng, chỉ giải mã bằng khóa trên Drive. Projection
web chỉ có dự báo, số liệu tổng hợp và hồ sơ/ảnh công khai; không có workbook thô,
trọng số model, API key, khóa riêng hoặc đường dẫn workspace. Bootstrap có thật
và đã qua gate được đóng gói cùng deploy để web vẫn đọc được khi GitHub tạm lỗi.
Bootstrap không được giả thành phiên train mới; trang hiện ngày dữ liệu thực tế.

Event Lab vẫn là World Cup 2022 replay. Mỗi tuần cập nhật CLB 5 giải; không tự
biến cohort lịch sử thành dữ liệu cầu thủ hiện tại toàn cầu. Artwork giữ credit
và giới hạn độ phủ; ảnh không nhúng trên web để giảm băng thông, có fallback.

## Backend chỉ đọc

| API | Dữ liệu |
|---|---|
| `/api/health`, `/api/status` | Backend, nguồn snapshot, pipeline, tuổi dữ liệu, lịch |
| `/api/bootstrap` | Metadata, metrics, độ phủ, danh mục và danh sách giải |
| `/api/league?league=E0` | Dự báo tất cả cặp đội và cuộc đua của một giải |
| `/api/predict?league=E0&home=Arsenal&away=Chelsea` | Dự báo một cặp đội hợp lệ |
| `/api/players?league=E0&q=Saka` | Danh mục hồ sơ công khai |
| `/api/research?part=overview` | Metadata, cúp, XI, kiểm định replay |
| `/api/research?part=forecasts` | Dự báo sự kiện cho các cặp tuyển |
| `/api/research?part=spatial` | Bản đồ vị trí sự kiện |
| `/api/research?part=players` | Dự báo cầu thủ trong cohort lịch sử |

Chỉ GET/HEAD; không có API công khai để cào, train, ghi registry hoặc upload model.
Không cần database cho dashboard đọc projection. Theo dõi cầu thủ lưu trong
localStorage trên trình duyệt của người xem; chưa có tài khoản hay đồng bộ đa máy.

## Deploy và vận hành

- Import repository `HongQuang26/pitchops` vào đúng workspace Vercel, root repo.
- `vercel.json` dùng `npm run build`, output `public`, API Node trong `api/`.
  Build kiểm tra bootstrap và kích thước từng phản hồi trước khi tạo asset.
- Không cần token GitHub/Google, khóa model hoặc dịch vụ database trong Vercel.
- Git integration deploy code main và preview branch. Commit chỉ đổi registry
  được bỏ qua bằng `ignoreCommand`; backend vẫn nhận registry mới.
- Headers CSP/nosniff và module asset có hash; dữ liệu có CDN cache ngắn. Cache
  trong process chỉ là tối ưu cho instance ấm, không phải persistent storage.
- CI chạy Python contracts, Node API/fallback tests và build. Lỗi gate/upload
  giữ bản đã duyệt; lỗi origin dùng snapshot đã lưu/approved bootstrap.
- Không ghi vào filesystem của Vercel hoặc chạy daemon nền. Durable state nằm
  ở GitHub release/registry; Colab/Drive tiếp tục dùng cho nghiên cứu và backup.

Khi trang có lỗi, kiểm tra `/api/health`, Actions và deployment/runtime logs của
đúng project. Không reset budget nguồn để chữa lỗi deploy. Vercel cần quyền
workspace hợp lệ; cấp quyền kết nối là thao tác do chủ tài khoản xác nhận.
