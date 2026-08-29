# RetAIn — BLUEPRINT (Spec Kit v1.0)

> **Đây là hợp đồng kỹ thuật của agent RetAIn.** Viết TRƯỚC khi code.
> Mọi quyết định trong file này đã được kiểm chứng với: `flight_risk_score.py`, dữ liệu thực tế trong `./data/`,
> và SKILL.md của `agentbase-policy` / `agentbase-identity` / `agentbase-wizard`.
> Chỗ nào là **giả định chưa verify** đều được đánh dấu `⚠️ ASSUMPTION`.
>
> Ngày lập: 27/08/2026 · Chủ dự án: Đức (Team Lead / Product Owner) · Cuộc thi: MSB AI Hackathon 2026, track AI FOR MY TEAM
> Cách dùng: mở file này trước mỗi phiên Claude Code. Nó là nguồn sự thật; code phải khớp spec, không phải ngược lại.

---

## 0. TÓM TẮT MỘT ĐOẠN (đọc cái này nếu chỉ có 30 giây)

RetAIn là **agent hội thoại Kiểu 2 (multi-step)** cho HRBP và line manager, chạy trên GreenNode AgentBase.
Nó **không tính điểm** — engine `flight_risk_score.py` đã tính sẵn và ghi vào `fact_flight_risk_score`.
Agent làm 3 việc: **Detect** (ai đang rủi ro trong phạm vi của người hỏi) → **Explain** (vì sao, theo 4 yếu tố có trọng số)
→ **Act** (gợi ý P1/P2/P3). Ranh giới sống còn: **phạm vi dữ liệu do danh tính người hỏi quyết định, không phải câu hỏi**,
và **LLM chỉ diễn đạt số đã có, không được sinh số**.

---

## 1. MỤC ĐÍCH

### 1.1 Bài toán
Line manager và HRBP hiện chỉ biết một nhân sự sắp nghỉ **khi đơn đã trên bàn**. Lúc đó phương án duy nhất còn lại là
counter-offer ad-hoc — đắt, muộn, và tỷ lệ giữ được thấp. Dữ liệu để biết sớm hơn thì đã nằm sẵn trong HRIS
(lương, KPI, thâm niên, lịch sử điều chỉnh) nhưng không ai đọc nổi 1.285 dòng snapshot mỗi tháng.

### 1.2 Việc RetAIn phải làm được
| # | Job-to-be-done | Câu hỏi thật của người dùng |
|---|---|---|
| J1 | Thu hẹp 1.285 người → danh sách cần để mắt | "Team tôi ai đang rủi ro nghỉ?" |
| J2 | Hiểu vì sao, đủ để tranh luận được | "Vì sao bạn này bị chấm cao?" |
| J3 | Biết làm gì tiếp theo | "Tôi nên làm gì với bạn này?" |
| J4 | Nhìn bức tranh đơn vị, không chỉ từng ca | "Cả phòng tôi tình hình thế nào?" |

### 1.3 Thành công trông như thế nào (V1)
- Một line manager hỏi bằng tiếng Việt tự nhiên → nhận đúng danh sách **trong phạm vi của mình**, kèm lý do truy vết được.
- Cùng câu hỏi đó, hỏi về người **ngoài phạm vi** → agent từ chối, và từ chối vì **dữ liệu không tới tay nó**, không phải vì LLM ngoan.
- Mọi con số trong câu trả lời đều tra ngược được về một dòng trong `fact_flight_risk_score`.

### 1.4 Nguyên tắc bất biến (không được vi phạm dù đánh đổi gì)
1. **Agent đọc điểm đã tính. Không tự tính, không nội suy, không ước lượng.**
2. **Phân quyền nằm ở tầng dữ liệu, không ở prompt.** Prompt guard có thể lách; data filter thì không.
3. **100% synthetic data.** Dữ liệu thật không bao giờ rời `_private/`.
4. **Không suy luận trên thuộc tính được bảo vệ** (giới tính, tình trạng hôn nhân, học vấn) — xem §5.3.
5. **Trung thực về giới hạn.** POC trên synthetic chứng minh *cơ chế*; predictive validity validate khi pilot.

---

## 2. NGƯỜI DÙNG & MÔ HÌNH PHẠM VI

