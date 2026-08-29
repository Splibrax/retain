# -*- coding: utf-8 -*-
"""
check_env.py — kiểm file .env đã đủ chưa.

CHỈ in TÊN biến và độ dài giá trị. KHÔNG BAO GIỜ in giá trị —
khoá bí mật không được lọt vào màn hình, log, hay cửa sổ chat.

    python check_env.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.llm import ALIASES, load_dotenv, _pick   # noqa: E402

names = load_dotenv()
print(f"Đọc .env: {len(names)} biến" if names else "KHÔNG thấy file .env ở thư mục này.")
if names:
    print("Tên biến có trong file:", ", ".join(sorted(set(names))))

print()
ok = True
for kind in ("base_url", "api_key", "model"):
    val, src = _pick(kind)
    if val:
        shown = val if kind != "api_key" else f"<đã ẩn, {len(val)} ký tự>"
        print(f"  ✓ {kind:<9} lấy từ biến {src:<20} = {shown}")
    else:
        ok = False
        print(f"  ✗ {kind:<9} CHƯA CÓ. Đặt một trong: {', '.join(ALIASES[kind])}")

print()
print("Đủ để chạy --real." if ok else "Chưa đủ. Bổ sung biến còn thiếu vào .env rồi chạy lại.")
