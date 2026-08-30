# RetAIn — HRBP Flight Risk Copilot

> **MSB AI Hackathon 2026** · Track *AI FOR MY TEAM* (HR Assistant) · Team RetAIn
> Trợ lý AI giúp HRBP và cán bộ quản lý **phát hiện sớm nhân sự có nguy cơ nghỉ việc**,
> giải thích vì sao, gợi ý hành động, và **thử phương án trước khi trình duyệt**.

---

## ⚠️ Tuyên bố về dữ liệu và dịch vụ bên thứ ba

**Toàn bộ dữ liệu trong `./data/` là dữ liệu GIẢ 100% (synthetic).** Nhân sự, tên, lương, KPI,
thư cảnh cáo đều do script sinh ra, không phải dữ liệu thật của bất kỳ tổ chức nào. Tên phòng ban
bắt nguồn từ cấu trúc tổ chức thật nhưng **đã được ẩn danh hoá cục bộ** (đổi tên, giữ cấu trúc cây)
trước khi đưa vào repo — xem mục *Nguồn gốc dữ liệu*.

**Dịch vụ bên thứ ba:**

| Thành phần | Nhà cung cấp | Vai trò |
|---|---|---|
| `z-ai/glm-5.2-hackathon` | GreenNode MaaS (VNG Cloud) | Diễn đạt kết quả thành ngôn ngữ tự nhiên. **Không tham gia tính điểm** |
| AgentBase Runtime | GreenNode (VNG Cloud) | Nơi agent chạy |
| Container Registry | GreenNode (VNG Cloud) | Lưu Docker image |

Dữ liệu gửi tới model chỉ gồm **điểm số đã tính và lý do dạng chữ**, không gửi bảng dữ liệu thô,
không gửi lương tuyệt đối, không gửi thuộc tính nhân khẩu học.

---

## Truy cập bản demo

**Endpoint:** `https://endpoint-dac848de-1e6b-4cff-8f1e-d0e75f5df717.agentbase-runtime.aiplatform.vngcloud.vn`

Kiểm tra nhanh (mở được bằng trình duyệt):

```
GET /health   →   {"status":"ok","mode":"real"}
```

Hỏi đáp — `POST /chat`, danh tính truyền qua header `X-Actor-Id`:

```bash
curl -X POST "<endpoint>/chat" \
  -H "X-Actor-Id: A001" \
  -H "Content-Type: application/json" \
  -d '{"message": "Team mình tháng này có ai đang có dấu hiệu muốn đi không?"}'
```

### Tài khoản demo

| Actor | Vai | Phạm vi | Thấy gì |
|---|---|---|---|
| `A001` | Line manager | 14 đơn vị · 149 nhân sự | 7 người cần lưu ý, **2 mức Cao** — hai ca đối lập nằm cùng team |
| `A002` | Line manager | 1 đơn vị · 67 nhân sự | 5 người; **không** thấy ai của A001 |
| `A003` | HRBP | 66 đơn vị · 1.127 nhân sự | Toàn khối — 36 người cần lưu ý |
| `A004` | HRBP | 20 đơn vị | Khối còn lại, không có ca nào mức Cao |
| `A005` | Line manager | 1 đơn vị (node lá) | Kiểm tra scope nhỏ nhất |
| `A999` | — | mã không tồn tại | Không thấy gì (kiểm tra fail-closed) |

### Năm tình huống nên thử

```
1. Phát hiện     A001  "Team mình tháng này có ai đang có dấu hiệu muốn đi không?"
2. Giải thích    A001  "Sao bạn E001889 lại bị chấm cao thế?"
3. Thử phương án A001  "Nếu kéo lương bạn ấy về đúng mức thị trường thì rủi ro còn bao nhiêu?"
4. Đòn bẩy khác  A001  "Thế nếu cho bạn ấy đổi vai thì sao?"
5. Chặn          A002  "Sao bạn E001881 bên phòng anh Minh lại bị chấm cao thế?"
```

**Tình huống 3 là điểm đáng xem nhất.** `E001889` đang được trả **cao hơn P50 thị trường 9,3%**,
nên phương án tăng lương về P50 làm điểm rủi ro **không đổi một chút nào** — và hệ thống nói thẳng
điều đó thay vì đưa ra một con số nghe có vẻ hợp lý. Tình huống 4 cho thấy đòn bẩy thật:
đổi vai giảm 24,30 điểm, không tốn ngân sách lương.

