# -*- coding: utf-8 -*-
"""
Sinh dữ liệu FACT synthetic (100% giả) cho mô hình flight risk, dựa trên các
dim đã ẩn danh sẵn trong ./data/. Không đọc/ghi bất cứ gì trong ./_private/.

Output (./data/):
  dim_employee.csv
  dim_market_benchmark.csv     (không có bản thật -> sinh mới toàn bộ)
  fact_workforce_snapshot.csv  (monthly, 2021-01..2025-12)
  fact_salary_snapshot.csv     (monthly)
  fact_rm_kpi.csv              (monthly, gồm cả disciplinary_warning_count_period)
  fact_termination.csv
"""
import csv
import random
from faker import Faker

SEED = 42
random.seed(SEED)
Faker.seed(SEED)
fake = Faker('vi_VN')

DATA_DIR = 'data'


def p(*parts):
    return '/'.join([DATA_DIR] + list(parts)) if False else __import__('os').path.join(DATA_DIR, *parts)

# --------------------------------------------------------------- helpers --
def midx(y, m):
    return (y - 2000) * 12 + (m - 1)


def from_midx(idx):
    y = 2000 + idx // 12
    m = idx % 12 + 1
    return y, m


def date_str(y, m, d=1):
    return f'{y:04d}-{m:02d}-{d:02d}'


START_IDX = midx(2021, 1)
END_IDX = midx(2025, 12)   # inclusive, 60 months total

# ----------------------------------------------------- 1. load real dims --
with open(p('dim_position.csv'), encoding='utf-8') as f:
    all_positions = list(csv.DictReader(f))
active_positions = [r for r in all_positions if r['status'] == 'A']

with open(p('dim_department.csv'), encoding='utf-8') as f:
    departments = list(csv.DictReader(f))
active_dept_codes = {r['dept_code'] for r in departments if r['is_active'] == '1'}
active_positions = [r for r in active_positions if r['dept_code'] in active_dept_codes]

with open(p('dim_job.csv'), encoding='utf-8') as f:
    job_by_code = {r['job_code']: r for r in csv.DictReader(f)}

print(f'active position templates available: {len(active_positions)}')

# ------------------------------------------------- 2. market benchmark ----
BAND_BASE_P50 = {
    'Band 1': 12_000_000, 'Band 2': 15_000_000, 'Band 3': 19_000_000,
    'Band 4': 24_000_000, 'Band 5': 32_000_000, 'Band 6': 45_000_000,
    'Band 7': 65_000_000, 'Band 8': 100_000_000, 'Band 9': 180_000_000,
    'K': 20_000_000, 'M4': 55_000_000, '': 16_000_000,
}
YEARS = [2021, 2022, 2023, 2024, 2025]
YEAR_GROWTH = {y: 1.07 ** (y - 2021) for y in YEARS}

market_benchmark_rows = []
mbk = 0
benchmark_lookup = {}  # (band, year) -> dict(p25,p50,p75,p90)
for band, base in BAND_BASE_P50.items():
    for y in YEARS:
        p50 = round(base * YEAR_GROWTH[y], -3)
        p25, p75, p90 = round(p50 * 0.85, -3), round(p50 * 1.18, -3), round(p50 * 1.35, -3)
        mbk += 1
        benchmark_lookup[(band, y)] = {'p25': p25, 'p50': p50, 'p75': p75, 'p90': p90}
        market_benchmark_rows.append({
            'market_benchmark_key': mbk,
            'benchmark_id': f'MB{mbk:05d}',
            'job_level': band if band else 'Unspecified',
            'industry_segment': 'Banking',
            'region': 'Vietnam',
            'benchmark_period': date_str(y, 1),
            'currency_code': 'VND',
            'salary_p25': int(p25), 'salary_p50': int(p50), 'salary_p75': int(p75), 'salary_p90': int(p90),
            'source_survey_name': 'Synthetic Salary Survey',
            'data_as_of_date': date_str(y, 1),
            'load_ts': '2026-08-24 00:00:00',
        })