### 2.1 Hai persona
| Persona | Phạm vi thấy được | Tool được gọi | Ví dụ |
|---|---|---|---|
| **Line Manager (LM)** | Đúng nhánh tổ chức mình quản lý (1 node + toàn bộ cây con) | `list_team_risk`, `explain_employee_risk`, `suggest_actions` | GĐ Phòng TTKD Miền Bắc |
| **HRBP** | Toàn khối được phân công (node cấp cao hơn + cây con) | Toàn bộ, thêm `dept_risk_summary` | HRBP Khối EB |

### 2.2 Danh tính đến từ đâu
| Môi trường | Nguồn danh tính |
|---|---|
| **Production (tương lai)** | JWT từ SSO của ngân hàng → claim `sub`, `role`, `dept_scope`. Gateway xác thực trước khi request chạm agent. |
| **Demo Hackathon (V1)** | Bảng `dim_actor` (synthetic) + header `X-Actor-Id`. Runtime resolve actor → `(role, dept_scope)` **một lần, ở entrypoint**, trước khi LLM nhìn thấy bất cứ thứ gì. |

> **Nói thẳng cái này trong pitch, đừng giấu:** demo dùng actor giả lập vì không đấu SSO trong 4 tuần.
> Cái được chứng minh là **cơ chế** — scope được resolve từ danh tính đã xác thực, không phải từ câu hỏi.
> Thay `X-Actor-Id` bằng JWT claim là đổi 1 hàm, không đổi kiến trúc.

### 2.3 Bảng `dim_actor` (tạo mới cho demo — 6 dòng là đủ)
```
actor_id, actor_name, role,  dept_scope_code, note
A001,     Nguyễn Văn A, LM,   01CN000015,      GĐ Phòng TTKD Miền Bắc — dùng cho demo scene 1
A002,     Trần Thị B,   LM,   01CN000057,      GĐ đơn vị khác — dùng cho demo scene 3 (từ chối chéo)
A003,     Đức,          HRBP, 01CN000025,      HRBP Khối — thấy toàn khối
A004,     Lê Văn C,     HRBP, 01CN000xxx,      HRBP khối còn lại
```

---

## 3. SCOPE — LÀM GÌ / KHÔNG LÀM GÌ

### 3.1 IN SCOPE (V1 — phải chạy được ngày 23/9)
- ✅ Hội thoại tiếng Việt, 4 intent (J1–J4).
- ✅ Lọc dữ liệu theo scope người hỏi, ở tầng SQL.
- ✅ Giải thích điểm theo 4 yếu tố + trọng số **thực dùng** (`weight_*_used`) + `missing_features`.
- ✅ Áp quy tắc loại trừ cứng (≥2 cảnh cáo/12 tháng).
- ✅ Gợi ý hành động P1/P2/P3 theo playbook cố định.
- ✅ Audit log mọi truy vấn.
- ✅ Kịch bản từ chối khi hỏi ngoài phạm vi.

### 3.2 OUT OF SCOPE (V1 — nói "không" dứt khoát để khỏi trôi)
- ❌ **Multi-agent.** Kiểu 2 multi-step là đủ; multi-agent là over-engineer, sẽ bị hỏi "vì sao cần" mà không trả lời được.
- ❌ **Ghi ngược vào HRIS.** Agent chỉ đọc. Không tạo đề xuất tăng lương, không cập nhật hồ sơ.
- ❌ **Train/retrain model trong agent.** Trọng số là expert-set, cố định trong V1.
- ❌ **Kết nối HRIS thật.** Demo chạy trên DuckDB synthetic đóng gói trong image.
- ❌ **Dự báo cấp tổ chức / mô phỏng chính sách.** Để roadmap.
- ❌ **Giọng nói, mobile app, tích hợp Teams/Zalo.** Web chat là đủ cho demo.

### 3.3 Ranh giới "gần nhưng không làm" — chuẩn bị câu trả lời
> "Sao không cho agent tự tính điểm luôn?" → Vì tính điểm là logic kiểm toán được, phải chạy deterministic, có test,
> có version. Để LLM tính là mất khả năng giải trình — thứ duy nhất khiến mô hình chấm điểm con người được chấp nhận trong ngân hàng.

---

## 4. KIẾN TRÚC V1 (đã chốt)

