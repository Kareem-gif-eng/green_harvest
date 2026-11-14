import os

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from ..ai import run_ai
from ..db import execute, query
from ..helpers import notify, save_image
from ..security import need

bp = Blueprint("diagnosis", __name__)


@bp.route("/diagnose", methods=["GET", "POST"])
@need("farmer")
def diagnose():
    if request.method == "POST":
        f = request.form
        crop = f.get("crop", "").strip()
        img = save_image(request.files.get("image"), "d") if crop else None
        if not crop or not img:
            flash("اختر المحصول وأرفق صورة (png/jpg/webp).", "err")
            return redirect(url_for("diagnosis.diagnose"))
        diag_id = execute(
            "INSERT INTO diagnoses(user_id,crop,symptoms,image) VALUES(?,?,?,?)",
            (g.user["id"], crop, f.get("symptoms"), img),
        )
        try:
            result = run_ai(os.path.join(current_app.config["UPLOADS"], img), crop, f.get("symptoms"))
        except NotImplementedError:
            result = None
        if result:
            execute("UPDATE diagnoses SET status='done',result=?,confidence=?,advice=? WHERE id=?",
                    (result["result"], result["confidence"], result["advice"], diag_id))
            notify(g.user["id"], "ظهرت نتيجة تشخيص جديدة.", url_for("diagnosis.diagnose"))
        else:
            flash("تم حفظ الطلب. التشخيص الآلي لسه مش متاح، اسأل مساعدك الزراعي عن المشكلة دي.", "ok")
        return redirect(url_for("diagnosis.diagnose"))
    rows = query("SELECT * FROM diagnoses WHERE user_id=? ORDER BY id DESC", (g.user["id"],))
    return render_template("diagnosis/diagnose.html", rows=rows)
