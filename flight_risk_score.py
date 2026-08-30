# -*- coding: utf-8 -*-
"""
flight_risk_score.py — scoring engine cho mô hình flight risk (RetAIn).

Đọc từ ./data/ (KHÔNG đụng ./_private/):
  fact_workforce_snapshot.csv  -> tenure, seniority risk window, employment_status
  fact_salary_snapshot.csv     -> salary_gap_to_p50_pct, pay_freeze_months
  fact_rm_kpi.csv              -> kpi_score, disciplinary_warning_count_period (warning_letter_count_12m
                                   được engine TỰ tính lại từ đây, không phụ thuộc cột có sẵn trong
                                   fact_workforce_snapshot, để scoring logic độc lập với generation logic)

Trọng số KHÔNG còn khai báo ở file này — xem agent/scoring.py (nguồn sự thật duy nhất,
dùng chung với generate_facts.py và agent/tools.py). Luận giải: TRONG_SO.md.
Nếu một record thiếu feature (không tìm thấy salary_snapshot hoặc rm_kpi cùng employee_id+snapshot_date),
trọng số các feature còn lại được RENORMALIZE (chia lại cho tổng trọng số khả dụng) thay vì coi thiếu = 0.

Hard exclusion: warning_letter_count_12m >= 2 -> loại khỏi danh sách rủi ro (is_excluded_from_risk_list=True).

Output: ./data/fact_flight_risk_score.csv (kèm cột lý do (reason) cho từng yếu tố).

Usage: python3 flight_risk_score.py
"""
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import scoring   # noqa: E402  — nguồn sự thật duy nhất của trọng số

DATA_DIR = 'data'


def p(fname):
    import os
    return os.path.join(DATA_DIR, fname)


WEIGHTS = scoring.WEIGHTS


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
def compute_risk_components(gap_pct, kpi_score, freeze_months, seniority_flag,
                            months_since_move=None):
    return scoring.components(gap_pct, kpi_score, freeze_months, seniority_flag,
                              months_since_move)


def renormalized_score(comps):
    return scoring.renormalize(comps)


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


def reason_promo(months_since_move):
    if months_since_move is None:
        return 'Thiếu dữ liệu lịch sử đổi vai'
    if months_since_move <= scoring.PROMO_RISK_STARTS_AT:
        return f'Đổi vai gần đây ({months_since_move} tháng trước)'
    if months_since_move >= scoring.PROMO_SATURATION_MONTHS:
        return f'Chưa đổi vai hoặc thăng cấp {months_since_move} tháng'
    return f'Lần đổi vai gần nhất cách đây {months_since_move} tháng'


def reason_seniority(flag, label, tenure_months):
    if flag:
        return f'Đang trong cửa sổ rủi ro thâm niên ({label}, {tenure_months} tháng)'
    return f'Ngoài cửa sổ rủi ro thâm niên (thâm niên {tenure_months} tháng)'

