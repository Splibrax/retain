# RetAIn — Checklist deploy lên GreenNode AgentBase

> Mở file này bên cạnh khi chạy Claude Code. Wizard sẽ hỏi xác nhận ở gần như mọi bước
> (nó có "HARD GATE", không tự quyết thay). Câu trả lời đã chốt sẵn ở dưới để anh
> không phải vừa chạy vừa nghĩ.

---

## 0. TRƯỚC KHI MỞ CLAUDE CODE (5 phút)

```powershell
cd C:\Users\bviet\Documents\AgentBase\retain
python -m pytest tests\ -q          # phải 31 passed
python check_env.py                 # phải "Đủ để chạy --real"
docker build -t retain .            # phải build sạch
git status                          # phải sạch, đã commit hết
```

Bốn dòng này xanh thì mọi lỗi gặp sau đó chắc chắn là lỗi nền tảng, không phải lỗi code.
Không kiểm trước thì mất thời gian đoán mò giữa chừng.

---

## 1. LỆNH CHẠY

Trong Claude Code, tại thư mục `retain`:

```
/agentbase-deploy
```

Nếu nó bảo cần chạy wizard trước, hoặc anh muốn đi đủ các bước:

```
/agentbase-wizard
```

Wizard có 9 bước và **tự nhận ra bước nào đã xong**, nên không sợ làm lại từ đầu.
Có thể nhảy: `/agentbase-wizard step-6`.

---

## 2. CÂU TRẢ LỜI ĐÃ CHỐT SẴN

| Wizard hỏi | Trả lời | Vì sao |
|---|---|---|
| **Bước 2** — Scaffold project mới? | **Không.** Dùng project đang có | `main.py`, `Dockerfile`, `agent/` đã xong và đã test |
| **Bước 3** — Cần Memory không? | **Không, bỏ qua** | Lịch sử hội thoại đã được truyền qua trường `history` trong body. Thêm Memory lúc này là thêm một thứ có thể hỏng, không đổi lấy gì cho demo |
| **Bước 4** — Cần Identity / outbound auth? | **Không, bỏ qua** | Agent chỉ gọi MaaS bằng API key trong biến môi trường. Runtime tự cấp identity |
| **Bước 5** — Sửa code agent? | **Không** | Code đã chạy thật với GLM-5.2 |
| **Bước 6** — Nhà cung cấp LLM? | **GreenNode AI Platform** | Đang dùng sẵn, key đã có |
| **Bước 6** — Model? | `z-ai/glm-5.2-hackathon` | Đã xác nhận ENABLED và đã chạy thật |
| **Bước 7** — Test local? | **Có** — nhưng đã làm rồi, xác nhận nhanh | Container đã chạy ở máy |
| **Bước 8** — Cấu hình runtime? | **Nhỏ nhất** trong các lựa chọn Recommended | Agent rất nhẹ: đọc CSV, không train, không xử lý ảnh |

---

## 3. ⚠️ BIẾN MÔI TRƯỜNG — CHỖ DỄ HỎNG NHẤT

Runtime phải có đủ **ba** biến (tên nào cũng được, code nhận nhiều biến thể):

```
GREENNODE_BASE_URL   hoặc  LLM_BASE_URL
GREENNODE_API_KEY    hoặc  LLM_API_KEY
GREENNODE_MODEL      hoặc  LLM_MODEL
```

**KHÔNG đặt `RETAIN_MOCK`.** Từ bản này, không đặt gì thì agent chạy **model thật**.

> **Vì sao đổi:** trước đây mặc định là mock. Nếu deploy mà quên đặt biến, agent vẫn
> chạy, vẫn trả lời trôi chảy, `/health` vẫn 200 — nhưng bằng dữ liệu giả lập.
> Không có dấu hiệu nào để nhận ra, kể cả khi đang demo trước hội đồng.
> Giờ thiếu cấu hình thì `/chat` báo lỗi thẳng — ồn ào nhưng an toàn.

---

## 4. KIỂM SAU KHI DEPLOY — theo đúng thứ tự này

```
1. Runtime STATUS = ACTIVE
2. GET  <endpoint>/health   →  200 và  {"status":"ok","mode":"real"}
```

**Nhìn kỹ chữ `"mode":"real"`.** Ra `"mock"` là biến môi trường chưa tới được container —
dừng lại sửa, đừng demo tiếp.

```
3. POST <endpoint>/chat
   Header:  X-Actor-Id: A001
   Body:    {"message": "Team mình tháng này có ai đang có dấu hiệu muốn đi không?"}
   → phải ra 4 người, tổng 147 nhân sự

4. POST <endpoint>/chat
   Header:  X-Actor-Id: A002
   Body:    {"message": "Sao bạn E001881 bên phòng anh Minh lại bị chấm cao thế?"}
   → phải TỪ CHỐI, không lộ tên, không lộ điểm
```

**Bước 4 là bước quan trọng nhất.** Nó chứng minh phân quyền còn nguyên sau khi lên nền tảng —
đúng câu hỏi hội đồng sẽ hỏi. Chạy được bước này thì G4 xanh.

---

## 5. GẶP LỖI THÌ MANG GÌ VỀ

Dán nguyên văn, đừng tóm tắt:

- Thông báo lỗi đầy đủ của wizard
- `runtime.sh get <runtime_id>` → phần `statusReason`
- Log runtime (qua `/agentbase-monitor` hoặc console)
- Bước số mấy đang đứng

Ba loại lỗi hay gặp và ý nghĩa:

| Triệu chứng | Nghĩa là |
|---|---|
| Đẩy image lên registry hỏng | Vấn đề credential container registry — wizard có bước riêng xử lý |
| Runtime ACTIVE nhưng `/health` không trả lời | Container chết sau khi khởi động, xem log |
| `/health` ra `"mode":"mock"` | Biến môi trường chưa tới container |
| `/chat` lỗi 500 | Thiếu cấu hình LLM, hoặc key/model sai |

---

## 6. XONG THÌ GHI LẠI

- `runtime_id`
- URL endpoint
- Cấu hình compute đã chọn
- Có phải đặt thêm biến nào ngoài ba biến trên không

Bốn thứ này cần cho README repo (bài nộp bắt buộc có hướng dẫn truy cập demo),
và cho slide chi phí vận hành.