### 4.1 Lựa chọn nền tảng
| Quyết định | Chọn | Vì sao |
|---|---|---|
| Đường triển khai AgentBase | **Custom Agent** (Docker → `/agent-runtimes`) | Cần code truy vấn dữ liệu riêng. OpenClaw là chatbot template, không nhét được tool SQL. |
| Framework | **LangChain + Memory** | Wizard khuyến nghị; tool-calling sẵn; Memory cho ngữ cảnh hội thoại nhiều lượt. |
| LLM | **GLM-5.2 qua GreenNode MaaS** | ⚠️ ASSUMPTION — phải xác nhận `modelStatus = ENABLED` với mentor (§15). |
| Kho dữ liệu | **DuckDB file, read-only, đóng gói trong image** | Không hạ tầng thêm, không network egress, deploy 1 bước. Đúng tinh thần "deploy sớm". |
| Memory | AgentBase Memory (short-term checkpointer) | Để hỏi tiếp "còn bạn thứ 2 thì sao" mà không phải nhắc lại tên. |

### 4.2 ⚠️ PHÁT HIỆN QUAN TRỌNG — AgentBase Policy KHÔNG làm row-level filtering

Đã đọc `agentbase-policy/SKILL.md`. Sự thật:
- Resource type duy nhất được bảo vệ hôm nay là **`gateway`** (Resource Gateway / MCP).
- Condition chỉ có **9 toán tử**, và key chỉ gồm `context.ip`, `context.input.<name>` (một trường trong `params.arguments`),
  `principal.<name>` (claim JWT).
- Toán tử so sánh key với **một giá trị hằng viết cứng trong policy**. **Không có cách nào viết "dept_code phải nằm trong cây con của người hỏi"**.
- Quota: 20 policy group/user, 10 policy/group → không thể viết 1 policy cho mỗi đơn vị.

**Hệ quả:** sơ đồ workflow hiện tại (bước 2–3 "xác thực + lọc theo quyền") **đang ngầm giả định AgentBase làm việc đó. Nó không làm.**
Nếu để nguyên và bị hội đồng hỏi kỹ, đây là chỗ vỡ.

**Cách sửa — 4 tuyến phòng thủ, mỗi tuyến nói rõ ai thực thi:**

| Tuyến | Thực thi ở đâu | Chặn được gì |
|---|---|---|
| **1. Xác thực danh tính** | Gateway inbound auth (JWT) / demo: entrypoint resolve `X-Actor-Id` | Người hỏi không tự khai mình là ai |
| **2. Policy theo vai trò** | AgentBase Policy trên gateway — `allow`/`deny` theo `principal.role` cho từng tool | LM không gọi được `dept_risk_summary`; principal bị treo không gọi được gì |
| **3. Scope resolution trong code tool** ← **tuyến chính** | Hàm `resolve_scope(actor)` trong agent, build mệnh đề `WHERE dept_code IN (...)` | Rò rỉ chéo đơn vị. `dept_code` **không bao giờ là tham số do LLM truyền vào** |
| **4. Audit log** | Bảng `audit_query_log` | Truy vết sau sự cố |

> **Câu chốt cho pitch (thay câu cũ):**
> *"Phân quyền không nằm ở lời dặn LLM, cũng không phó mặc cho platform. Danh tính được xác thực ở gateway;
> phạm vi dữ liệu được suy ra từ danh tính đó **trong code**, rồi mới dựng câu SQL. LLM nhận về một tập dữ liệu đã bị cắt sẵn —
> nó không có gì để rò rỉ, kể cả khi bị hỏi khéo."*

### 4.3 Luồng một truy vấn (bản đã sửa — thay bản trong `RetAIn_Architecture_Flow.md`)
```
1. Người hỏi gửi câu hỏi  ──►  Gateway: xác thực → principal {id, role, dept_scope}
2. Policy check (AgentBase): principal này được gọi tool nào?          [tuyến 2]
3. Agent runtime: resolve_scope(principal) → danh sách dept_code       [tuyến 3] ★ LLM CHƯA THAM GIA
4. LLM (GLM) đọc câu hỏi → chọn tool + tham số (KHÔNG có dept_code)
5. Tool chạy SQL trên DuckDB, WHERE dept_code IN (<scope đã resolve ở bước 3>)
6. Áp exclusion rule (≥2 cảnh cáo) + cắt cột theo whitelist (§5.2)
7. Trả tối đa N dòng, cột tối thiểu, cho LLM diễn đạt
8. Kiểm tra hậu kiểm: mọi số trong output có mặt trong tool result?    [§8.R6]
9. Ghi audit log → trả lời người dùng
```
**Điểm mấu chốt:** bước 3 xảy ra **trước** bước 4. LLM không bao giờ được cầm quyền quyết định phạm vi.