def p50_of(band, year):
    year = min(2025, max(2021, year))
    return benchmark_lookup.get((band, year), benchmark_lookup[('', year)])['p50']

# ------------------------------------------------------- 3. hazard curve --
def hazard(t):
    if t <= 11:
        return 0.012
    if t == 12:
        return 0.0750
    if 13 <= t <= 17:
        return 0.010
    if t == 18:
        return 0.0394
    if 19 <= t <= 36:
        return 0.01345
    return 0.008


def simulate_termination(hire_idx):
    """Returns termination_idx (month index) or None if censored/active through END_IDX."""
    t_start = max(1, START_IDX - hire_idx + 1)
    t_end = END_IDX - hire_idx
    for t in range(t_start, t_end + 1):
        if random.random() < hazard(t):
            return hire_idx + t
    return None

# ------------------------------------------------ 4. employee population --
employees = []  # dicts
eid_counter = 0


def next_eid():
    global eid_counter
    eid_counter += 1
    return f'E{eid_counter:06d}'


def sample_position():
    return random.choice(active_positions)


def make_name_gender():
    gender = random.choice(['M', 'F'])
    try:
        name = fake.name_male() if gender == 'M' else fake.name_female()
    except AttributeError:
        name = fake.name()
    return name, gender


def new_employee(hire_idx, tag=''):
    pos = sample_position()
    name, gender = make_name_gender()
    birth_year = random.randint(1970, 2003)
    emp = {
        'employee_id': next_eid(),
        'full_name': name,
        'gender': gender,
        'birth_date': date_str(birth_year, random.randint(1, 12), random.randint(1, 28)),
        'hire_date': date_str(*from_midx(hire_idx)),
        'hire_idx': hire_idx,
        'dept_code': pos['dept_code'],
        'job_code': pos['job_code'],
        'band': pos['band'],
        'position_code': pos['position_code'],
        'is_manager': pos['is_manager'],
        'location_code': pos['location_code'],
        'job_group_code': pos['job_group_code'],
        'case_study_tag': tag,
    }
    return emp

# --- 4a. seed workforce already employed before 2021-01 -------------------
SEED_SIZE = 500
for _ in range(SEED_SIZE):
    tenure_ago = min(240, max(1, round(random.expovariate(1 / 36))))
    hire_idx = START_IDX - tenure_ago
    emp = new_employee(hire_idx)
    emp['termination_idx'] = simulate_termination(hire_idx)
    emp['freeze_start_offset'] = random.randint(6, 40) if random.random() < 0.18 else None
    emp['freeze_duration'] = random.randint(3, 12) if emp['freeze_start_offset'] is not None else 0
    emp['initial_compa'] = min(1.25, max(0.65, random.gauss(0.95, 0.10)))
    emp['kpi_base'] = min(100, max(10, random.gauss(65, 12)))
    emp['warn_prob_month'] = 0.0025
    employees.append(emp)

# --- 4b. new hires over the 60-month window, growing headcount ------------
for t_off in range(0, 60):
    hire_idx = START_IDX + t_off
    n_hires = round(15 + 16 * t_off / 59)
    for _ in range(n_hires):
        emp = new_employee(hire_idx)
        emp['termination_idx'] = simulate_termination(hire_idx)
        emp['freeze_start_offset'] = random.randint(6, 40) if random.random() < 0.18 else None
        emp['freeze_duration'] = random.randint(3, 12) if emp['freeze_start_offset'] is not None else 0
        emp['initial_compa'] = min(1.25, max(0.65, random.gauss(0.95, 0.10)))
        emp['kpi_base'] = min(100, max(10, random.gauss(65, 12)))
        emp['warn_prob_month'] = 0.0025
        employees.append(emp)

print(f'generic population generated: {len(employees)} employees')

# ------------------------------------------------- 5. case-study employees
CASE_HIRE_IDX = START_IDX  # hired 2021-01 -> full 59-month tenure by Dec-2025
TENURE_AT_END = END_IDX - CASE_HIRE_IDX  # 59

