import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import execute, query

bp = Blueprint("auth", __name__)
PUBLIC_ROLES = ("farmer", "charity")  # المدير مش بيتسجل من الموقع


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        role = f.get("role")
        name = f.get("name", "").strip()
        email = f.get("email", "").strip().lower()
        if role not in PUBLIC_ROLES or not name or "@" not in email:
            flash("أكمل الاسم والبريد ونوع الحساب.", "err")
        elif len(f.get("password", "")) < 8:
            flash("كلمة المرور يجب ألا تقل عن 8 أحرف.", "err")
        else:
            try:
                uid = execute(
                    "INSERT INTO users(name,email,pw,role,phone,city) VALUES(?,?,?,?,?,?)",
                    (name, email, generate_password_hash(f["password"]), role, f.get("phone"), f.get("city")),
                )
            except sqlite3.IntegrityError:
                flash("هذا البريد مسجّل بالفعل.", "err")
            else:
                session.clear()
                session["uid"] = uid
                return redirect(url_for("dashboard.home"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = query("SELECT * FROM users WHERE email=?",
                     (request.form.get("email", "").strip().lower(),), one=True)
        if user and check_password_hash(user["pw"], request.form.get("password", "")):
            session.clear()
            session["uid"] = user["id"]
            return redirect(url_for("dashboard.home"))
        flash("البريد أو كلمة المرور غير صحيحة.", "err")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.index"))