# ------------------------------------------------------------ self-test --
def _self_test():
    # đủ 4 feature: trọng số gốc
    comps_full = compute_risk_components(gap_pct=-0.5, kpi_score=20, freeze_months=24,
                                         seniority_flag=True, months_since_move=36)
    score_full, w_full = renormalized_score(comps_full)
    assert abs(sum(w_full.values()) - 1.0) < 1e-9
    assert abs(w_full['salary'] - WEIGHTS['salary']) < 1e-9

    inv = scoring.check_invariants()
    assert not inv['pair_can_reach_high'], inv
    assert inv['well_paid_can_reach_high'], inv

    # thiếu salary+freeze (giả lập không có salary_snapshot tháng đó): chỉ còn kpi(0.3)+seniority(0.1)
    comps_partial = compute_risk_components(gap_pct=None, kpi_score=20, freeze_months=None,
                                            seniority_flag=True, months_since_move=None)
    score_partial, w_partial = renormalized_score(comps_partial)
    assert abs(sum(w_partial.values()) - 1.0) < 1e-9, 'renormalized weights must sum to 1'
    expect_kpi = WEIGHTS['kpi'] / (WEIGHTS['kpi'] + WEIGHTS['seniority'])
    assert abs(w_partial['kpi'] - expect_kpi) < 1e-6, w_partial
    print('self-test passed: renormalization + bất biến trọng số OK')
    print(f"  trọng số: {WEIGHTS}")
    print(f"  hai yếu tố nặng nhất = {inv['top_two_weights']} (ngưỡng Cao = {scoring.BAND_HIGH_AT})")
    print(f"  trần thực tế khi KHÔNG thiếu lương = {inv['realistic_max_without_salary']}")


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
    msm = wf.get('months_since_last_move')
    months_since_move = int(msm) if msm not in (None, '') else None
    seniority_label = wf['seniority_risk_window_label']
    tenure_months = int(wf['tenure_months'])

    comps = compute_risk_components(gap_pct, kpi_score, freeze_months, seniority_flag,
                                    months_since_move)
    score, norm_w = renormalized_score(comps)

    warn_12m = rolling_warning_count_12m(eid, month_idx)
    is_excluded = warn_12m >= 2
    exclusion_reason = 'WARNING_LETTERS_GE_2_12M' if is_excluded else ''

    if score is None:
        band = ''
    else:
        band = scoring.band(score)

    missing_features = ','.join(f for f in scoring.FACTOR_ORDER if f not in comps)

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
        'months_since_last_move': months_since_move if months_since_move is not None else '',
        'seniority_risk_window_flag': seniority_flag,
        'risk_component_salary': round(comps['salary'], 4) if 'salary' in comps else '',
        'risk_component_kpi': round(comps['kpi'], 4) if 'kpi' in comps else '',
        'risk_component_promo': round(comps['promo'], 4) if 'promo' in comps else '',
        'risk_component_freeze': round(comps['freeze'], 4) if 'freeze' in comps else '',
        'risk_component_seniority': round(comps['seniority'], 4) if 'seniority' in comps else '',
        'weight_salary_used': round(norm_w.get('salary', 0), 4),
        'weight_kpi_used': round(norm_w.get('kpi', 0), 4),
        'weight_promo_used': round(norm_w.get('promo', 0), 4),
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
        'reason_promo': reason_promo(months_since_move),
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

# ------------------------------------------------- 11. chẩn đoán vòng luẩn quẩn
# Bảng này tồn tại để trả lời câu hỏi khó nhất của hội đồng:
# "mô hình phát hiện rủi ro, hay chỉ đang xếp hạng người thiếu lương?"
# Nếu mọi ca mức Cao đều nằm ở một ô duy nhất của bảng, câu trả lời là vế sau.
def _gap_bucket(g):
    if g is None or g == '':
        return 'thiếu dữ liệu'
    g = float(g)
    if g >= 0:
        return 'bằng/trên P50'
    if g > -0.2:
        return 'thiếu <20%'
    if g > -0.4:
        return 'thiếu 20-40%'
    return 'thiếu >40%'


from collections import Counter as _C  # noqa: E402
_x = _C()
for r in latest:
    _x[(_gap_bucket(r['salary_gap_to_p50_pct']), r['flight_risk_band'])] += 1

print(f'\n=== PHÂN BỐ: mức thiếu lương × band @ {latest_date} ===')
print(f"{'':16}{'Low':>8}{'Medium':>9}{'High':>7}")
for b in ('bằng/trên P50', 'thiếu <20%', 'thiếu 20-40%', 'thiếu >40%', 'thiếu dữ liệu'):
    row = [_x[(b, k)] for k in ('Low', 'Medium', 'High')]
    if sum(row):
        print(f'{b:16}{row[0]:>8}{row[1]:>9}{row[2]:>7}')

_well_paid_flagged = sum(v for (b, k), v in _x.items()
                         if b == 'bằng/trên P50' and k in ('Medium', 'High'))
