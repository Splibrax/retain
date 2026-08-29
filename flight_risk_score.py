# -*- coding: utf-8 -*-
"""
flight_risk_score.py — scoring engine cho mô hình flight risk (RetAIn).

Đọc từ ./data/ (KHÔNG đụng ./_private/):
  fact_workforce_snapshot.csv  -> tenure, seniority risk window, employment_status
  fact_salary_snapshot.csv     -> salary_gap_to_p50_pct, pay_freeze_months
  fact_rm_kpi.csv              -> kpi_score, disciplinary_warning_count_period (warning_letter_count_12m
                                   được engine TỰ tính lại từ đây, không phụ thuộc cột có sẵn trong
                                   fact_workforce_snapshot, để scoring logic độc lập với generation logic)

Trọng số: market gap vs P50 (40%), KPI (30%), pay freeze duration (20%), tenure risk window (10%).
Nếu một record thiếu feature (không tìm thấy salary_snapshot hoặc rm_kpi cùng employee_id+snapshot_date),
trọng số các feature còn lại được RENORMALIZE (chia lại cho tổng trọng số khả dụng) thay vì coi thiếu = 0.

Hard exclusion: warning_letter_count_12m >= 2 -> loại khỏi danh sách rủi ro (is_excluded_from_risk_list=True).

Output: ./data/fact_flight_risk_score.csv (kèm cột lý do (reason) cho từng yếu tố).

Usage: python3 flight_risk_score.py
"""
import csv
from collections import defaultdict

DATA_DIR = 'data'


def p(fname):
    import os
    return os.path.join(DATA_DIR, fname)


WEIGHTS = {'salary': 0.40, 'kpi': 0.30, 'freeze': 0.20, 'seniority': 0.10}


def midx(y, m):
    return (y - 2000) * 12 + (m - 1)


def parse_date(s):
    y, m, d = s.split('-')
    return int(y), int(m), int(d)


def to_bool(s):
    return str(s).strip() == 'True'

# ------------------------------------------------------------- load ------
with open(p('fact_workforce_snapshot.csv'), encoding='utf-8') as f:
    workforce = list(csv.DictReader(f))

with open(p('fact_salary_snapshot.csv'), encoding='utf-8') as f:
    salary_rows = list(csv.DictReader(f))
salary_by_key = {(r['employee_id'], r['snapshot_date']): r for r in salary_rows}

with open(p('fact_rm_kpi.csv'), encoding='utf-8') as f:
    kpi_rows = list(csv.DictReader(f))
kpi_by_key = {(r['employee_id'], r['kpi_period_start_date']): r for r in kpi_rows}

# warning history per employee, as (month_index, warning_count) sorted by month
warnings_by_emp = defaultdict(list)
for r in kpi_rows:
    cnt = int(r['disciplinary_warning_count_period'])
    if cnt > 0:
        y, m, d = parse_date(r['kpi_period_start_date'])
        warnings_by_emp[r['employee_id']].append((midx(y, m), cnt))
for eid in warnings_by_emp:
    warnings_by_emp[eid].sort()

print(f'loaded: {len(workforce)} workforce_snapshot rows, {len(salary_rows)} salary rows, {len(kpi_rows)} kpi rows')


def rolling_warning_count_12m(employee_id, snapshot_month_idx):
    total = 0
    for mo_idx, cnt in warnings_by_emp.get(employee_id, []):
        if snapshot_month_idx - 11 <= mo_idx <= snapshot_month_idx:
            total += cnt
    return total

# ------------------------------------------------------- scoring core ----
def compute_risk_components(gap_pct, kpi_score, freeze_months, seniority_flag):
    """Returns dict of factor -> (risk_value 0..1) for whichever factors have data."""
    comps = {}
    if gap_pct is not None:
        comps['salary'] = min(1.0, max(0.0, -gap_pct) / 0.6)
    if freeze_months is not None:
        comps['freeze'] = min(1.0, max(0.0, freeze_months) / 24)
    if kpi_score is not None:
        comps['kpi'] = min(1.0, max(0.0, (70 - kpi_score) / 60))
    if seniority_flag is not None:
        comps['seniority'] = 1.0 if seniority_flag else 0.3
    return comps


