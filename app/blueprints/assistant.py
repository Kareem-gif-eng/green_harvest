"""المساعد الزراعي الذكي: محادثة نصية + صور متعددة، الرد من Gemini."""
import os
import uuid

from flask import (Blueprint, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from .. import gemini
from ..db import execute, query
from ..helpers import IMAGE_EXTS, looks_like_image
from ..security import need

bp = Blueprint("assistant", __name__)

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TEXT = 2000
HISTORY_TURNS = 10


def _error(message, status):
    return jsonify(ok=False, error=message), status


def _read_image(file):
    """يرجع (ext, bytes) للصورة الصالحة، أو None."""
    if "." not in file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_EXTS:
        return None
    data = file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES or not looks_like_image(data, ext):
        return None
    return ext, data


def _history(user_id):
    rows = query("SELECT role,text FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                 (user_id, HISTORY_TURNS))
    return [{"role": r["role"], "text": r["text"]} for r in reversed(rows)]


@bp.route("/assistant")
@need()
def page():
    uid = g.user["id"]
    messages = list(reversed(query(
        "SELECT * FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT 60", (uid,))))
    images = {}
    for r in query("SELECT i.message_id, i.filename FROM ai_images i "
                   "JOIN ai_messages m ON m.id=i.message_id WHERE m.user_id=? ORDER BY i.id", (uid,)):
        images.setdefault(r["message_id"], []).append(r["filename"])
    return render_template("assistant/index.html", messages=messages, images=images,
                           enabled=bool(current_app.config["GEMINI_API_KEY"]),
                           max_images=MAX_IMAGES,
                           model_name=current_app.config["GEMINI_MODEL"])


@bp.route("/assistant/message", methods=["POST"])
def message():
    if not g.user:
        return _error("لازم تسجّل دخول الأول.", 401)
    api_key = current_app.config["GEMINI_API_KEY"]
    if not api_key:
        return _error("خدمة المساعد الذكي مش مفعّلة دلوقتي. كلّم المدير.", 503)

    text = (request.form.get("text") or "").strip()
    if len(text) > MAX_TEXT:
        return _error(f"الرسالة طويلة. الحد الأقصى {MAX_TEXT} حرف.", 400)

    uploads = [f for f in request.files.getlist("images") if f and f.filename]
    if len(uploads) > MAX_IMAGES:
        return _error(f"تقدر ترفع {MAX_IMAGES} صور كحد أقصى في الرسالة الواحدة.", 400)
    if not text and not uploads:
        return _error("اكتب سؤالك أو صوّر النبات الأول.", 400)

    prepared = []
    for number, file in enumerate(uploads, 1):
        parsed = _read_image(file)
        if parsed is None:
            return _error(f"الصورة رقم {number} مش مقبولة. استخدم JPG أو PNG أو WEBP، وحجمها أقل من 5 ميجا.", 400)
        prepared.append(parsed)

    try:
        reply = gemini.generate_reply(api_key, current_app.config["GEMINI_MODEL"],
                                      _history(g.user["id"]), text, prepared)
    except gemini.GeminiError as exc:
        return _error(exc.message, exc.status)

    user_msg = execute("INSERT INTO ai_messages(user_id,role,text) VALUES(?,?,?)",
                       (g.user["id"], "user", text or "(صور بدون كلام)"))
    names = []
    for ext, data in prepared:
        name = f"c_{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(current_app.config["UPLOADS"], name), "wb") as out:
            out.write(data)
        execute("INSERT INTO ai_images(message_id,filename) VALUES(?,?)", (user_msg, name))
        names.append(name)
    bot_msg = execute("INSERT INTO ai_messages(user_id,role,text) VALUES(?,?,?)",
                      (g.user["id"], "assistant", reply))
    return jsonify(ok=True, reply=reply, id=bot_msg, images=names)


@bp.route("/assistant/reset", methods=["POST"])
@need()
def reset():
    rows = query("SELECT i.filename FROM ai_images i JOIN ai_messages m ON m.id=i.message_id "
                 "WHERE m.user_id=?", (g.user["id"],))
    for r in rows:
        try:
            os.remove(os.path.join(current_app.config["UPLOADS"], r["filename"]))
        except OSError:
            pass
    execute("DELETE FROM ai_messages WHERE user_id=?", (g.user["id"],))  # الصور بتتمسح بالـ CASCADE
    flash("تم مسح المحادثة.", "ok")
    return redirect(url_for("assistant.page"))
