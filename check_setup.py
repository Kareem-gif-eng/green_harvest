"""فحص سريع للإعداد: شغّله أولاً لو المشروع مش بيشتغل.

    python check_setup.py

بيطبع إيه اللي ناقص بالظبط، ولو كل حاجة تمام بيقولك "كل شيء جاهز".
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
problems = []


def check(ok, good, bad):
    print(("  ✔ " if ok else "  ✘ ") + (good if ok else bad))
    if not ok:
        problems.append(bad)


print("== بيئة التشغيل")
print("  مجلد التشغيل:", os.getcwd())
print("  مجلد المشروع:", ROOT)
check(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "لازم Python 3.10 أو أحدث")

print("== الملفات")
required = [
    "run.py", "schema.sql", "requirements.txt",
    "app/__init__.py", "app/db.py", "app/security.py", "app/helpers.py",
    "app/ai.py", "app/stats.py",
    "app/templates/base.html", "app/templates/public/index.html",
    "app/static/css/style.css",
]
for rel in required:
    check((ROOT / rel).exists(), rel, f"ملف ناقص: {rel}")

print("== المكتبات")
for mod in ("flask", "dotenv", "werkzeug"):
    try:
        __import__(mod)
        check(True, mod, "")
    except ImportError:
        check(False, "", f"مكتبة مش مثبتة: {mod} (شغّل: pip install -r requirements.txt)")

if not problems:
    print("== تشغيل اختباري للتطبيق")
    try:
        sys.path.insert(0, str(ROOT))
        from app import create_app
        app = create_app(os.path.join(tempfile.mkdtemp(), "check.db"),
                         uploads_dir=tempfile.mkdtemp())
        with app.test_client() as c:
            status = c.get("/").status_code
            check(status == 200, f"الصفحة الرئيسية ترجع {status}", f"الصفحة الرئيسية ترجع {status}")
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        problems.append(str(exc))
        print("  ✘ التطبيق مش بيقوم:", exc)

print()
if problems:
    print("فيه مشاكل لازم تتحل:")
    for p in problems:
        print(" -", p)
    print("انسخ الرسائل دي وابعتهالي.")
else:
    print("كل شيء جاهز. شغّل: python run.py ثم افتح http://127.0.0.1:5000")
