
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

# تحميل ملف .env محليًا إن وُجد، دون الاعتماد عليه في بيئة الإنتاج.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def _project_path(value, default):
    """تحويل المسارات النسبية إلى مسارات تبدأ من جذر المشروع."""
    value = value or default
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def create_app(db_path=None, uploads_dir=None):
    app = Flask(__name__)

    is_vercel = os.environ.get("VERCEL") == "1"

    # Vercel يسمح بالكتابة داخل /tmp فقط.
    if is_vercel:
        default_db = "/tmp/greenharvest.db"
        default_uploads = "/tmp/greenharvest_uploads"
    else:
        default_db = _project_path(None, "greenharvest.db")
        default_uploads = _project_path(None, "uploads")

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),

        DB=db_path or _project_path(
            os.environ.get("DATABASE"),
            default_db
        ) if not db_path else db_path,

        UPLOADS=uploads_dir or (
            os.environ.get("UPLOADS")
            if os.environ.get("UPLOADS") and os.path.isabs(os.environ["UPLOADS"])
            else _project_path(os.environ.get("UPLOADS"), default_uploads)
        ),

        MAX_CONTENT_LENGTH=25 * 1024 * 1024,

        GEMINI_API_KEY=os.environ.get("GEMINI_API_KEY", "").strip(),
        GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "").strip()
        or "gemini-3.8-flash",
    )

    # إنشاء مجلد الرفع وقاعدة البيانات في المسار المسموح.
    os.makedirs(app.config["UPLOADS"], exist_ok=True)

    if not app.config["GEMINI_API_KEY"]:
        logging.getLogger("greenharvest").warning(
            "GEMINI_API_KEY مش مضبوط؛ المساعد الذكي لن يعمل."
        )

    # تهيئة قاعدة البيانات.
    init_db(app.config["DB"])

    app.teardown_appcontext(close_db)
    app.before_request(load_user)

    @app.context_processor
    def inject_globals():
        unread = 0

        if g.get("user"):
            result = query(
                """
                SELECT COUNT(*) AS c
                FROM notifications
                WHERE user_id = ? AND is_read = 0
                """,
                (g.user["id"],),
                one=True,
            )
            unread = result["c"] if result else 0

        return {
            "user": g.get("user"),
            "unread": unread,
            "ROLES": ROLES,
            "csrf_field": csrf_input(),
            "csrf_token": session.get("csrf", ""),
        }

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(413)
    @app.errorhandler(404)
    @app.errorhandler(405)
    def http_error(error):
        return render_template("errors/error.html", e=error), error.code

    from .blueprints import (
        assistant,
        auth,
        dashboard,
        diagnosis,
        donations,
        farm_calendar,
        main,
        market,
        media,
        notifications,
        orders,
    )

    blueprints = (
        main,
        auth,
        dashboard,
        media,
        diagnosis,
        market,
        orders,
        donations,
        notifications,
        farm_calendar,
        assistant,
    )

    for module in blueprints:
        app.register_blueprint(module.bp)

    @app.cli.command("create-admin")
    def create_admin():
        """إنشاء حساب مدير."""
        import getpass

        from werkzeug.security import generate_password_hash
        from .db import execute

        email = input("Admin email: ").strip().lower()
        password = getpass.getpass("Password (8+): ")

        if len(password) < 8:
            print("كلمة المرور لازم تكون 8 أحرف على الأقل.")
            return

        try:
            execute(
                "INSERT INTO users(name,email,pw,role) VALUES('Admin',?,?,'admin')",
                (email, generate_password_hash(password)),
            )
        except sqlite3.IntegrityError:
            print("هذا البريد مسجّل بالفعل.")
            return

        print("تم إنشاء حساب المدير.")

    return app
