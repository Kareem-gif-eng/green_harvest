"""أرقام لوحة الأثر، محسوبة من قاعدة البيانات مباشرة."""
from .db import query


def _scalar(sql):
    return query(sql, one=True)[0] or 0


def impact():
    return dict(
        offered=_scalar("SELECT COALESCE((SELECT SUM(quantity_kg) FROM products),0)"
                        "+COALESCE((SELECT SUM(qty_kg) FROM donations),0)"),
        sold=_scalar("SELECT COALESCE(SUM(qty_kg),0) FROM orders WHERE status='completed'"),
        agreed=_scalar("SELECT COALESCE(SUM(qty_kg),0) FROM donations WHERE status IN('reserved','collected')"),
        collected=_scalar("SELECT COALESCE(SUM(qty_kg),0) FROM donations WHERE status='collected'"),
        completed=_scalar("SELECT COUNT(*) FROM donations WHERE status='collected'"),
        farmers=_scalar("SELECT COUNT(*) FROM users WHERE role='farmer'"),
        charities=_scalar("SELECT COUNT(*) FROM users WHERE role='charity'"),
    )