case_defs = [
    # (tag, compa, kpi_base, freeze_target_months, warnings_in_trailing_12m)
    ('P1_high_risk_1', 0.60, 20, 24, 0),
    ('P1_high_risk_2', 0.62, 22, 20, 0),
    ('P1_high_risk_3', 0.58, 18, 18, 0),
    ('P2_medium_1', 0.88, 58, 6, 0),
    ('P2_medium_2', 0.90, 62, 7, 0),
    ('P2_medium_3', 0.75, 45, 9, 0),
    ('EXCLUDE_warnings_1', 0.55, 15, 15, 2),
    ('EXCLUDE_warnings_2', 0.52, 12, 13, 3),
]

case_employees = []
for tag, compa, kpi_base, freeze_target, n_warn in case_defs:
    emp = new_employee(CASE_HIRE_IDX, tag=tag)
    emp['termination_idx'] = None  # active through end of sim, by design
    emp['freeze_start_offset'] = TENURE_AT_END - freeze_target + 1
    emp['freeze_duration'] = 9999  # ongoing, never ends within sim window
    emp['initial_compa'] = compa
    emp['kpi_base'] = kpi_base
    emp['warn_prob_month'] = 0.0
    emp['forced_warning_months'] = []
    if n_warn:
        # spread forced warnings within the trailing 12 months before END_IDX
        offsets = random.sample(range(0, 12), n_warn)
        emp['forced_warning_months'] = [END_IDX - off for off in offsets]
    case_employees.append(emp)

employees.extend(case_employees)
print(f'case-study employees added: {len(case_employees)}')
print(f'total employees: {len(employees)}')

# --------------------------------------------- 6. per-employee monthly sim
workforce_rows = []
salary_rows = []
kpi_rows = []
termination_rows = []

wf_key = sal_key = kpi_key = term_key = 0