def renormalized_score(comps):
    avail_weight = sum(WEIGHTS[k] for k in comps)
    if avail_weight == 0:
        return None, {}
    norm_w = {k: WEIGHTS[k] / avail_weight for k in comps}
    score = 100 * sum(norm_w[k] * comps[k] for k in comps)
    return round(score, 2), norm_w


def reason_salary(gap_pct):
    if gap_pct is None:
        return 'Thiếu dữ liệu lương tháng này'
    if gap_pct < 0:
        return f'Lương thấp hơn P50 thị trường {abs(gap_pct) * 100:.1f}%'
    return f'Lương bằng/cao hơn P50 thị trường ({gap_pct * 100:+.1f}%)'


def reason_kpi(kpi_score):
    if kpi_score is None:
        return 'Thiếu dữ liệu KPI tháng này'
    return f'Điểm KPI {kpi_score:.1f}/100'


def reason_freeze(freeze_months):
    if freeze_months is None:
        return 'Thiếu dữ liệu lương (không xác định pay freeze)'
    if freeze_months > 0:
        return f'Đang bị đóng băng lương {freeze_months} tháng'
    return 'Không bị đóng băng lương'


def reason_seniority(flag, label, tenure_months):
    if flag:
        return f'Đang trong cửa sổ rủi ro thâm niên ({label}, {tenure_months} tháng)'
    return f'Ngoài cửa sổ rủi ro thâm niên (thâm niên {tenure_months} tháng)'

# ------------------------------------------------------------ self-test --
def _self_test():
    # đủ 4 feature: trọng số gốc
    comps_full = compute_risk_components(gap_pct=-0.5, kpi_score=20, freeze_months=24, seniority_flag=True)
    score_full, w_full = renormalized_score(comps_full)
    assert abs(sum(w_full.values()) - 1.0) < 1e-9
    assert abs(w_full['salary'] - 0.40) < 1e-9

    # thiếu salary+freeze (giả lập không có salary_snapshot tháng đó): chỉ còn kpi(0.3)+seniority(0.1)
    comps_partial = compute_risk_components(gap_pct=None, kpi_score=20, freeze_months=None, seniority_flag=True)
    score_partial, w_partial = renormalized_score(comps_partial)
    assert abs(sum(w_partial.values()) - 1.0) < 1e-9, 'renormalized weights must sum to 1'
    assert abs(w_partial['kpi'] - 0.75) < 1e-6, f"kpi weight should renormalize to 0.3/0.4=0.75, got {w_partial['kpi']}"
    assert abs(w_partial['seniority'] - 0.25) < 1e-6
    print('self-test passed: renormalization when features are missing works as expected')


_self_test()

# --------------------------------------------------------- main scoring --
out_rows = []
key = 0
n_missing_salary = n_missing_kpi = 0