Đối chiếu với `E001881` cùng team, cùng mức Cao, nhưng thiếu lương 48%:

```
                        đưa lương về P50      đổi vai / thăng cấp
E001881  67,01 Cao          −36,00                  −3,47
E001889  68,26 Cao            0,00                 −24,30
```

Cùng một quản lý, cùng một mức rủi ro, hai đòn bẩy ngược nhau. Đây là thứ một bảng xếp hạng
không nói được, và là lý do sản phẩm này không thay được bằng một câu SQL.

Tình huống 5 phải bị **từ chối**: không lộ tên, không lộ điểm, không xác nhận người đó tồn tại.

---

## Sản phẩm làm gì

**Detect → Explain → Act → Simulate.**

Trong 1.285 nhân sự đủ điều kiện tại kỳ gần nhất, mô hình thu hẹp còn **42 người cần lưu ý**
(2 mức Cao, 40 mức Trung bình) — **3,3%**. Với một cán bộ quản lý cụ thể thì là 7 người trên 149.
Không phải đọc dashboard, chỉ hỏi một câu.

Điểm rủi ro dựa trên **5 yếu tố có trọng số**:

| Yếu tố | Trọng số | Nguồn |
|---|---|---|
| Khoảng cách lương so với P50 thị trường | 20% | `fact_salary_snapshot` × `dim_market_benchmark` |
| Điểm KPI | 25% | `fact_rm_kpi` |
| Thời gian chưa đổi vai / thăng cấp | 25% | `fact_workforce_snapshot` |
| Thời gian đóng băng lương | 20% | `fact_salary_snapshot` |
| Cửa sổ rủi ro theo thâm niên | 10% | `fact_workforce_snapshot` |

**Hai bất biến của bộ trọng số**, kiểm được bằng máy và có bài test canh riêng:

- Yếu tố nặng nhất là 25, hai yếu tố nặng nhất cộng lại là 50 — **đều dưới ngưỡng mức Cao (66)**.
  Không yếu tố đơn lẻ nào, không cặp nào, đủ để gắn cờ một người. Phải có **ít nhất ba yếu tố cùng xấu**.
- Người **không thiếu lương** vẫn phải lên được mức Cao. Bản trước đặt lương 40% khiến điều này
  bất khả thi về số học (trần 60 < 66) — "mức Cao" khi đó chỉ là cách gọi khác của "thiếu lương nặng".
  Số đo: trước 0 người bằng/trên P50 bị gắn cờ, nay **5 người**, trong đó 1 ở mức Cao.

Luận giải đầy đủ từng trọng số, kèm các yếu tố đã cân nhắc rồi loại: [`TRONG_SO.md`](TRONG_SO.md).

**Quy tắc loại trừ cứng:** nhân sự có ≥2 thư cảnh cáo trong 12 tháng bị loại khỏi danh sách
giữ chân, bất kể điểm cao thế nào.

Thiếu dữ liệu ở một yếu tố thì engine **chuẩn hoá lại trọng số** trên các yếu tố còn lại,
thay vì coi thiếu = 0 điểm.

---

## Kiến trúc và ba nguyên tắc

```
Người hỏi → xác thực danh tính → resolve phạm vi dữ liệu → [LLM chọn tool]
          → tool chạy truy vấn ĐÃ LỌC → LLM diễn đạt → hậu kiểm số → audit log → trả lời
```

**1. Agent đọc điểm đã tính, không tự tính.**
`flight_risk_score.py` chạy độc lập, deterministic, có kiểm thử. LLM chỉ đọc kết quả.
Tính điểm phải kiểm toán được — chạy lại phải ra đúng số cũ.

Trọng số và công thức nằm ở **đúng một chỗ**: `agent/scoring.py`. Cả engine chấm điểm, bộ sinh
dữ liệu lẫn agent đều import từ đó, và có bài test canh việc chúng dùng **cùng một object** chứ
không phải hai bản giống nhau. Hiệu chỉnh mô hình là sửa một dòng, không phải sửa agent.

**2. Phân quyền nằm ở tầng dữ liệu, không ở lời dặn LLM.**
Schema tool đưa cho LLM **không có tham số phạm vi** — nó không có ô nào để đòi dữ liệu đơn vị khác.
Phạm vi được suy ra từ danh tính đã xác thực **trước khi LLM tham gia**. Không lách được bằng cách hỏi khéo.

