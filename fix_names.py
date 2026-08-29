# -*- coding: utf-8 -*-
"""
fix_names.py — chuẩn hoá full_name trong data/dim_employee.csv về đúng kiểu Việt.

Hai lỗi cần sửa (do thư viện sinh tên để lại):
  1. Còn dính kính ngữ ở đầu:  "Bà Thảo Trần"  → bỏ "Bà"
  2. Sai thứ tự (tên trước họ): "Thảo Trần"     → "Trần Thảo"

CHỈ đụng cột full_name. Mọi cột khác giữ nguyên byte-for-byte.

Chạy (đứng ở thư mục retain):
    python fix_names.py            # xem trước, KHÔNG ghi gì
    python fix_names.py --apply    # ghi, có backup tự động
"""
import csv
import os
import shutil
import sys
from collections import Counter

SRC = os.path.join("data", "dim_employee.csv")

# Kính ngữ thư viện hay gắn ở ĐẦU chuỗi.
# Lưu ý: "Anh", "Chị", "Cô", "Em" cũng là tên thật của người Việt — nhưng khi là
# tên thật chúng đứng CUỐI (Nguyễn Thị Anh), không đứng đầu. Chỉ bỏ ở vị trí đầu.
PREFIXES = {"Ông", "Bà", "Anh", "Chị", "Cô", "Chú", "Bác", "Em", "Ngài"}

# Họ phổ biến của người Việt — dùng để BIẾT tên đang ở thứ tự nào,
# thay vì đảo mù (đảo mù sẽ phá hỏng những dòng vốn đã đúng).
SURNAMES = {
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
    "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Đào", "Đoàn",
    "Trương", "Lâm", "Mai", "Tô", "Trịnh", "Cao", "Chu", "Lưu", "Tạ", "Hà",
    "Kiều", "Thái", "Quách", "Vương", "La", "Tống", "Từ", "Bạch", "Chử",
    "Nghiêm", "Xuân", "Bành", "Ninh", "Khổng", "Lã", "Lại", "Hứa",
}

AMBIGUOUS: list[str] = []      # tên không đoán được thứ tự → để nguyên, báo cáo


def fix(name: str) -> str:
    if not name or not name.strip():
        return name
    parts = name.strip().split()

    # 1. bỏ kính ngữ ở đầu, chỉ khi phần còn lại vẫn đủ ≥2 từ
    if len(parts) >= 3 and parts[0] in PREFIXES:
        parts = parts[1:]

    if len(parts) < 2:
        return " ".join(parts)

    # 2. quyết định theo VỊ TRÍ CỦA HỌ, không đảo mù
    if parts[-1] in SURNAMES:
        # họ đang ở cuối → thứ tự Tây → đảo lên đầu
        parts = [parts[-1]] + parts[:-1]
    elif parts[0] in SURNAMES:
        pass                      # đã đúng thứ tự Việt → GIỮ NGUYÊN
    else:
        AMBIGUOUS.append(" ".join(parts))   # không rõ → giữ nguyên, báo cáo

    return " ".join(parts)


def main():
    apply = "--apply" in sys.argv

    if not os.path.exists(SRC):
        sys.exit(f"Không thấy {SRC}. Phải đứng ở thư mục retain khi chạy.")

    with open(SRC, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    if "full_name" not in fields:
        sys.exit("File không có cột full_name — dừng, không đụng gì.")

    changed = []
    for r in rows:
        old = r["full_name"]
        new = fix(old)
        if new != old:
            changed.append((old, new))
        r["full_name"] = new

    # ── báo cáo ──────────────────────────────────────────────────────────
    print(f"Tổng số dòng      : {len(rows)}")
    print(f"Số tên bị đổi     : {len(changed)}")

    dup_before = sum(c - 1 for c in Counter(o for o, _ in changed).values() if c > 1)
    names_after = Counter(r["full_name"] for r in rows)
    dup_after = sum(c - 1 for c in names_after.values() if c > 1)
    print(f"Tên trùng sau khi đổi: {dup_after}  "
          f"(trùng là bình thường với dữ liệu giả, chỉ cần không tăng vọt)")

    print("\n30 ví dụ TRƯỚC → SAU:")
    for old, new in changed[:30]:
        print(f"   {old:<28} → {new}")

    # cảnh báo nếu còn sót kính ngữ ở đầu
    leftover = [r["full_name"] for r in rows
                if r["full_name"].split() and r["full_name"].split()[0] in PREFIXES]
    if leftover:
        print(f"\n⚠️  Còn {len(leftover)} tên bắt đầu bằng từ trong danh sách kính ngữ.")
        print("   Có thể là tên thật — xem qua rồi quyết:", leftover[:10])

    if AMBIGUOUS:
        uniq = sorted(set(AMBIGUOUS))
        print(f"\n⚠️  {len(AMBIGUOUS)} tên KHÔNG đoán được thứ tự (không từ nào là họ phổ biến).")
        print("   Đã GIỮ NGUYÊN, không đụng vào. Xem thử:", uniq[:10])
        print("   Nếu nhiều, bổ sung họ còn thiếu vào SURNAMES rồi chạy lại.")

    if not apply:
        print("\n── XEM TRƯỚC, chưa ghi gì ──")
        print("Nhìn 30 dòng trên. Nếu đúng kiểu Việt rồi thì chạy lại:")
        print("    python fix_names.py --apply")
        return

    # ── ghi, có backup ───────────────────────────────────────────────────
    bak = SRC + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(SRC, bak)
        print(f"\nĐã sao lưu bản gốc: {bak}")
    else:
        print(f"\n{bak} đã tồn tại — giữ nguyên bản sao lưu đầu tiên.")

    with open(SRC, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Đã ghi {SRC} ({len(rows)} dòng).")
    print("\nChạy lại để kiểm tra:")
    print("    python -m pytest tests\\ -q     # vẫn phải 21 passed")
    print("    python demo_smoke.py           # tên ở cảnh 1 phải đúng kiểu Việt")


if __name__ == "__main__":
    main()
