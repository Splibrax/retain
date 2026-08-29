# RetAIn — People Analytics Flight Risk (Synthetic Demo)

RetAIn là dự án People Analytics dự báo **rủi ro nghỉ việc (flight risk)** của nhân sự, dựa trên dữ liệu
HR dạng star schema (fact/dim). Mô hình chấm điểm rủi ro cho từng nhân viên theo 4 yếu tố có trọng số:

| Yếu tố | Trọng số | Nguồn |
|---|---|---|
| Khoảng cách lương so với P50 thị trường (market gap) | 40% | `fact_salary_snapshot` × `dim_market_benchmark` |
| Điểm KPI | 30% | `fact_rm_kpi` |
| Thời gian đóng băng lương (pay freeze) | 20% | `fact_salary_snapshot` |
| Cửa sổ rủi ro theo thâm niên (tenure risk window) | 10% | `fact_workforce_snapshot` |

**Quy tắc loại trừ cứng (hard exclusion)**: nhân sự có ≥2 thư cảnh cáo trong 12 tháng gần nhất bị loại
khỏi danh sách rủi ro, bất kể điểm số cao thế nào.

Nếu một nhân viên/tháng thiếu dữ liệu ở một yếu tố nào đó (không tìm thấy salary snapshot hoặc KPI tháng
đó), engine **renormalize** trọng số trên các yếu tố còn dữ liệu thay vì coi thiếu = 0 điểm.

> ⚠️ **Toàn bộ dữ liệu trong `./data/` là dữ liệu GIẢ 100% (synthetic)** — nhân sự, tên phòng ban, lương,
> KPI, thư cảnh cáo... đều được sinh bằng script, không phải dữ liệu thật của bất kỳ tổ chức nào. Tên
> phòng ban/đơn vị đã được đổi tên hư cấu qua một bước ẩn danh hóa từ dữ liệu tổ chức thật (xem mục
> "Nguồn gốc dữ liệu" bên dưới) trước khi bất kỳ thứ gì rời khỏi máy này.

## Cấu trúc thư mục

- **`_private/`** — dữ liệu tổ chức THẬT (dim_dept_hierarchy, dim_department, dim_job, dim_position,
  dim_job_grouping, dim_date, data_dictionary gốc) và bảng map tên thật↔tên giả dùng để tra cứu ngược.
  **Bị `.gitignore` chặn hoàn toàn, không bao giờ commit.** Các pipeline sinh dữ liệu fact/scoring ở dưới
  đây **không bao giờ đọc hay ghi vào thư mục này**.
- **`data/`** — dữ liệu **synthetic** duy nhất được commit lên git:
  - `dim_department.csv`, `dim_dept_hierarchy.csv`, `dim_job.csv`, `dim_job_grouping.csv`,
    `dim_position.csv`, `dim_date.csv`, `data_dictionary.csv` — dim đã ẩn danh hóa từ dữ liệu thật.
  - `dim_employee.csv` — nhân sự giả 100% (Faker, tên VN), gán vào dept/job/position/band có sẵn.
  - `dim_market_benchmark.csv` — benchmark lương thị trường theo band × năm, sinh mới hoàn toàn (không
    có bản dữ liệu thật tương ứng).
  - `fact_workforce_snapshot.csv`, `fact_salary_snapshot.csv`, `fact_rm_kpi.csv`, `fact_termination.csv`
    — fact monthly grain, 2021-01 → 2025-12, do `generate_facts.py` sinh ra.
  - `fact_flight_risk_score.csv` — điểm rủi ro từng nhân viên/tháng, do `flight_risk_score.py` sinh ra.
- **`schema_reference.md`** — schema chi tiết (tên cột + kiểu dữ liệu) toàn bộ bảng fact/dim.
- **`generate_facts.py`** — sinh nhân sự + toàn bộ fact table synthetic (đọc dim từ `./data/`, ghi fact
  vào `./data/`). Đã bao gồm sẵn ~8 nhân sự case-study (3 P1 rủi ro cao, 3 P2 trung bình, 2 case test
  hard-exclusion) được đánh dấu ở cột `dim_employee.case_study_tag`.
- **`flight_risk_score.py`** — scoring engine chính thức, tách biệt khỏi `generate_facts.py`.
- **`verify_survival.py`** — kiểm tra nhanh đường cong sống sót (survival curve) của dữ liệu termination
  sinh ra so với mục tiêu hiệu chỉnh ban đầu.

## Cách chạy

Bộ dữ liệu hiện tại trong `./data/` đã đạt yêu cầu, **không cần sinh lại** trừ khi bạn chủ động muốn làm
mới. Thứ tự chạy đúng nếu cần tái sinh:

```
python3 generate_facts.py       # sinh dim_employee + toàn bộ fact_* (trừ flight_risk_score)
python3 flight_risk_score.py    # đọc fact_* vừa sinh, tính điểm, ghi fact_flight_risk_score.csv
```

`flight_risk_score.py` luôn đọc lại dữ liệu hiện có trong `./data/` — chạy độc lập bất cứ lúc nào mà
không cần chạy lại `generate_facts.py`, miễn là các file `fact_workforce_snapshot.csv`,
`fact_salary_snapshot.csv`, `fact_rm_kpi.csv` đã tồn tại. Cả hai script đều set random seed cố định
(42) để kết quả tái lập được.

Sau khi chạy `flight_risk_score.py`, script tự in ra **top 10 rủi ro cao nhất** tại tháng snapshot mới
nhất (sau khi áp exclusion rule) kèm kiểm tra tự động: 3 case P1 phải nằm trong top 10.

## Nguồn gốc dữ liệu

Dim gốc (`dim_department`, `dim_dept_hierarchy`, `dim_job`, `dim_position`...) bắt nguồn từ dữ liệu tổ
chức thật, được ẩn danh hóa cục bộ (rename đơn vị/phòng ban, giữ nguyên cấu trúc cây và format mã) trước
khi đưa vào `./data/`. Toàn bộ nhân sự, lương, KPI, termination, thư cảnh cáo là dữ liệu **sinh mới hoàn
toàn**, không truy xuất từ bất kỳ hệ thống hay cá nhân thật nào.

## ⚠️ Trước khi `git init` / commit lần đầu

Chạy lệnh sau để xác nhận `_private/` thực sự bị git bỏ qua trước khi push bất cứ thứ gì:

```
git check-ignore -v ./_private/
```

Lệnh phải trả về kết quả khớp với dòng `_private/` trong `.gitignore`. Nếu không có output nghĩa là
`.gitignore` **chưa** hoạt động — dừng lại, không commit, kiểm tra lại trước khi tiếp tục.
