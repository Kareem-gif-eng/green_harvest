from flask import Blueprint, g, redirect, render_template, request, url_for

from ..db import execute, query
from ..security import need

bp = Blueprint("notifications", __name__)


@bp.route("/notifications", methods=["GET", "POST"])
@need()
def index():
    if request.method == "POST":
        execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],))
        return redirect(url_for("notifications.index"))
    rows = query("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", (g.user["id"],))
    return render_template("notifications/index.html", rows=rows)
