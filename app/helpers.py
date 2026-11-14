"""دوال مساعدة مشتركة بين الـ blueprints."""
import os
import uuid

from flask import abort, current_app

from .db import execute, query

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}


def notify(user_id, text, link):
    execute("INSERT INTO notifications(user_id,text,link) VALUES(?,?,?)", (user_id, text, link))


def positive_number(value):
    try:
        x = float(value)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def looks_like_image(data, ext):
    """يتأكد من محتوى الملف (التوقيع) وليس من الامتداد فقط."""
    if ext == "png":
        return data.startswith(b"\x89PNG")
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def save_image(file, prefix):
    """يحفظ الصورة ويرجع اسمها، أو None لو الملف مش صورة صالحة."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_EXTS:
        return None
    data = file.read()
    if not looks_like_image(data, ext):
        return None
    name = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(current_app.config["UPLOADS"], name), "wb") as out:
        out.write(data)
    return name


def owned_row(sql, id_, owner_field, owner_id):
    """يجيب السجل ويتأكد إن المستخدم صاحبه، وإلا 404 أو 403."""
    row = query(sql, (id_,), one=True)
    if not row:
        abort(404)
    if row[owner_field] != owner_id:
        abort(403)
    return row
