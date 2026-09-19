# -*- coding: utf-8 -*-
"""
migrate_reason_wording.py — đổi TỪ NGỮ trong các cột reason_* của fact table.
Chạy một lần, ngày 15/09/2026.

VÌ SAO PHẢI CÓ FILE NÀY
-----------------------
Các câu lý do được TÍNH SẴN và ghi cứng vào fact_flight_risk_score.csv lúc sinh
dữ liệu. Sửa hàm reason_*() trong flight_risk_score.py KHÔNG làm đổi dữ liệu
đang chạy — dữ liệu đã nằm đó rồi.

Cách an toàn KHÔNG phải là sinh lại fact table: generate_facts.py có yếu tố
ngẫu nhiên, sinh lại sẽ làm đổi điểm và đổi luôn ba ca demo đã thuộc lòng.
File này chỉ GHI ĐÈ CHUỖI, không đụng một con số nào.

BẤT BIẾN (script tự kiểm tra ở cuối, không cần tin lời):
    mọi cột KHÔNG bắt đầu bằng 'reason_' phải giống hệt trước và sau, từng byte.

Cách dùng:
    python migrate_reason_wording.py data/fact_flight_risk_score.csv
    python migrate_reason_wording.py data/fact_flight_risk_score.csv --dry-run

Tự nhận diện dữ liệu 4 yếu tố (không có reason_promo) hay 5 yếu tố.
Tự sao lưu sang .bak trước khi ghi.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import sys

csv.field_size_limit(10_000_000)

# ------------------------------------------------------------------ freeze --
# Cũ: 'Đang bị đóng băng lương 7 tháng' / 'Không bị đóng băng lương'
RE_FREEZE_ON = re.compile(r'^Đang bị đóng băng lương (\d+) tháng$')
RE_FREEZE_OFF = re.compile(r'^Không bị đóng băng lương$')
RE_FREEZE_NA = re.compile(r'^Thiếu dữ liệu lương \(không xác định pay freeze\)$')


def new_freeze(old: str) -> str:
    m = RE_FREEZE_ON.match(old)
    if m:
        return f'Bị dừng xét điều chỉnh lương {m.group(1)} tháng'
    if RE_FREEZE_OFF.match(old):
        # KHÔNG dịch thành 'đã được điều chỉnh lương'. Bằng 0 chỉ có nghĩa là
        # không nằm trong cửa sổ dừng xét — người chưa tới kỳ cũng bằng 0.
        return 'Vẫn trong diện xét điều chỉnh lương bình thường'
    if RE_FREEZE_NA.match(old):
        return 'Thiếu dữ liệu lương (không xác định được diện xét điều chỉnh)'
    return old


# ------------------------------------------------------------------- promo --
# Cũ: 'Đổi vai gần đây (N tháng trước)'
#     'Chưa đổi vai hoặc thăng cấp N tháng'
#     'Lần đổi vai gần nhất cách đây N tháng'
#     'Thiếu dữ liệu lịch sử đổi vai'
RE_PROMO_RECENT = re.compile(r'^Đổi vai gần đây \((\d+) tháng trước\)$')
RE_PROMO_LONG = re.compile(r'^Chưa đổi vai hoặc thăng cấp (\d+) tháng$')
RE_PROMO_MID = re.compile(r'^Lần đổi vai gần nhất cách đây (\d+) tháng$')
RE_PROMO_NA = re.compile(r'^Thiếu dữ liệu lịch sử đổi vai$')


def new_promo(old: str, months_since_move, tenure_months) -> str:
    """
    Ca 'mới gia nhập' được quyết bằng SỐ, không bằng chuỗi: khi số tháng từ lần
    thay đổi vị trí gần nhất >= thâm niên thì người đó chưa từng được điều
    chuyển hay bổ nhiệm lần nào — cái gọi là 'move' chính là ngày vào làm.
    """
    if months_since_move is not None and tenure_months is not None \
            and months_since_move >= tenure_months:
        return (f'Chưa điều chuyển/bổ nhiệm lần nào kể từ khi vào làm '
                f'({tenure_months} tháng)')
    m = RE_PROMO_RECENT.match(old)
    if m:
        return f'Vừa được điều chuyển/bổ nhiệm ({m.group(1)} tháng trước)'
    m = RE_PROMO_LONG.match(old)
    if m:
        return f'Chưa được điều chuyển hoặc bổ nhiệm {m.group(1)} tháng'
    m = RE_PROMO_MID.match(old)
    if m:
        return f'Lần điều chuyển/bổ nhiệm gần nhất cách đây {m.group(1)} tháng'
    if RE_PROMO_NA.match(old):
        return 'Thiếu dữ liệu lịch sử điều chuyển/bổ nhiệm'
    return old


def _to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def main(path: str, dry_run: bool = False) -> int:
    if not os.path.exists(path):
        print(f'KHÔNG THẤY FILE: {path}')
        return 2

    with open(path, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    has_promo = 'reason_promo' in fields
    print(f'Đọc {len(rows):,} dòng · {len(fields)} cột · '
          f"{'5 yếu tố (có reason_promo)' if has_promo else '4 yếu tố (không có reason_promo)'}")

    changed = {'reason_freeze': 0, 'reason_promo': 0}
    samples: dict[str, list[tuple[str, str]]] = {'reason_freeze': [], 'reason_promo': []}

    for r in rows:
        if 'reason_freeze' in r:
            old = r['reason_freeze']
            new = new_freeze(old)
            if new != old:
                changed['reason_freeze'] += 1
                if len(samples['reason_freeze']) < 3:
                    samples['reason_freeze'].append((old, new))
                r['reason_freeze'] = new

        if has_promo:
            old = r['reason_promo']
            new = new_promo(old,
                            _to_int(r.get('months_since_last_move')),
                            _to_int(r.get('tenure_months')))
            if new != old:
                changed['reason_promo'] += 1
                if len(samples['reason_promo']) < 3:
                    samples['reason_promo'].append((old, new))
                r['reason_promo'] = new

    for col, n in changed.items():
        if n:
            print(f'\n{col}: đổi {n:,} dòng')
            for old, new in samples[col]:
                print(f'    - {old}\n    + {new}')

    if dry_run:
        print('\n[dry-run] Không ghi gì.')
        return 0

    bak = path + '.bak'
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f'\nĐã sao lưu → {bak}')
    else:
        print(f'\n{bak} đã tồn tại, giữ nguyên bản sao lưu cũ.')

    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    print(f'Đã ghi → {path}')

    return verify(bak, path)


def verify(before: str, after: str) -> int:
    """
    BẤT BIẾN: mọi cột không phải reason_* phải giống hệt, từng byte.
    Đây là chỗ chứng minh không con số nào bị đụng vào.
    """
    with open(before, encoding='utf-8', newline='') as fa, \
            open(after, encoding='utf-8', newline='') as fb:
        ra, rb = csv.DictReader(fa), csv.DictReader(fb)
        if ra.fieldnames != rb.fieldnames:
            print('LỖI: thứ tự/tên cột đã đổi.')
            return 1
        cols = [c for c in (ra.fieldnames or []) if not c.startswith('reason_')]
        n = 0
        for i, (a, b) in enumerate(zip(ra, rb), start=2):
            for c in cols:
                if a[c] != b[c]:
                    print(f'LỖI dòng {i}, cột {c}: {a[c]!r} → {b[c]!r}')
                    return 1
            n += 1

    print(f'KIỂM CHỨNG ĐẠT: {n:,} dòng, {len(cols)} cột không phải reason_* '
          f'giống hệt trước/sau. Không con số nào bị đụng vào.')
    return 0


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    target = args[0] if args else 'data/fact_flight_risk_score.csv'
    sys.exit(main(target, dry_run='--dry-run' in sys.argv))
