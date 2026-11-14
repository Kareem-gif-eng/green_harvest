"""نقطة تشغيل المشروع: python run.py"""
import os
import sys

if sys.version_info < (3, 10):
    sys.exit("GreenHarvest يحتاج Python 3.10 أو أحدث. الإصدار الحالي: " + sys.version.split()[0])

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("DEBUG") == "1")