_inv = scoring.check_invariants()
print(f"\nbất biến 1 — hai yếu tố nặng nhất = {_inv['top_two_weights']} < {scoring.BAND_HIGH_AT}: "
      f"{'PASS' if not _inv['pair_can_reach_high'] else 'FAIL'}  (phải cần ≥3 yếu tố xấu)")
print(f"bất biến 2 — người KHÔNG thiếu lương vẫn lên được mức Cao (trần "
      f"{_inv['realistic_max_without_salary']}): {'PASS' if _inv['well_paid_can_reach_high'] else 'FAIL'}")
print(f"thực tế    — số người bằng/trên P50 mà vẫn bị gắn cờ: {_well_paid_flagged} "
      f"{'PASS' if _well_paid_flagged else 'FAIL (mô hình vẫn chỉ đang xếp hạng người thiếu lương)'}")

print('\n=== CASE STUDY: phân rã từng yếu tố ===')
for r in latest:
    tag = emp_meta[r['employee_id']]['case_study_tag']
    if not tag:
        continue
    comps = compute_risk_components(
        float(r['salary_gap_to_p50_pct']) if r['salary_gap_to_p50_pct'] != '' else None,
        float(r['kpi_score']) if r['kpi_score'] != '' else None,
        int(r['pay_freeze_months']) if r['pay_freeze_months'] != '' else None,
        r['seniority_risk_window_flag'],
        int(r['months_since_last_move']) if r['months_since_last_move'] != '' else None)
    sc, w = renormalized_score(comps)
    parts = '  '.join(f"{k}={100 * w[k] * comps[k]:.1f}" for k in scoring.FACTOR_ORDER if k in comps)
    print(f"  {sc:6.2f} {scoring.band(sc):<7} {r['employee_id']}  {tag:<18} {parts}")


# ------------------------------- 12. ca mẫu có nằm trong tầm nhìn actor không --
# Điểm đẹp mà actor demo không nhìn thấy thì kịch bản demo vẫn hỏng.
# Kiểm luôn ở đây thay vì phát hiện lúc đứng trên sân khấu.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent.scope import resolve_scope

    with open(p('dim_actor.csv'), encoding='utf-8') as f:
        _actors = list(csv.DictReader(f))
    _scopes = {a['actor_id']: resolve_scope(a['dept_scope_code']) for a in _actors}

    print('\n=== AI NHÌN THẤY CA MẪU NÀO ===')
    for r in latest:
        tag = emp_meta[r['employee_id']]['case_study_tag']
        if not tag:
            continue
        seen = [aid for aid, sc in _scopes.items() if r['dept_code'] in sc]
        print(f"  {r['employee_id']}  {tag:<20} {r['dept_code']}  ->  "
              f"{', '.join(seen) if seen else 'KHÔNG AI THẤY — kịch bản demo sẽ hỏng'}")
except Exception as _e:
    print(f'\n(bỏ qua kiểm tra tầm nhìn actor: {_e})')


# ---------------------------- 13. chọn ngưỡng band bằng số liệu, không bằng cảm --
# "Bao nhiêu người cần để mắt" là con số sản phẩm, không phải con số kỹ thuật.
# Gắn cờ 14% nhân sự thì cán bộ quản lý sẽ bỏ qua toàn bộ danh sách.
_scores = sorted((r['flight_risk_score'] for r in latest
                  if not r['is_excluded_from_risk_list'] and r['flight_risk_score'] != ''),
                 reverse=True)
_n = len(_scores)
print(f'\n=== CHỌN NGƯỠNG: {_n} nhân sự đủ điều kiện @ {latest_date} ===')
print(f"{'ngưỡng':>8}{'số người':>10}{'% nhân sự':>11}")
for th in (33, 38, 40, 45, 50, 55, 66):
    k = sum(1 for s_ in _scores if s_ >= th)
    print(f'{th:>8}{k:>10}{100 * k / _n:>10.1f}%')
print('  (mục tiêu nhóm Trung bình+Cao: khoảng 3-6% — đủ ít để người ta thật sự đọc hết)')
