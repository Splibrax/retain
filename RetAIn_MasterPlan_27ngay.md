# RetAIn — Master Plan 27 ngày (27/8 → 25/9/2026)

> Một kế hoạch duy nhất, thay cho việc rải to-do ở nhiều file. Cập nhật ở đây, đừng cập nhật chỗ khác.
> Quy ước: 🔴 đường găng (trượt = hỏng cả chuỗi) · 🟡 quan trọng · ⚪ tốt-thì-có, cắt được.

---

## 1. THỰC TẾ CẦN NHÌN THẲNG TRƯỚC KHI LẬP KẾ HOẠCH

| Sự thật | Hệ quả lên kế hoạch |
|---|---|
| Còn **27 ngày**, nhưng anh có việc HRBP full-time | Ngân sách thật ≈ **4 tối/tuần × 2h + 4 cuối tuần** ≈ 60–70 giờ. Không phải 27 ngày × 8h. |
| Team 2 người, **0 AI engineer** | Claude Code là người thực thi. Nó chỉ nhanh khi có spec. `BLUEPRINT.md` là khoản đầu tư trả lãi cao nhất đã làm. |
| **2/9 nghỉ lễ Quốc khánh** | Đây là block dài duy nhất trước Build in Public 4/9. Đừng tiêu nó vào việc lặt vặt. |
| Submit **23/9 EOD**, thiếu 1 trong 3 (demo/repo/deck) = **loại** | 23/9 không phải deadline. **20/9 mới là deadline thật** — 3 ngày đệm cho sự cố. |
| Nộp là "demo link chạy được" | Agent **phải deploy**, không được chỉ chạy local. Đây là ràng buộc kỹ thuật nặng nhất. |

### Một câu về chiến lược
Mục tiêu #1 là **Best Pitch**. Nhưng pitch không cứu được demo hỏng — hội đồng sẽ hỏi và sẽ thấy.
Vì vậy: **kỹ thuật đủ dùng, xong sớm; thời gian dôi ra dồn hết vào pitch.**
Đảo thứ tự (làm deck trước, code sau) là cách phổ biến nhất để trượt cả hai.

---

## 2. ĐƯỜNG GĂNG (critical path) — 6 mắt xích

```
🔴 G1. Chốt model ENABLED  →  🔴 G2. resolve_scope + tool chạy local  →  🔴 G3. Agent scaffold + LLM nối được
   →  🔴 G4. Deploy AgentBase ACTIVE  →  🔴 G5. 3 cảnh demo chạy trơn  →  🔴 G6. Submit đủ 3 thứ
```
**Mọi việc khác — deck, animation, số impact, Q&A — chạy SONG SONG và không được chen vào đường găng.**

| Mắt xích | Hạn chót | Nếu trượt thì sao |
|---|---|---|
| G1 Chốt model | **31/8** | Không nối được LLM → mọi thứ phía sau đứng. Hỏi mentor NGAY, đừng chờ 4/9. |
| G2 Tool + scope chạy local | **3/9** | Đến Build in Public tay không, phí buổi có mentor. |
| G3 Agent nối LLM | **6/9** | Dồn toàn bộ rủi ro kỹ thuật vào 2 tuần cuối. |
| G4 Deploy ACTIVE | **13/9** | Nguy hiểm — deploy luôn phát sinh lỗi lạ. Cần ≥10 ngày đệm. |
| G5 Demo trơn | **18/9** | Không kịp quay video dự phòng. |
| G6 Submit | **20/9** (không phải 23/9) | Hết đệm. |

---

## 3. SPRINT 1 — NỀN MÓNG (27/8 → 3/9) · 8 ngày

**Mục tiêu sprint:** đến Build in Public 4/9, anh mang theo **spec + code chạy local**, không phải câu hỏi.

| Ngày | Việc | Ưu tiên | Ai |
|---|---|---|---|
| **T5 27/8** | ✅ `BLUEPRINT.md` xong (đã có). Đọc lại §4.2 — phần AgentBase Policy không làm row-level. | 🔴 | Đức |
| **T6 28/8** | **Nhắn mentor GreenNode 3 câu hỏi** (§7 dưới đây). Push repo lên GitHub private. | 🔴 G1 | Đức |
| **T7 29/8** | Tạo `dim_actor.csv` (6 dòng). Viết `resolve_scope()` + 5 unit test theo BLUEPRINT §7. | 🔴 G2 | Claude Code |
| **CN 30/8** | Viết 5 tool (T1–T5) chạy trên DuckDB local. Test bằng script, chưa cần LLM. | 🔴 G2 | Claude Code |
| **T2 31/8** | **GATE G1** — model đã xác nhận chưa? Chưa thì leo thang (hỏi BTC/Slack chung). | 🔴 | Đức |
| **T3 1/9** | Backtest lift: nhóm High nghỉ gấp mấy lần Low. Ghi lại 1 con số + 1 biểu đồ. | 🟡 | Claude Code |
| **T4 2/9 (lễ)** | **Block dài** — dựng khung agent LangChain, nối tool, test tool-calling bằng LLM bất kỳ (kể cả OpenAI local) để chắc logic đúng. | 🔴 G3 | Claude Code |
| **T5 3/9** | **GATE G2** — chạy 3 cảnh demo bằng CLI, chưa có UI. Chuẩn bị danh sách câu hỏi cho mentor. | 🔴 | Đức |