---

## 5. CONTRACT DỮ LIỆU

### 5.1 Bảng agent được đọc
| Bảng | Dùng để | Ghi chú thực tế đã kiểm |
|---|---|---|
| `fact_flight_risk_score` | Nguồn sự thật duy nhất về điểm | 52.698 dòng, 60 tháng, **snapshot là ngày ĐẦU tháng** (`2021-01-01` → `2025-12-01`) |
| `dim_employee` | Tên, đơn vị hiện tại | ⚠️ có cột nhạy cảm — xem §5.3 |
| `dim_dept_hierarchy` | Resolve scope | 78 dòng, 5 cấp: `lvl1..lvl4_code` + `lowest_code` |
| `dim_actor` | Danh tính demo | Tạo mới, ~6 dòng |
| `fact_termination` | Backtest lift (offline, không phải tool) | Không expose qua agent ở V1 |

### 5.2 WHITELIST cột được đưa vào prompt LLM
Chỉ đúng những cột này, không hơn:
```
employee_id, full_name, dept_code, dept_name, band, tenure_months,
flight_risk_score, flight_risk_band, snapshot_date,
risk_component_salary, risk_component_kpi, risk_component_freeze, risk_component_seniority,
weight_salary_used, weight_kpi_used, weight_freeze_used, weight_seniority_used,
missing_features, is_excluded_from_risk_list, exclusion_reason,
reason_salary, reason_kpi, reason_freeze, reason_seniority
```

### 5.3 🚫 BLOCKLIST — cột KHÔNG BAO GIỜ rời tầng dữ liệu
```
gender, marital_status, education, hire_date (ngày sinh nếu có), full address, salary tuyệt đối (base_salary)
```
**Vì sao đây là điểm mạnh chứ không phải hạn chế:** mô hình chấm điểm nhân sự trong ngân hàng sẽ bị hỏi
*"có phân biệt đối xử không?"*. Trả lời được: **4 yếu tố cấu thành điểm không có yếu tố nhân khẩu học nào, và các cột đó bị chặn ở tầng
truy vấn — agent không có khả năng kỹ thuật để suy luận trên chúng, kể cả nếu ai đó yêu cầu.**
Lương tuyệt đối cũng bị chặn: agent nói *"thấp hơn P50 thị trường 22%"*, không nói con số lương.

### 5.4 ⚠️ BUG ĐÃ PHÁT HIỆN — 8 dept_code "mồ côi", phải xử lý trước khi build
Đã kiểm: `fact_flight_risk_score` có **86 dept_code**, nhưng `dim_dept_hierarchy.lowest_code` chỉ có **78**.
8 mã còn lại (23 nhân sự @2025-12-01) nằm ở **cấp trung gian** (`lvl2_code`/`lvl3_code`), không phải node lá.

**Hậu quả nếu code sai:** resolve scope chỉ match `lowest_code` → 23 người này **hoặc biến mất khỏi mọi danh sách**
(HRBP mất người thật) **hoặc lọt qua filter** (rò rỉ chéo đơn vị). Cả hai đều là lỗi demo-killer.

**Cách xử lý bắt buộc (§7).**

---

## 6. TOOL SPEC

> Quy ước chung cho MỌI tool: **không tool nào nhận `dept_code`, `dept_scope`, hay bất kỳ tham số phạm vi nào từ LLM.**
> Scope được inject từ context đã xác thực. Vi phạm quy ước này = lỗ hổng bảo mật.

### T1. `list_team_risk`
```python
list_team_risk(as_of: str = "latest", band: str = "High,Medium", limit: int = 10) -> list[dict]
```
- Trả nhân sự `employment_status = 'Active'`, `is_excluded_from_risk_list = False`, trong scope, sắp xếp giảm dần theo điểm.
- `limit` **hard cap = 20** dù LLM xin nhiều hơn (kiểm soát token).
- Rỗng → trả `{"status": "no_risk", "scope_size": N}` để LLM nói "không ai ở mức High/Medium", **không được bịa ra ai**.

