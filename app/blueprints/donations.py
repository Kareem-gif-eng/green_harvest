import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import execute, query
from ..helpers import notify, positive_number
from ..security import need

bp = Blueprint("donations", __name__)


def _owned_request(i, role):
    r = query("SELECT r.*,d.farmer_id,d.product FROM donation_requests r "
              "JOIN donations d ON d.id=r.donation_id WHERE r.id=?", (i,), one=True)
    if not r:
        abort(404)
    owner = r["farmer_id"] if role == "farmer" else r["charity_id"]
    if owner != g.user["id"]:
        abort(403)
    return r


@bp.route("/donations", methods=["GET", "POST"])
@need("farmer", "charity")
def index():
    u = g.user
    if request.method == "POST":
        if u["role"] != "farmer":
            abort(403)
        f = request.form
        qty = positive_number(f.get("qty_kg"))
        if not f.get("product", "").strip() or not qty:
            flash("المنتج والكمية مطلوبان.", "err")
        else:
            execute("INSERT INTO donations(farmer_id,product,qty_kg,city,available_from) VALUES(?,?,?,?,?)",
                    (u["id"], f["product"].strip(), qty, f.get("city"), f.get("available_from")))
            flash("تم نشر عرض التبرع.", "ok")
        return redirect(url_for("donations.index"))

    if u["role"] == "farmer":
        rows = query("SELECT * FROM donations WHERE farmer_id=? ORDER BY id DESC", (u["id"],))
        reqs = query("SELECT r.*,c.name charity,c.phone cphone FROM donation_requests r "
                     "JOIN users c ON c.id=r.charity_id JOIN donations d ON d.id=r.donation_id "
                     "WHERE d.farmer_id=? ORDER BY r.id DESC", (u["id"],))
    else:
        rows = query("SELECT d.*,f.name farmer FROM donations d JOIN users f ON f.id=d.farmer_id "
                     "WHERE d.status='available' ORDER BY d.id DESC")
        reqs = query("SELECT r.*,d.product,d.qty_kg,d.city,f.name farmer,f.phone fphone "
                     "FROM donation_requests r JOIN donations d ON d.id=r.donation_id "
                     "JOIN users f ON f.id=d.farmer_id WHERE r.charity_id=? ORDER BY r.id DESC", (u["id"],))
    return render_template("donations/index.html", rows=rows, reqs=reqs)


@bp.route("/donations/<int:i>/request", methods=["POST"])
@need("charity")
def request_donation(i):
    d = query("SELECT * FROM donations WHERE id=? AND status='available'", (i,), one=True)
    if not d:
        abort(404)
    try:
        execute("INSERT INTO donation_requests(donation_id,charity_id) VALUES(?,?)", (i, g.user["id"]))
    except sqlite3.IntegrityError:
        flash("طلبت هذا التبرع من قبل.", "err")
        return redirect(url_for("donations.index"))
    notify(d["farmer_id"], f"{g.user['name']} طلبت تبرعك ({d['product']}).", url_for("donations.index"))
    return redirect(url_for("donations.index"))


@bp.route("/requests/<int:i>/respond", methods=["POST"])
@need("farmer")
def respond(i):
    r = _owned_request(i, "farmer")
    if r["status"] != "requested":
        abort(400)
    if request.form.get("action") == "accept":
        execute("UPDATE donation_requests SET status='accepted' WHERE id=?", (i,))
        execute("UPDATE donation_requests SET status='declined' WHERE donation_id=? AND id<>? AND status='requested'",
                (r["donation_id"], i))
        execute("UPDATE donations SET status='reserved' WHERE id=?", (r["donation_id"],))
        notify(r["charity_id"], f"قُبل طلبك على {r['product']}. حدّد موعد الاستلام.", url_for("donations.index"))
    else:
        execute("UPDATE donation_requests SET status='declined' WHERE id=?", (i,))
        notify(r["charity_id"], f"رُفض طلبك على {r['product']}.", url_for("donations.index"))
    return redirect(url_for("donations.index"))


@bp.route("/requests/<int:i>/schedule", methods=["POST"])
@need("charity")
def schedule(i):
    r = _owned_request(i, "charity")
    if r["status"] != "accepted" or not request.form.get("pickup_time"):
        abort(400)
    execute("UPDATE donation_requests SET pickup_time=?,pickup_place=? WHERE id=?",
            (request.form["pickup_time"], request.form.get("pickup_place"), i))
    notify(r["farmer_id"], f"موعد استلام {r['product']}: {request.form['pickup_time']}.", url_for("donations.index"))
    return redirect(url_for("donations.index"))


@bp.route("/requests/<int:i>/collected", methods=["POST"])
@need("charity")
def collected(i):
    r = _owned_request(i, "charity")
    if r["status"] != "accepted":
        abort(400)
    execute("UPDATE donation_requests SET status='collected' WHERE id=?", (i,))
    execute("UPDATE donations SET status='collected' WHERE id=?", (r["donation_id"],))
    notify(r["farmer_id"], f"تم استلام {r['product']} فعلياً. شكراً لك!", url_for("donations.index"))
    return redirect(url_for("donations.index"))
