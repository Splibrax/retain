# -*- coding: utf-8 -*-
"""
run_local.py — chat với agent ngay trong terminal, không cần dựng server.

    python run_local.py                    # mock, không cần model, không tốn token
    python run_local.py --actor A002       # đổi vai để thử phân quyền
    python run_local.py --real             # gọi model thật (cần .env)
    python run_local.py --scenario         # chạy tự động 4 cảnh demo
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

from agent import runtime          # noqa: E402
from agent.llm import make_llm     # noqa: E402

SCENES = [
    ("A001", "Team mình tháng này có ai đang có dấu hiệu muốn đi không?"),
    ("A001", "Sao bạn E001881 lại bị chấm cao thế?"),
    ("A001", "Giờ mình nên làm gì với bạn ấy?"),
    ("A001", "Nếu kéo lương bạn ấy về đúng mức thị trường thì rủi ro còn bao nhiêu?"),
    ("A002", "Bên team anh Minh có bạn nào đang lung lay không, để anh còn liệu?"),
]


def show(actor, q, r):
    print(f"\n\033[36m[{actor}] {q}\033[0m")
    print(r["answer"])
    meta = (f"  · tool: {[c['name'] for c in r['tool_calls']] or 'không gọi'}"
            f" · guard: {'ĐẠT' if r['verified'] else 'HỎNG'}"
            f"{' (đã viết lại)' if r.get('retried') else ''}"
            f" · scope: {r.get('scope_size')} đơn vị")
    if r["usage"].get("prompt"):
        meta += f" · token: {r['usage']['prompt']}+{r['usage']['completion']}"
    dropped = [c for c in r["tool_calls"] if c.get("dropped_params")]
    if dropped:
        meta += f" · ⚠️ model cố truyền tham số phạm vi: {dropped}"
    print(f"\033[90m{meta}\033[0m")
    # Khi guard bắt viết lại, in ra CÁI GÌ đã kích hoạt — để chỉnh prompt cho trúng
    # thay vì đoán. Mỗi lần viết lại tốn thêm một lượt gọi model.
    if r.get("retried"):
        g = r.get("guard_report", {})
        first = r.get("first_draft_report", {})
        det = first or g
        print(f"\033[33m  ↳ guard bắt viết lại — số không truy được: "
              f"{det.get('unverified_numbers')} · cụm từ: {det.get('forbidden_phrases')}\033[0m")


def main():
    real = "--real" in sys.argv
    llm = make_llm(mock=not real)
    print(f"Model: {'THẬT (' + str(getattr(llm,'model','?')) + ')' if real else 'MOCK — không gọi mạng'}")

    if "--scenario" in sys.argv:
        # Giữ lịch sử RIÊNG cho từng actor — demo là hội thoại liên tục,
        # người quản lý nói "bạn ấy" ở câu 3 và trông chờ agent nhớ câu 2.
        hist: dict = {}
        for actor, q in SCENES:
            h = hist.setdefault(actor, [])
            r = runtime.answer(llm, actor, q, h)
            show(actor, q, r)
            h += [{"role": "user", "content": q},
                  {"role": "assistant", "content": r["answer"]}]
        return

    actor = "A001"
    if "--actor" in sys.argv:
        actor = sys.argv[sys.argv.index("--actor") + 1]
    print(f"Đang đóng vai {actor}. Gõ câu hỏi, Ctrl+C để thoát.\n")
    history = []
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            continue
        r = runtime.answer(llm, actor, q, history)
        show(actor, q, r)
        history += [{"role": "user", "content": q},
                    {"role": "assistant", "content": r["answer"]}]


if __name__ == "__main__":
    main()
