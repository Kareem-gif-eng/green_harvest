from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import execute, query
from ..helpers import owned_row
from ..security import need

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@need()
def home():
    u = g.user
    ctx = {}
    if u["role"] == "farmer":
        ctx["crops"] = query("SELECT * FROM crops WHERE user_id=? ORDER BY id DESC", (u["id"],))
        ctx["diags"] = query("SELECT COUNT(*) c FROM diagnoses WHERE user_id=?", (u["id"],), one=True)["c"]
        ctx["prods"] = query("SELECT COUNT(*) c FROM products WHERE seller_id=?", (u["id"],), one=True)["c"]
    elif u["role"] == "admin":
        ctx["users"] = query("SELECT id,name,email,role,city,created FROM users ORDER BY id DESC")
    return render_template("dashboard/home.html", **ctx)


@bp.route("/crops", methods=["POST"])
@need("farmer")
def crop_add():
    f = request.form
    name = f.get("name", "").strip()
    if not name:
        flash("اسم المحصول مطلوب.", "err")
        return redirect(url_for("dashboard.home"))
    days = f.get("harvest_days", "").strip()
    harvest_days = int(days) if days.isdigit() and 0 < int(days) <= 730 else None
    execute(
        "INSERT INTO crops(user_id,name,planting_date,field,notes,harvest_days) VALUES(?,?,?,?,?,?)",
        (g.user["id"], name, f.get("planting_date") or None, f.get("field"), f.get("notes"), harvest_days),
    )
    flash("تمت إضافة المحصول.", "ok")
    return redirect(url_for("dashboard.home"))


@bp.route("/crops/<int:i>/delete", methods=["POST"])
@need("farmer")
def crop_delete(i):
    owned_row("SELECT * FROM crops WHERE id=?", i, "user_id", g.user["id"])
    execute("DELETE FROM crops WHERE id=?", (i,))
    return redirect(url_for("dashboard.home"))