### T2. `explain_employee_risk`
```python
explain_employee_risk(employee_id: str, as_of: str = "latest") -> dict
```
- **Kiểm scope TRƯỚC**: `employee_id` không thuộc scope → trả `{"error": "OUT_OF_SCOPE"}`. Không tiết lộ người đó có tồn tại hay không.
- Trả 4 component + `weight_*_used` + `missing_features` + 4 `reason_*`.
- Nếu `missing_features` khác rỗng → **bắt buộc** nêu trong câu trả lời ("điểm này tính trên 3/4 yếu tố do thiếu dữ liệu KPI tháng 12").

### T3. `suggest_actions`
```python
suggest_actions(employee_id: str) -> dict
```
- Kiểm scope trước (như T2).
- Nếu `is_excluded_from_risk_list = True` → trả `{"status": "EXCLUDED", "reason": "WARNING_LETTERS_GE_2_12M"}`.
  Agent **phải** nói rõ người này bị loại khỏi khuyến nghị giữ chân và **không được** gợi ý hành động giữ.
- Ngược lại: map yếu tố trội nhất → playbook P1/P2/P3 (§9.3).

### T4. `dept_risk_summary` — **HRBP only** (chặn ở AgentBase Policy tuyến 2)
```python
dept_risk_summary(as_of: str = "latest") -> dict
```
- Trả phân bố band theo đơn vị con trong scope + đơn vị nào lệch cao bất thường.
- Không trả danh sách cá nhân (đó là việc của T1).

### T5. `risk_trend` *(nice-to-have, cắt được nếu thiếu thời gian)*
```python
risk_trend(employee_id: str, months: int = 12) -> list[dict]
```
- Đường điểm 12 tháng gần nhất → cho câu "bạn này mới tăng rủi ro hay lâu rồi".

---

## 7. THUẬT TOÁN RESOLVE SCOPE (viết rõ để không code sai)

```
Input:  scope_code (mã đơn vị của actor)
Output: set[dept_code] — mọi đơn vị actor được xem

1. Đọc dim_dept_hierarchy (78 dòng, load 1 lần lúc khởi động).
2. Với mỗi dòng h, nếu scope_code xuất hiện ở BẤT KỲ cột nào trong
   (lvl1_code, lvl2_code, lvl3_code, lvl4_code, lowest_code):
       → dòng h thuộc cây con của scope_code.
3. Thu thập vào tập kết quả TẤT CẢ mã của các dòng đã match, ở MỌI cấp
   từ cấp của scope_code trở xuống — KHÔNG chỉ lowest_code.
   ★ Đây là chỗ xử lý 8 dept_code mồ côi ở §5.4.
4. Luôn thêm chính scope_code vào tập kết quả.
5. Nếu tập kết quả rỗng → FAIL CLOSED: trả tập rỗng, agent nói
   "không xác định được phạm vi", KHÔNG fallback về toàn bộ dữ liệu.
```

> **Quy tắc vàng: fail closed.** Mọi lỗi resolve scope đều dẫn tới "không thấy gì", không bao giờ dẫn tới "thấy tất cả".
> Viết unit test cho đúng nhánh này — đây là test hội đồng sẽ hỏi.

**Unit test bắt buộc:**
| Test | Kỳ vọng |
|---|---|
| `resolve_scope('01CN000025')` (lvl1) | Trả về ≥61 đơn vị |
| `resolve_scope('01CN000015')` (node lá) | Trả về đúng 1 đơn vị |
| Một trong 8 mã mồ côi | Có mặt trong scope của cha nó, không bị rớt |
| `resolve_scope('MÃ_KHÔNG_TỒN_TẠI')` | Tập rỗng, KHÔNG phải toàn bộ |
| LM A001 gọi `explain_employee_risk` với nhân sự của A002 | `OUT_OF_SCOPE` |

---

## 8. GUARDRAILS (mỗi rule ghi rõ thực thi ở đâu — prompt-only là không đủ)