for emp in employees:
    hire_idx = emp['hire_idx']
    term_idx = emp.get('termination_idx')
    band = emp['band']
    freeze_start = emp['freeze_start_offset']
    freeze_dur = emp['freeze_duration']
    kpi_base = emp['kpi_base']
    warn_prob = emp['warn_prob_month']
    forced_warn_months = set(emp.get('forced_warning_months', []))

    last_month = term_idx if term_idx is not None else END_IDX
    first_month = max(hire_idx, START_IDX)

    current_salary = None
    warning_months = []  # month indices where a warning occurred

    # pass 1: determine warning months across the employee's active window
    for m in range(first_month, min(last_month, END_IDX) + 1):
        if m in forced_warn_months:
            warning_months.append(m)
        elif warn_prob > 0 and random.random() < warn_prob:
            warning_months.append(m)

    for m in range(first_month, min(last_month, END_IDX) + 1):
        y, mo = from_midx(m)
        tenure_t = m - hire_idx

        # ---- salary state machine (recompute forward each month) ----
        if current_salary is None:
            current_salary = emp['initial_compa'] * p50_of(band, from_midx(hire_idx)[0])
        if tenure_t > 0 and tenure_t % 12 == 0:
            is_frozen_now = freeze_start is not None and freeze_start <= tenure_t < freeze_start + freeze_dur
            if not is_frozen_now:
                raise_pct = min(0.12, max(0.0, random.gauss(0.05, 0.02)))
                current_salary *= (1 + raise_pct)

        is_frozen = freeze_start is not None and freeze_start <= tenure_t < freeze_start + freeze_dur
        pay_freeze_months = (tenure_t - freeze_start + 1) if is_frozen else 0

        p50 = p50_of(band, y)
        gap_pct = (current_salary - p50) / p50
        compa_ratio = current_salary / p50

        # ---- kpi ----
        kpi_base = min(100, max(10, kpi_base + random.gauss(0, 1)))
        kpi_score = round(min(100, max(5, kpi_base + random.gauss(0, 5))), 1)

        # ---- warnings (rolling 12m, inclusive) ----
        warn_this_month = 1 if m in warning_months else 0
        warn_12m = sum(1 for wm in warning_months if m - 11 <= wm <= m)

        # ---- seniority risk window ----
        if tenure_t in (11, 12, 13):
            sw_flag, sw_label = True, '12M_ANNIVERSARY'
        elif tenure_t in (17, 18, 19):
            sw_flag, sw_label = True, '18M_ANNIVERSARY'
        else:
            sw_flag, sw_label = False, ''

        # ---- risk score ----
        risk_salary = min(1.0, max(0.0, -gap_pct) / 0.6)
        risk_kpi = min(1.0, max(0.0, (70 - kpi_score) / 60))
        risk_freeze = min(1.0, pay_freeze_months / 24)
        risk_seniority = 1.0 if sw_flag else 0.3
        flight_risk_score = round(100 * (0.4 * risk_salary + 0.3 * risk_kpi + 0.2 * risk_freeze + 0.1 * risk_seniority), 2)
        flight_risk_band = 'High' if flight_risk_score >= 66 else ('Medium' if flight_risk_score >= 33 else 'Low')

        is_excluded = warn_12m >= 2
        exclusion_reason = 'WARNING_LETTERS_GE_2_12M' if is_excluded else ''

        is_last_month = (term_idx is not None and m == term_idx)
        employment_status = 'Terminated' if is_last_month else 'Active'
        snapshot_date = date_str(y, mo)

        wf_key += 1
        workforce_rows.append({
            'workforce_snapshot_key': wf_key,
            'snapshot_date': snapshot_date,
            'employee_id': emp['employee_id'],
            'dept_code': emp['dept_code'],
            'job_code': emp['job_code'],
            'band': band,
            'manager_employee_id': '',  # filled in post-pass
            'employment_status': employment_status,
            'hire_date': emp['hire_date'],
            'tenure_months': tenure_t,
            'seniority_risk_window_flag': sw_flag,
            'seniority_risk_window_label': sw_label,
            'warning_letter_count_12m': warn_12m,
            'is_excluded_from_risk_list': is_excluded,
            'exclusion_reason': exclusion_reason,
            'flight_risk_score': flight_risk_score,
            'flight_risk_band': flight_risk_band,
        })

        sal_key += 1
        salary_rows.append({
            'salary_snapshot_key': sal_key,
            'employee_id': emp['employee_id'],
            'snapshot_date': snapshot_date,
            'dept_code': emp['dept_code'],
            'band': band,
            'base_salary': int(round(current_salary)),
            'currency_code': 'VND',
            'market_p50': int(p50),
            'salary_gap_to_p50_pct': round(gap_pct, 4),
            'compa_ratio': round(compa_ratio, 4),
            'is_pay_frozen': is_frozen,
            'pay_freeze_months': pay_freeze_months,
        })

        kpi_key += 1
        kpi_rows.append({
            'rm_kpi_key': kpi_key,
            'employee_id': emp['employee_id'],
            'dept_code': emp['dept_code'],
            'kpi_period_start_date': snapshot_date,
            'kpi_period_end_date': snapshot_date,
            'kpi_period_type': 'Monthly',
            'kpi_score': kpi_score,
            'kpi_rating': 'Exceeds' if kpi_score >= 80 else ('Meets' if kpi_score >= 55 else ('Below' if kpi_score >= 35 else 'Poor')),
            'disciplinary_warning_count_period': warn_this_month,
        })

    if term_idx is not None:
        ty, tm = from_midx(term_idx)
        term_key += 1
        termination_rows.append({
            'termination_key': term_key,
            'employee_id': emp['employee_id'],
            'dept_code': emp['dept_code'],
            'termination_date': date_str(ty, tm),
            'last_working_date': date_str(ty, tm),
            'termination_type': 'Voluntary' if random.random() < 0.85 else 'Involuntary',
            'termination_reason_code': random.choice(['CAREER_CHANGE', 'COMPENSATION', 'RELOCATION', 'PERFORMANCE', 'PERSONAL', 'OTHER']),
            'is_regretted_loss': random.random() < 0.4,
            'tenure_at_termination_months': term_idx - hire_idx,
            'band': band,
        })

print(f'workforce_snapshot rows: {len(workforce_rows)}')
print(f'salary_snapshot rows:    {len(salary_rows)}')
print(f'rm_kpi rows:             {len(kpi_rows)}')
print(f'termination rows:        {len(termination_rows)}')

