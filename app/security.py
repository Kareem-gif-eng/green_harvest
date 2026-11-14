"""المستخدم الحالي، الصلاحيات، وحماية CSRF."""
import secrets
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from markupsafe import Markup

from .db import query

ROLES = {"farmer": "مزارع", "charity": "جمعية خيرية", "admin": "مدير"}

# مفيش نقاط نهاية معفاة من CSRF
CSRF_EXEMPT_ENDPOINTS = set()


def load_user():
    session.setdefault("csrf", secrets.token_hex(16))
    g.user = query("SELECT * FROM users WHERE id=?", (session["uid"],), one=True) if session.get("uid") else None
    if (request.method == "POST" and request.endpoint not in CSRF_EXEMPT_ENDPOINTS
            and (request.form.get("_csrf") or request.headers.get("X-CSRF-Token")) != session["csrf"]):
        abort(400)


def need(*roles):
    """يتطلب تسجيل الدخول، ولو فيه أدوار محددة يتطلب إنها تكون من ضمنها."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not g.user:
                return redirect(url_for("auth.login"))
            if roles and g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def csrf_input():
    return Markup('<input type="hidden" name="_csrf" value="%s">' % session["csrf"])