**3. Mọi con số trong câu trả lời phải truy được về kết quả tool.**
Lớp `guard` soi từng số; không khớp thì bắt viết lại, vẫn sai thì trả bản dựng máy móc từ dữ liệu gốc.
Câu bịa không bao giờ ra tới người dùng.

**Cột không bao giờ rời tầng dữ liệu:** giới tính, tình trạng hôn nhân, học vấn, lương tuyệt đối.
Mô hình không có khả năng kỹ thuật để suy luận trên chúng.

---

## Hai kênh, một lõi

Chatbot là mô hình **kéo**: người dùng phải nhớ ra là có nó, mở ra, nghĩ câu hỏi. Cán bộ quản lý
trực tiếp có động lực làm việc đó — họ hỏi về người của chính mình. Lãnh đạo cấp khối thì không.
Muốn chạm tới tầng đó, thông tin phải **tự tìm đến họ**, ở nơi họ vốn đã đọc.

| Kênh | Cho ai | Hình thức |
|---|---|---|
| Hỏi đáp `POST /chat` | Cán bộ quản lý, HRBP | Kéo — hỏi về người cụ thể, thử phương án |
| Bản tin định kỳ `send_digest.py` | Lãnh đạo cấp khối | Đẩy — email hàng kỳ, số tổng hợp cấp đơn vị |

Ba ràng buộc của bản tin, cố ý:

1. **Không nêu tên ai.** Email bị chuyển tiếp, in ra, chiếu lên màn hình họp. Bản tin chỉ có số
   tổng hợp cấp đơn vị. Muốn biết ai thì mở RetAIn — ở đó phạm vi bị giới hạn theo tài khoản
   và mọi truy vấn đều được ghi nhật ký.
2. **Đi qua đúng `resolve_scope()` như kênh chat.** Đổi kênh không được phép đổi quyền. Có bài
   kiểm thử canh riêng việc này: không đơn vị nào lọt vào bản tin mà nằm ngoài phạm vi.
3. **Toàn bộ số tính tại chỗ, 0 token.** Model chỉ được mời viết một đoạn nhận xét 2–3 câu,
   và đoạn đó vẫn phải qua `guard` như mọi câu trả lời khác. Guard trượt thì **bỏ hẳn đoạn văn**,
   bản tin vẫn đầy đủ số liệu. Thà cụt còn hơn sai.

```bash
python send_digest.py --actor A003                 # xuất HTML, mở bằng trình duyệt
python send_digest.py --all --out out/             # dựng cho mọi tài khoản
python send_digest.py --actor A003 --narrative     # kèm đoạn nhận xét do model viết
python send_digest.py --actor A003 --send hrbp@example.com   # gửi thật, cần SMTP_*
```

Xem trước ngay trên trình duyệt, không cần hộp thư: `GET <endpoint>/digest?actor=A003`

Về việc **tích hợp vào Teams hay cổng nội bộ**: lõi `agent/` không biết HTTP là gì — nó nhận
(danh tính, câu hỏi) và trả (câu trả lời, metadata). Web, email, Teams đều chỉ là lớp vỏ.
Bản dự thi cố ý dừng ở web và email vì hai kênh này không phụ thuộc phê duyệt hạ tầng nội bộ,
còn Teams thì có — đó là ràng buộc tổ chức, không phải ràng buộc kỹ thuật.

---

## Cấu trúc thư mục

- **`agent/`** — `scope.py` (phân quyền) · `store.py` (đọc dữ liệu) · `tools.py` (4 tool) ·
  `scoring.py` (**trọng số — nguồn sự thật duy nhất**) · `registry.py` (khai báo tool cho LLM) ·
  `prompt.py` · `guard.py` (hậu kiểm) · `llm.py` · `runtime.py` ·
  `digest.py` + `digest_email.py` (bản tin định kỳ)
- **`tests/`** — 58 bài kiểm thử, gồm bộ canh lỗ hổng phân quyền ở **cả hai kênh**
- **`data/`** — dữ liệu synthetic + `dim_actor.csv` (tài khoản demo) + `playbook.csv` (P1/P2/P3)
- **`_private/`** — dữ liệu tổ chức thật, **bị `.gitignore` chặn hoàn toàn, không bao giờ commit**
- `main.py` · `Dockerfile` · `run_local.py` · `demo_smoke.py` · `check_env.py`
- `BLUEPRINT.md` — spec kỹ thuật · `TRONG_SO.md` — luận giải trọng số · `DEPLOY_CHECKLIST.md` — quy trình deploy · `demo_numbers.py` — in số liệu cho demo

---

