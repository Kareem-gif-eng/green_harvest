"""مصنع التطبيق: create_app()."""
import logging
import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, g, render_template, session

from .db import close_db, init_db, query
from .security import ROLES, csrf_input, load_user

PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:  # python-dotenv اختياري: لو مش مثبت التطبيق بيشتغل بمتغيرات البيئة
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def _project_path(value, default):
    """المسارات النسبية بتتحسب من جذر المشروع مش من مكان التشغيل."""
    value = value or default
    return value if os.path.isabs(value) else str(PROJECT_ROOT / value)


def create_app(db_path=None, uploads_dir=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DB=db_path or _project_path(os.environ.get("DATABASE"), "greenharvest.db"),
        UPLOADS=uploads_dir or _project_path(os.environ.get("UPLOADS"), "uploads"),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,  # يكفي لـ 4 صور مع الحد الأقصى لكل صورة
        GEMINI_API_KEY=os.environ.get("GEMINI_API_KEY", "").strip(),
        GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.8-flash",
    )
    os.makedirs(app.config["UPLOADS"], exist_ok=True)
    if not app.config["GEMINI_API_KEY"]:
        logging.getLogger("greenharvest").warning(
            "GEMINI_API_KEY مش متظبط، فالمساعد الزراعي مش هيشتغل. "
            "ضيف السطر GEMINI_API_KEY=... في ملف .env وأعد تشغيل التطبيق.")
    init_db(app.config["DB"])

    app.teardown_appcontext(close_db)
    app.before_request(load_user)

    @app.context_processor
    def inject_globals():
        unread = 0
        if g.get("user"):
            unread = query("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0",
                           (g.user["id"],), one=True)["c"]
        return dict(user=g.get("user"), unread=unread, ROLES=ROLES, csrf_field=csrf_input(),
                    csrf_token=session.get("csrf", ""))

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(413)
    @app.errorhandler(404)
    @app.errorhandler(405)
    def http_error(e):
        return render_template("errors/error.html", e=e), e.code

    from .blueprints import (assistant, auth, dashboard, diagnosis, donations,
                             farm_calendar, main, market, media, notifications, orders)
    for module in (main, auth, dashboard, media, diagnosis, market, orders, donations,
                   notifications, farm_calendar, assistant):
        app.register_blueprint(module.bp)

    @app.cli.command("create-admin")
    def create_admin():
        """إنشاء حساب مدير: flask --app run create-admin"""
        import getpass
        from werkzeug.security import generate_password_hash
        from .db import execute

        email = input("Admin email: ").strip().lower()
        password = getpass.getpass("Password (8+): ")
        if len(password) < 8:
            print("كلمة المرور لازم تكون 8 أحرف على الأقل.")
            return
        try:
            execute("INSERT INTO users(name,email,pw,role) VALUES('Admin',?,?,'admin')",
                    (email, generate_password_hash(password)))
        except sqlite3.IntegrityError:
            print("هذا البريد مسجّل بالفعل.")
            return
        print("تم إنشاء حساب المدير.")

    return app
