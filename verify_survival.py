import csv

with open('data/dim_employee.csv', encoding='utf-8') as f:
    emps = {r['employee_id']: r for r in csv.DictReader(f)}

with open('data/fact_termination.csv', encoding='utf-8') as f:
    terms = {r['employee_id']: int(r['tenure_at_termination_months']) for r in csv.DictReader(f)}


def midx(y, m):
    return (y - 2000) * 12 + (m - 1)


END_IDX = midx(2025, 12)


START_IDX = midx(2021, 1)


def check(t_mark, new_hires_only):
    n_eligible = 0
    n_survived = 0
    for eid, e in emps.items():
        if e['case_study_tag']:
            continue
        y, m, d = map(int, e['hire_date'].split('-'))
        hire_idx = midx(y, m)
        if new_hires_only and hire_idx < START_IDX:
            continue  # seed employee: pre-hire history not simulated, skews low-t checks
        if hire_idx + t_mark > END_IDX:
            continue  # not enough follow-up time yet
        n_eligible += 1
        t_term = terms.get(eid)
        if t_term is None or t_term > t_mark:
            n_survived += 1
    return n_survived / n_eligible if n_eligible else None, n_eligible


print('-- pure new-hire cohorts only (full hazard curve from month 1) --')
for t in (12, 18, 36, 59):
    rate, n = check(t, new_hires_only=True)
    print(f't={t:>3} months: survival = {rate:.3f}  (n eligible cohort = {n})')

print('\n-- whole population incl. seed (for reference; seed pre-history not simulated) --')
for t in (12, 18, 36, 60):
    rate, n = check(t, new_hires_only=False)
    print(f't={t:>3} months: survival = {rate:.3f}  (n eligible cohort = {n})')