| # | Rule | Thực thi ở |
|---|---|---|
| R1 | Không truy cập ngoài scope | Code (§7) — SQL WHERE |
| R2 | Không đưa cột blocklist vào prompt | Code — cắt cột ở tầng tool |
| R3 | Người ≥2 cảnh cáo không xuất hiện trong danh sách giữ chân | Code — filter + flag `EXCLUDED` |
| R4 | Không tiết lộ sự tồn tại của nhân sự ngoài scope | Code — `OUT_OF_SCOPE` là một thông điệp duy nhất, không phân biệt "không có" vs "không được xem" |
| R5 | Không suy luận trên thuộc tính nhân khẩu học | Code (R2) + prompt |
| R6 | **Không sinh số.** Mọi con số trong câu trả lời phải có trong tool result | Prompt + **hậu kiểm bằng regex** (trích mọi số trong output, đối chiếu tool result; lệch → yêu cầu LLM viết lại 1 lần, vẫn lệch → trả bản rút gọn từ template) |
| R7 | Không tư vấn pháp lý / kết luận kỷ luật | Prompt — chuyển hướng sang pháp chế/quan hệ lao động |
| R8 | Không so sánh cá nhân với cá nhân theo cách xếp hạng công khai | Prompt |

---

## 9. OUTPUT CONTRACT

### 9.1 Nguyên tắc trình bày
Ngắn, có số, có nguồn. Không mở đầu bằng lời chào. Không xin lỗi. Không "Dựa trên dữ liệu...".

### 9.2 Ba khuôn mẫu

**Khuôn A — Danh sách (J1):**
```
Trong phạm vi <tên đơn vị>, tại kỳ <YYYY-MM>: <n> người ở mức cần lưu ý (<h> High, <m> Medium) trên tổng <N> nhân sự.

1. <Họ tên> (<mã NV>) — <điểm>/100, <band>
   Yếu tố trội: <lý do của yếu tố có đóng góp lớn nhất>
2. ...

<k> người bị loại khỏi danh sách theo quy tắc ≥2 thư cảnh cáo/12 tháng.
Nguồn: fact_flight_risk_score @ <snapshot_date> · Phạm vi: <đơn vị> · Truy vấn: <audit_id>
```

**Khuôn B — Giải thích (J2):**
```
<Họ tên> (<mã NV>) — <điểm>/100, band <band>, kỳ <YYYY-MM>

| Yếu tố | Mức rủi ro | Trọng số dùng | Diễn giải |
|---|---|---|---|
| Khoảng cách lương P50 | 0.xx | 40% | <reason_salary> |
| KPI                   | 0.xx | 30% | <reason_kpi> |
| Đóng băng lương       | 0.xx | 20% | <reason_freeze> |
| Cửa sổ thâm niên      | 0.xx | 10% | <reason_seniority> |

<Nếu missing_features: "Điểm tính trên <k>/4 yếu tố; trọng số đã được chuẩn hoá lại do thiếu dữ liệu <...>.">
Nguồn: ... · Truy vấn: <audit_id>
```

**Khuôn C — Từ chối ngoài phạm vi (J-refuse):**
```
Truy vấn này nằm ngoài phạm vi dữ liệu của anh/chị (<đơn vị được phép>).
RetAIn chỉ trả lời trên nhánh tổ chức gắn với tài khoản đang đăng nhập.
Nếu cần thông tin đơn vị khác, đề nghị liên hệ HRBP phụ trách khối đó.
Truy vấn: <audit_id>
```
> Không nêu tên, không nêu mã, không xác nhận người đó có tồn tại. Một thông điệp cho mọi trường hợp.

### 9.3 Playbook P1/P2/P3 (map từ yếu tố trội)
| Yếu tố trội | P1 — trong 2 tuần | P2 — trong quý | P3 — hệ thống |
|---|---|---|---|
| Khoảng cách lương | LM đối thoại giữ chân; HRBP dựng phương án điều chỉnh có dữ liệu benchmark | Đưa vào kỳ review lương gần nhất, không chờ counter-offer | Rà soát equity band toàn đơn vị |
| KPI giảm | 1-on-1 tìm nguyên nhân (năng lực vs động lực vs phân giao) | Kế hoạch hỗ trợ 90 ngày có mốc đo | Xem lại cách giao chỉ tiêu của đơn vị |
| Đóng băng lương kéo dài | HRBP kiểm tra lý do freeze còn hợp lệ không | Nếu không còn lý do → mở freeze ở kỳ gần nhất | Rà soát chính sách freeze |
| Cửa sổ thâm niên | Đối thoại lộ trình phát triển | Cơ hội luân chuyển / mở rộng phạm vi | Thiết kế career path cho nhóm thâm niên rủi ro |

