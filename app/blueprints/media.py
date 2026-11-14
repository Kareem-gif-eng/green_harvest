from flask import Blueprint, current_app, g, abort, send_from_directory

from ..db import query

bp = Blueprint("media", __name__)


@bp.route("/uploads/<path:name>")
def uploaded(name):
    """صور التشخيص خاصة بصاحبها والمدير؛ صور المنتجات عامة."""
    if name.startswith("d_"):
        row = query("SELECT user_id FROM diagnoses WHERE image=?", (name,), one=True)
        if not g.user or not row or (row["user_id"] != g.user["id"] and g.user["role"] != "admin"):
            abort(403)
    if name.startswith("c_"):
        row = query("SELECT m.user_id FROM ai_images i JOIN ai_messages m ON m.id=i.message_id "
                    "WHERE i.filename=?", (name,), one=True)
        if not g.user or not row or row["user_id"] != g.user["id"]:
            abort(403)
    return send_from_directory(current_app.config["UPLOADS"], name)