for wf in workforce:
    eid = wf['employee_id']
    snap_date = wf['snapshot_date']
    y, m, d = parse_date(snap_date)
    month_idx = midx(y, m)

    sal = salary_by_key.get((eid, snap_date))
    kpi = kpi_by_key.get((eid, snap_date))
    if sal is None:
        n_missing_salary += 1
    if kpi is None:
        n_missing_kpi += 1

    gap_pct = float(sal['salary_gap_to_p50_pct']) if sal else None
    freeze_months = int(sal['pay_freeze_months']) if sal else None
    kpi_score = float(kpi['kpi_score']) if kpi else None
    seniority_flag = to_bool(wf['seniority_risk_window_flag'])
    seniority_label = wf['seniority_risk_window_label']
    tenure_months = int(wf['tenure_months'])

    comps = compute_risk_components(gap_pct, kpi_score, freeze_months, seniority_flag)
    score, norm_w = renormalized_score(comps)

    warn_12m = rolling_warning_count_12m(eid, month_idx)
    is_excluded = warn_12m >= 2
    exclusion_reason = 'WARNING_LETTERS_GE_2_12M' if is_excluded else ''

    if score is None:
        band = ''
    else:
        band = 'High' if score >= 66 else ('Medium' if score >= 33 else 'Low')

    missing_features = ','.join(f for f in ('salary', 'kpi', 'freeze', 'seniority') if f not in comps)

    key += 1
    out_rows.append({
        'flight_risk_score_key': key,
        'employee_id': eid,
        'snapshot_date': snap_date,
        'dept_code': wf['dept_code'],
        'band': wf['band'],
        'employment_status': wf['employment_status'],
        'salary_gap_to_p50_pct': gap_pct if gap_pct is not None else '',
        'kpi_score': kpi_score if kpi_score is not None else '',
        'pay_freeze_months': freeze_months if freeze_months is not None else '',
        'tenure_months': tenure_months,
        'seniority_risk_window_flag': seniority_flag,
        'risk_component_salary': round(comps['salary'], 4) if 'salary' in comps else '',
        'risk_component_kpi': round(comps['kpi'], 4) if 'kpi' in comps else '',
        'risk_component_freeze': round(comps['freeze'], 4) if 'freeze' in comps else '',
        'risk_component_seniority': round(comps['seniority'], 4) if 'seniority' in comps else '',
        'weight_salary_used': round(norm_w.get('salary', 0), 4),
        'weight_kpi_used': round(norm_w.get('kpi', 0), 4),
        'weight_freeze_used': round(norm_w.get('freeze', 0), 4),
        'weight_seniority_used': round(norm_w.get('seniority', 0), 4),
        'missing_features': missing_features,
        'warning_letter_count_12m': warn_12m,
        'is_excluded_from_risk_list': is_excluded,
        'exclusion_reason': exclusion_reason,
        'flight_risk_score': score if score is not None else '',
        'flight_risk_band': band,
        'reason_salary': reason_salary(gap_pct),
        'reason_kpi': reason_kpi(kpi_score),
        'reason_freeze': reason_freeze(freeze_months),
        'reason_seniority': reason_seniority(seniority_flag, seniority_label, tenure_months),
    })

print(f'rows with missing salary_snapshot: {n_missing_salary}')
print(f'rows with missing rm_kpi:          {n_missing_kpi}')

with open(p('fact_flight_risk_score.csv'), 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)
print(f"wrote {p('fact_flight_risk_score.csv')} ({len(out_rows)} rows)")

# ------------------------------------------------------- top-10 preview --
latest_date = max(r['snapshot_date'] for r in out_rows)
latest = [r for r in out_rows if r['snapshot_date'] == latest_date and r['employment_status'] == 'Active']
eligible = [r for r in latest if not r['is_excluded_from_risk_list']]
eligible.sort(key=lambda r: -r['flight_risk_score'])

with open(p('dim_employee.csv'), encoding='utf-8') as f:
    emp_meta = {r['employee_id']: r for r in csv.DictReader(f)}

print(f'\n=== TOP 10 FLIGHT RISK @ {latest_date} (fact_flight_risk_score.csv, sau exclusion) ===')
for r in eligible[:10]:
    tag = emp_meta[r['employee_id']]['case_study_tag']
    tag_str = f"  [{tag}]" if tag else ''
    name = emp_meta[r['employee_id']]['full_name']
    print(f"  {r['flight_risk_score']:6.2f}  {r['employee_id']}  {name:<22}{tag_str}")

p1_cases = [eid for eid, e in emp_meta.items() if e['case_study_tag'].startswith('P1_')]
top10_ids = [r['employee_id'] for r in eligible[:10]]
p1_in_top10 = [eid for eid in p1_cases if eid in top10_ids]
print(f'\ncheck: {len(p1_in_top10)}/{len(p1_cases)} case P1 nằm trong top 10 -> {"PASS" if len(p1_in_top10) == len(p1_cases) else "FAIL"}')