**Sản phẩm cuối sprint 1:** repo có spec + tool + test pass + backtest number. Đủ để buổi 4/9 là buổi *gỡ vướng*, không phải buổi *bắt đầu*.

---

## 4. SPRINT 2 — LÊN NỀN AGENTBASE (4/9 → 13/9) · 10 ngày

**Mục tiêu sprint:** agent **deploy ACTIVE** và trả lời được 3 cảnh demo.

| Ngày | Việc | Ưu tiên |
|---|---|---|
| **T6 4/9 — Build in Public HN** | Mang spec + code đi. Hỏi mentor đúng 3 việc: (a) model ENABLED, (b) row-level scope — xác nhận cách làm ở §4.2 BLUEPRINT là đúng hướng, (c) cấu hình runtime nhỏ nhất đủ chạy. | 🔴 |
| **T7 5/9 – CN 6/9** | `/agentbase-wizard` full 9 bước. Memory. Env. Test local + Docker. | 🔴 G3 |
| **T2 7/9 – T4 9/9** | Deploy lên AgentBase Runtime. Xử lý lỗi deploy (luôn có). `/health` 200. | 🔴 G4 |
| **T5 10/9** | Cấu hình AgentBase Policy: chặn `dept_risk_summary` với role LM (tuyến 2). Verify bằng test thật. | 🟡 |
| **T6 11/9** | WS#2 HCM (online nếu không đi được). Đo token thật 3 truy vấn mẫu → có số cho slide chi phí. | 🟡 |
| **T7 12/9 ⚠️** | **ĐÓNG ĐĂNG KÝ EOD** — xác nhận cả 2 thành viên **đã tự đăng ký Luma**. Đăng ký hộ = loại đội. | 🔴 **cứng** |
| **CN 13/9** | **GATE G4** — agent ACTIVE, 3 cảnh chạy được qua endpoint thật. | 🔴 |

> **Nếu 13/9 chưa ACTIVE:** dừng mọi việc khác, dồn 100% vào deploy. Deck có thể làm trong 3 ngày; deploy hỏng thì không có gì để nộp.

---

## 5. SPRINT 3 — HOÀN THIỆN & PITCH (14/9 → 20/9) · 7 ngày

**Mục tiêu sprint:** đủ 3 thứ để nộp, nộp sớm 3 ngày.

| Ngày | Việc | Ưu tiên |
|---|---|---|
| **T2 14/9** | Build in Public HCM — nhờ mentor soi lỗ hổng bảo mật & chi phí (2 câu hội đồng sẽ hỏi). | 🟡 |
| **T3 15/9** | Deck v2: dựng lại theo mạch **Hook → Nghịch lý → How it works → Demo → ROI → Rừng di sản**. Nhét 2 sơ đồ (bản sơ đồ workflow đã sửa theo BLUEPRINT §4.3). | 🔴 |
| **T4 16/9** | **3 con số impact** — chốt hoặc bỏ. Có số thật thì điền; không có thì dùng khung công thức + benchmark ngành, **nói rõ là benchmark**. Đừng để trống. | 🟡 |
| **T5 17/9** | Animation "rừng di sản" (MP4 8–12s, nhúng PowerPoint). Nếu quá sức → 3 slide tĩnh chuyển cảnh, vẫn kể được đường cong compounding. | ⚪ |
| **T6 18/9** | **GATE G5** — quay **video demo dự phòng** (bắt buộc, không phải tùy chọn). README repo. Kiểm repo sạch PII. | 🔴 |
| **T7 19/9** | Chạy thử pitch full, bấm giờ ≤5 phút. Roleplay Q&A 4 nhóm với người thứ 2 trong team. | 🔴 |
| **CN 20/9** | **NỘP** — demo link + repo + deck PDF. Xong sớm 3 ngày. | 🔴 G6 |

---

## 6. SPRINT 4 — ĐỆM & LUYỆN (21/9 → 25/9) · 5 ngày