# ------------------------------------------------- 7. manager assignment --
managers_by_dept = {}
for emp in employees:
    if emp['is_manager'] == '1':
        managers_by_dept.setdefault(emp['dept_code'], []).append(emp['employee_id'])

emp_manager = {}
for emp in employees:
    cands = [m for m in managers_by_dept.get(emp['dept_code'], []) if m != emp['employee_id']]
    emp_manager[emp['employee_id']] = random.choice(cands) if cands else ''

for row in workforce_rows:
    row['manager_employee_id'] = emp_manager.get(row['employee_id'], '')

# --------------------------------------------------- 8. headcount sanity --
from collections import Counter
active_counts = Counter()
for row in workforce_rows:
    if row['employment_status'] == 'Active':
        active_counts[row['snapshot_date']] += 1
for ym in ('2021-01-01', '2022-01-01', '2023-01-01', '2024-01-01', '2025-01-01', '2025-12-01'):
    print(f'  active headcount @ {ym[:7]}: {active_counts.get(ym, 0)}')

# ------------------------------------------------------------- 9. write ---
def write(fname, rows, fieldnames):
    with open(p(fname), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f'wrote {p(fname)} ({len(rows)} rows)')


dim_employee_rows = []
for emp in employees:
    term_idx = emp.get('termination_idx')
    dim_employee_rows.append({
        'employee_id': emp['employee_id'],
        'full_name': emp['full_name'],
        'gender': emp['gender'],
        'birth_date': emp['birth_date'],
        'hire_date': emp['hire_date'],
        'termination_date': date_str(*from_midx(term_idx)) if term_idx is not None else '',
        'employment_status_current': 'Terminated' if term_idx is not None else 'Active',
        'dept_code': emp['dept_code'],
        'job_code': emp['job_code'],
        'band': emp['band'],
        'position_code': emp['position_code'],
        'is_manager': emp['is_manager'],
        'manager_employee_id': emp_manager.get(emp['employee_id'], ''),
        'location_code': emp['location_code'],
        'job_group_code': emp['job_group_code'],
        'case_study_tag': emp['case_study_tag'],
    })

write('dim_employee.csv', dim_employee_rows, list(dim_employee_rows[0].keys()))
write('dim_market_benchmark.csv', market_benchmark_rows, list(market_benchmark_rows[0].keys()))
write('fact_workforce_snapshot.csv', workforce_rows, list(workforce_rows[0].keys()))
write('fact_salary_snapshot.csv', salary_rows, list(salary_rows[0].keys()))
write('fact_rm_kpi.csv', kpi_rows, list(kpi_rows[0].keys()))
write('fact_termination.csv', termination_rows, list(termination_rows[0].keys()))

# --------------------------------------------------- 10. top-10 preview ---
latest = [r for r in workforce_rows if r['snapshot_date'] == '2025-12-01']
eligible = [r for r in latest if not r['is_excluded_from_risk_list']]
eligible.sort(key=lambda r: -r['flight_risk_score'])

tag_by_id = {e['employee_id']: e['case_study_tag'] for e in employees}
name_by_id = {e['employee_id']: e['full_name'] for e in employees}

print('\n=== TOP 10 FLIGHT RISK @ 2025-12 (sau khi áp exclusion rule) ===')
for r in eligible[:10]:
    tag = tag_by_id.get(r['employee_id'], '')
    tag_str = f'  [{tag}]' if tag else ''
    print(f"  {r['flight_risk_score']:6.2f}  {r['employee_id']}  {name_by_id[r['employee_id']]:<22}{tag_str}")

print('\n=== case-study employees: score + excluded? (kể cả bị loại) ===')
case_ids = {e['employee_id'] for e in case_employees}
for r in latest:
    if r['employee_id'] in case_ids:
        tag = tag_by_id[r['employee_id']]
        print(f"  {r['flight_risk_score']:6.2f}  excluded={r['is_excluded_from_risk_list']}  {r['employee_id']}  {tag}")
