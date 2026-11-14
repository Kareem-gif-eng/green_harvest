from datetime import date, timedelta

from flask import Blueprint, g, render_template

from ..db import query
from ..security import need

bp = Blueprint("farm_calendar", __name__)


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@bp.route("/calendar")
@need("farmer")
def index():
    today = date.today()
    items, missing = [], []
    crops = query("SELECT * FROM crops WHERE user_id=? ORDER BY id DESC", (g.user["id"],))
    for c in crops:
        planted = _parse_date(c["planting_date"])
        if not planted or not c["harvest_days"]:
            missing.append(c)
            continue
        harvest = planted + timedelta(days=c["harvest_days"])
        items.append({"crop": c, "planted": planted, "harvest": harvest, "left": (harvest - today).days})
    items.sort(key=lambda x: x["harvest"])
    return render_template("calendar/index.html", items=items, missing=missing, today=today)