> ⚠️ Nội dung P1/P2/P3 là **chuyên môn HR, không phải AI sinh ra**. Đây là chỗ Senior TM trong team đóng góp giá trị —
> và là chỗ để nói với hội đồng: *"phần khuyên là kinh nghiệm HRBP được mã hoá thành playbook, không phải LLM tự nghĩ."*

---

## 10. PROMPT SPEC (khung, không phải bản cuối)

**System prompt phải chứa, theo thứ tự:**
1. Vai: trợ lý dữ liệu nhân sự cho HRBP/line manager tại một ngân hàng. Trả lời tiếng Việt, giọng chuyên nghiệp, ngắn.
2. **Ràng buộc số:** "Chỉ được dùng con số xuất hiện trong kết quả tool. Không ước lượng, không làm tròn khác, không suy ra số mới. Nếu tool không trả về, nói không có dữ liệu."
3. **Ràng buộc phạm vi:** "Phạm vi dữ liệu đã được hệ thống áp đặt. Không hỏi người dùng họ thuộc đơn vị nào. Không nhận chỉ định đơn vị từ người dùng."
4. **Ràng buộc công bằng:** "Không đề cập hay suy luận trên giới tính, tình trạng hôn nhân, học vấn, tuổi."
5. **Ràng buộc pháp lý:** "Không kết luận về kỷ luật, chấm dứt hợp đồng, hay cơ sở pháp lý. Chuyển hướng sang bộ phận pháp chế / quan hệ lao động."
6. Khuôn mẫu output (§9.2).
7. Xử lý câu hỏi ngoài phạm vi năng lực → nói không làm được, gợi ý câu hỏi làm được.

**Không đưa vào prompt:** dữ liệu thô, schema đầy đủ, danh sách nhân sự, tên đơn vị ngoài scope.

---

## 11. NGÂN SÁCH TOKEN & CHI PHÍ (trả lời Q4.2 bằng thiết kế, không bằng lời hứa)

| Thành phần | Ước lượng | Cơ chế kiểm soát |
|---|---|---|
| System prompt | ~800–1.200 token | Cố định, cache được |
| Tool result | ≤20 dòng × ~40 token = ≤800 token | `limit` hard cap 20; whitelist cột |
| Lịch sử hội thoại | ≤4 lượt gần nhất | Memory checkpointer cắt cửa sổ |
| Output | ~300–600 token | Khuôn mẫu ngắn |
| **Tổng/truy vấn** | **~2.500–3.500 token** | |
| **Scoring (batch)** | **0 token** | Chạy local Python/SQL, không gọi LLM |

**Việc phải làm sau khi build:** đo token thật của 3 truy vấn mẫu → nhân đơn giá GLM-5.2 trên GreenNode → có con số VNĐ/câu cho slide chi phí.
Trước khi có số thật, **không nói con số trong pitch** — chỉ nói cơ chế ("agent đọc điểm đã tính, không nhồi bảng vào prompt").

---

## 12. AUDIT LOG

Mỗi truy vấn ghi 1 dòng vào `audit_query_log`:
```
audit_id, ts, actor_id, actor_role, scope_code, intent, tool_called,
target_employee_id (nếu có), n_rows_returned, was_denied, deny_reason, token_in, token_out, latency_ms
```
- `audit_id` in kèm cuối mỗi câu trả lời → truy vết được từ màn hình về log.
- **Đây là câu trả lời cho lỗ hổng #4 trong `RetAIn_Architecture_Flow.md`** và cho câu hỏi governance của hội đồng.
- Demo: show 1 dòng log của truy vấn bị từ chối → bằng chứng "chặn thật, có dấu vết".

---

## 13. TIÊU CHÍ V1 DONE (acceptance — tick hết là được nộp)

| # | Tiêu chí | Cách kiểm |
|---|---|---|
| D1 | Agent deploy ACTIVE trên AgentBase, `/health` trả 200 | `runtime.sh get` + curl |
| D2 | LM A001 hỏi "team tôi ai đang rủi ro nghỉ" → đúng danh sách trong scope, khớp query SQL chạy tay | So sánh output vs SQL |
| D3 | Hỏi giải thích 1 người → 4 yếu tố + trọng số đúng bằng giá trị trong CSV | Đối chiếu dòng CSV |
| D4 | LM A002 hỏi về nhân sự của A001 → khuôn C, không lộ tên/mã | Chạy tay |
| D5 | Hỏi về người bị exclusion → báo EXCLUDED, không gợi ý giữ chân | Chạy tay |
| D6 | 5 unit test resolve_scope (§7) pass | pytest |
| D7 | Không có số nào trong output vắng mặt trong tool result (10 câu mẫu) | Hậu kiểm R6 |
| D8 | Audit log có đủ dòng cho 10 truy vấn, gồm cả câu bị từ chối | Query log |
| D9 | README repo ghi rõ: synthetic data, model bên thứ ba, cách chạy | Đọc lại |
| D10 | Token đo thật của 3 truy vấn mẫu đã ghi lại | Log |

