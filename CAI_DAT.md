# RetAIn — khung agent v0.2 (29/08/2026)

Giải nén **đè lên gốc repo `retain`** (ghi đè `agent/`, `tests/` của v0.1).

```
retain/
  agent/     scope · store · tools · registry · prompt · guard · llm · runtime
  tests/     test_scope · test_tools · test_agent      (31 bài)
  data/      dim_actor.csv · playbook.csv              (mới)
  main.py · Dockerfile · requirements.txt · .dockerignore · run_local.py · demo_smoke.py
```

## Chạy — không cần model, không cần mạng

```powershell
python -m pip install -r requirements.txt
python -m pytest tests\ -q          # 31 passed
python run_local.py --scenario      # 5 cảnh demo qua CẢ đường ống agent
python run_local.py                 # chat tay, đóng vai A001
python run_local.py --actor A002    # đổi vai, thử phân quyền
```

`MockLLM` giả lập model: chọn tool bằng từ khoá rồi dựng câu trả lời từ đúng số của tool.
Không thay được model thật, nhưng đủ để kiểm đường ống + phân quyền + guard mà không tốn token.

## Chạy server (bước tập dượt cho deploy)

```powershell
python main.py
# cửa sổ khác:
curl http://localhost:8080/health
curl -X POST http://localhost:8080/chat -H "X-Actor-Id: A001" -H "Content-Type: application/json" -d "{\"message\":\"Team minh co ai muon di khong?\"}"
```

## Nối model thật

Điền `.env` (đã bị .gitignore chặn):
```
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_API_KEY=...
LLM_MODEL=<model đã xác nhận ENABLED>
```
rồi `python run_local.py --real --scenario`.

**Đây là lúc so model.** Chạy `--scenario` với từng model, nhìn ba cột: tool gọi có đúng
không · guard ĐẠT hay HỎNG · token tiêu bao nhiêu. Chọn bằng số, đừng chọn bằng cảm giác.

## Kiến trúc — vì sao tách như vậy

`main.py` **cố tình mỏng**. Ngày 4/9 chạy `/agentbase-wizard`, wizard sinh ra bản `main.py`
dùng `GreenNodeAgentBaseApp` — lúc đó **chỉ thay lớp server, giữ nguyên toàn bộ `agent/`**.
Nghiệp vụ và phân quyền không dính vào SDK nền tảng, nên đổi nền tảng không phải viết lại.

## Chốt an toàn — đừng gỡ

| Chỗ | Nội dung |
|---|---|
| `registry.TOOL_SCHEMAS` | Schema đưa cho LLM **không có** tham số phạm vi. LLM không có ô nào để đòi dữ liệu đơn vị khác. |
| `registry.dispatch()` | Vứt bỏ mọi tham số phạm vi nếu model cố truyền, và ghi lại vào `_dropped_params`. |
| `runtime.answer()` | Resolve scope ở **bước 2**, LLM chỉ vào cuộc ở **bước 3**. Thứ tự này là lý do không "hỏi khéo" được. |
| `guard.verify()` | Mọi con số trong câu trả lời phải truy được về kết quả tool. Sai → viết lại 1 lần → vẫn sai thì trả bản dựng từ template, **không đưa câu bịa ra ngoài**. |
| `test_schema_khong_lo_tham_so_pham_vi` | Bài test canh lỗ hổng. Đỏ là dừng, đừng tắt. |

## CHƯA làm

1. `estimate_cost()` trả `None` — cần `fact_salary_snapshot` + `dim_market_benchmark`.
2. T7 `allocate_retention_budget` — chờ (1).
3. T8 `unit_narrative` — cần model thật.
4. Memory (hội thoại nhiều lượt qua AgentBase Memory) — làm ở bước wizard.

## data/playbook.csv — chờ Mia

12 ô hiện là **bản nháp** (`status=draft`). Agent tự nói ra điều đó trong câu trả lời,
để bản nháp không lỡ lên sân khấu như bản thật.

Khi Mia gửi playbook: thay cột `action`, đổi `status` thành `final`. Không đụng cột
`factor` / `priority` — code tra theo hai cột đó.