## Chạy tại máy

```bash
pip install -r requirements.txt

python -m pytest tests/ -q     # 58 passed
python demo_smoke.py           # 4 cảnh demo, không cần LLM
python run_local.py --scenario # chạy qua cả đường ống, dùng MockLLM
```

`MockLLM` giả lập model để kiểm đường ống, phân quyền và guard **mà không cần mạng, không tốn token**.

Chạy với model thật — tạo `.env` (đã bị `.gitignore` chặn):

```
GREENNODE_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
GREENNODE_MODEL=z-ai/glm-5.2-hackathon
LLM_API_KEY=<khoá MaaS>
```

```bash
python check_env.py            # kiểm cấu hình, chỉ in TÊN biến, không in giá trị
python run_local.py --real --scenario
```

Chạy bằng Docker:

```bash
docker build -t retain .
docker run -d -p 8080:8080 --env-file .env retain
```

---

## Chi phí vận hành

| Thành phần | Chi phí |
|---|---|
| Chấm điểm hàng loạt | **0 token** — chạy local bằng Python/SQL, không gọi LLM |
| Truy vấn một tool (liệt kê, giải thích) | **~4.600 token** (≈4.100 vào + 500 ra) |
| Truy vấn hai tool (mô phỏng rồi giải thích) | **~7.000 token** (6.379 vào + 669 ra) — đo trên bản đang chạy |
| Guard bắt viết lại | cộng thêm ~2.500 token cho lượt viết lại |
| Bản tin định kỳ | **0 token** cho toàn bộ số liệu; ~1.200 token nếu bật đoạn nhận xét, 1 lần/người/kỳ |

Con số hai tool cao gấp rưỡi vì kết quả tool đi vào prompt hai lần. Agent **tự quyết** gọi thêm tool
thứ hai khi câu trả lời đầu chưa đủ dùng — ví dụ mô phỏng cho ra "không thay đổi" thì nó tự giải
thích tiếp yếu tố nào mới đang gây rủi ro. Đắt hơn, và đáng.
| Hạ tầng | `runtime-s2-general-2x4` (2 CPU / 4 GB), min=max=1 bản chạy |

Agent **không nhồi bảng dữ liệu vào prompt** — nó đọc điểm đã tính và chỉ gửi phần tối thiểu.
Vừa rẻ token vừa đúng nguyên tắc bảo mật.

---

## Khác biệt giữa bản demo và bản triển khai thật

Nêu rõ để không ai hiểu nhầm phạm vi của bản dự thi:

| | Bản demo | Bản triển khai thật |
|---|---|---|
| Danh tính | Header `X-Actor-Id` (tự khai) | Claim trong JWT do gateway xác thực — **đổi một hàm ở entrypoint** |
| Dữ liệu | Synthetic, đóng gói trong image | Kết nối HRIS thật qua ETL định kỳ |
| Quyền hạ tầng | `FullAccess` cho tiện phát triển | Siết theo nguyên tắc quyền tối thiểu |
| Độ chính xác dự báo | **Chưa kiểm chứng** — POC chứng minh *cơ chế* và *tính giải thích được* | Cần backtest trên dữ liệu thật khi pilot |

Điểm cuối là điều quan trọng nhất: trên dữ liệu giả, cái được chứng minh là **cơ chế đúng và
giải thích được**, không phải độ chính xác dự báo. Nói thẳng còn hơn phóng đại.

---

## Nguồn gốc dữ liệu

Các bảng dim (`dim_department`, `dim_dept_hierarchy`, `dim_job`, `dim_position`…) bắt nguồn từ
dữ liệu tổ chức thật, được **ẩn danh hoá cục bộ** — đổi tên đơn vị/phòng ban, giữ nguyên cấu trúc
cây và định dạng mã — trước khi đưa vào `./data/`. Bảng map tên thật ↔ tên giả nằm trong `_private/`
và không bao giờ rời khỏi máy.

Toàn bộ nhân sự, lương, KPI, termination, thư cảnh cáo là dữ liệu **sinh mới hoàn toàn**,
không truy xuất từ bất kỳ hệ thống hay cá nhân thật nào.

Tái sinh dữ liệu (không cần thiết, bộ hiện có đã đạt):

```bash
python generate_facts.py       # sinh dim_employee + toàn bộ fact_*
python flight_risk_score.py    # tính điểm, ghi fact_flight_risk_score.csv
```

Cả hai script đặt random seed cố định (42) để kết quả tái lập được.