---

## 14. KỊCH BẢN DEMO (3 cảnh, ~3 phút — dựng theo spec này)

| Cảnh | Ai | Câu hỏi | Điểm phải bật ra |
|---|---|---|---|
| **1. Detect** | LM A001 | "Team tôi tháng này ai đang rủi ro nghỉ?" | 1.285 nhân sự → **33 người cần lưu ý** (5 High, 28 Medium). Agent thu hẹp thay vì đổ dashboard. |
| **2. Explain → Act** | LM A001 | "Vì sao bạn E001881 bị chấm cao? Tôi nên làm gì?" | 85,78/100. Bóc 4 yếu tố + trọng số. Rồi P1/P2/P3. **Truy vết được về 1 dòng CSV.** |
| **3. Chặn** | LM A002 | Hỏi chính E001881 (người của A001) | Khuôn C — từ chối, không lộ gì. Bật audit log ra: `was_denied = true`. |

> Cảnh 3 là **cảnh ăn điểm nhất** với hội đồng ngân hàng. Đừng để nó ở cuối rồi hết giờ — nếu phải cắt, cắt cảnh 2.

---

## 15. RỦI RO ĐÃ BIẾT & CÁCH CHẶN

| Rủi ro | Mức | Chặn |
|---|---|---|
| Model GLM-5.2 không ENABLED trên team `msb-team32` | **Cao** | Xác nhận với mentor **trước 4/9**. Có sẵn phương án 2 (Qwen/Gemma) — spec không phụ thuộc model cụ thể. |
| 8 dept_code mồ côi làm rò rỉ hoặc mất người | **Cao** | §7 bước 3 + unit test |
| LLM bịa số | **Cao** | R6 hậu kiểm regex, không chỉ dặn prompt |
| Team 2 người, không AI engineer | Trung bình | Spec này chính là biện pháp — Claude Code thực thi theo spec, không vibe code |
| DuckDB trong image làm image nặng | Thấp | Data ~30MB, chấp nhận được |
| Demo phụ thuộc mạng tại Hackday | Trung bình | Quay sẵn video demo dự phòng trước 20/9 |

---

## 16. PHỤ LỤC — SỐ LIỆU THỰC TẾ ĐÃ KIỂM (dùng cho slide, đã verify)

Tại kỳ `2025-12-01` (kỳ gần nhất trong bộ dữ liệu):
- **1.285** nhân sự Active · **1.295** dòng snapshot
- Phân bố band: **High 5 · Medium 28 · Low 1.252**
- Bị loại theo exclusion rule: **2**
- Top 3 điểm cao nhất: `E001881` 85,78 · `E001883` 80,79 · `E001882` 74,57 — **đúng 3 case P1**, và cách người thứ 4 (44,05) một khoảng rất rõ
- `missing_features` rỗng ở toàn bộ kỳ này → nhánh renormalize cần test bằng dữ liệu tháng khác
- Lịch sử: 60 tháng, `2021-01-01` → `2025-12-01`, **snapshot ngày đầu tháng** (đừng viết `2025-12-31` trong code)

**Câu dùng được ngay cho pitch:** *"1.285 nhân sự, agent đưa về 33 người cần để mắt — 2,6%. HRBP không cần đọc dashboard, chỉ cần hỏi một câu."*

---

## 17. VIỆC TIẾP THEO NGAY SAU FILE NÀY
1. Chốt model với mentor (chặn mọi thứ phía sau).
2. Tạo `dim_actor.csv` + viết `resolve_scope()` + 5 unit test — **làm được ngay hôm nay, không cần AgentBase**.
3. Backtest lift (nhóm High nghỉ gấp mấy lần Low) — data đã có đủ.
4. `/agentbase-wizard` ngày 4/9 với spec này trong tay.