| Ngày | Việc |
|---|---|
| 21–22/9 | Đệm cho bất kỳ thứ gì trượt. Nếu không trượt: luyện pitch, mài Q&A. |
| **T4 23/9** | Deadline BTC — đã nộp từ 20/9, chỉ kiểm lại link còn sống. |
| 24/9 | Chạy pitch lần cuối. Chuẩn bị thiết bị, bản offline của video demo. Xác nhận ai ngồi ghế giám khảo → chọn bản hook đích danh hay chung. |
| **T6 25/9** | **Hackday Hà Nội.** Sáng: pitch track. Chiều: top 10 chung cuộc. |

---

## 7. BA CÂU HỎI PHẢI HỎI MENTOR — GỬI TRONG NGÀY 28/8

Copy nguyên văn, đừng diễn giải lại:

1. **Model:** "Team `msb-team32` hiện có model nào đang `modelStatus = ENABLED` trên MaaS? Tài liệu chỗ ghi GLM-5.2, chỗ ghi Gemma/Qwen/Minimax — em cần chốt để viết code."
2. **Phân quyền:** "Em đọc `agentbase-policy` thì hiểu Policy chỉ gate được `tools/call` theo `principal.*` claim và `context.input.*`, **không làm row-level filter**. Nên em định enforce phạm vi dữ liệu ngay trong code tool (resolve scope từ danh tính đã xác thực, `dept_code` không bao giờ là tham số LLM truyền vào). Cách này có đúng hướng của platform không, hay có cơ chế nào em bỏ sót?"
3. **Runtime:** "Agent của em rất nhẹ (đọc DuckDB đóng gói sẵn trong image, ~30MB data). Cấu hình runtime nhỏ nhất nào đủ chạy, và có giới hạn kích thước image không?"

> Câu 2 là câu **ghi điểm với mentor** — nó cho thấy anh đã đọc tài liệu chứ không hỏi chay. Cũng chính là câu trả lời cho hội đồng sau này.

---

## 8. NHỮNG THỨ TÔI KHUYÊN CẮT (để bảo vệ đường găng)

| Thứ | Vì sao cắt / hạ ưu tiên |
|---|---|
| **Clip TED Dan Pink** | Rủi ro bản quyền + tốn 40s trong pitch 5 phút + phụ thuộc thiết bị BTC. Thay bằng **1 câu quote + hình tĩnh**, giữ nguyên sức mạnh luận điểm. |
| **Tool T5 `risk_trend`** | Nice-to-have. Cắt nếu 6/9 chưa xong G3. |
| **Animation "rừng di sản" dạng video** | Nếu 17/9 chưa xong → 3 slide tĩnh. Ý tưởng mạnh nằm ở *3 nhịp*, không ở kỹ xảo. |
| **Chờ 3 con số impact thật của MSB** | Đừng để nó chặn deck. Dùng **khung công thức AEV + benchmark ngành ghi rõ nguồn**; nếu lấy được số thật thì thay vào sau. Hội đồng chấp nhận benchmark có nguồn hơn là ô trống hoặc số bịa. |
| **Tìm thêm người technical standby** | Tốn thời gian tuyển + onboard nhiều hơn giá trị mang lại trong 4 tuần. Thay bằng **video demo dự phòng** (18/9) — giải quyết đúng nỗi lo "demo hỏng trên sân khấu". |

---

## 9. BẢNG THEO DÕI GATE (in ra, tick tay)

| Gate | Hạn | Xong? | Ghi chú |
|---|---|---|---|
| G1 Model ENABLED xác nhận | 31/8 | ⬜ | |
| G2 resolve_scope + 5 tool chạy local, test pass | 3/9 | ⬜ | |
| G3 Agent nối LLM, tool-calling đúng | 6/9 | ⬜ | |
| **Đăng ký Luma cả 2 người** | **12/9** | ⬜ | **cứng — không đệm** |
| G4 Deploy ACTIVE, /health 200 | 13/9 | ⬜ | |
| G5 3 cảnh demo trơn + video dự phòng | 18/9 | ⬜ | |
| G6 Nộp đủ demo + repo + deck | **20/9** | ⬜ | BTC hạn 23/9 |
| Hackday | 25/9 | ⬜ | |

---

## 10. ĐIỂM CHẾT — 3 thứ duy nhất có thể làm hỏng cả dự án

1. **Không deploy được lên AgentBase.** → Giảm rủi ro: deploy một agent "hello world" **trước 6/9**, trước cả khi logic xong. Biết sớm nó gãy ở đâu.
2. **Quên/lỡ đăng ký Luma trước 12/9 EOD.** → Loại đội, không kháng cáo. Đặt nhắc lịch 10/9 và 12/9.
3. **Demo trên sân khấu hỏng vì mạng/endpoint.** → Video dự phòng quay 18/9, để offline trong máy và trong USB.

Ba thứ này đều **phòng được bằng việc làm sớm**, không phòng được bằng làm kỹ. Đó là lý do kế hoạch này dồn kỹ thuật lên đầu.
