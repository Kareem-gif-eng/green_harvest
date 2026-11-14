from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import execute, query
from ..helpers import notify
from ..security import need

bp = Blueprint("orders", __name__)

LABELS = {"accepted": "قُبل", "rejected": "رُفض", "completed": "اكتمل", "cancelled": "أُلغي"}


@bp.route("/orders")
@need()
def index():
    base = ("SELECT o.*,p.name pname,p.price_per_kg,b.name buyer,b.phone bphone,"
            "s.name seller,s.phone sphone FROM orders o JOIN products p ON p.id=o.product_id "
            "JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=p.seller_id")
    return render_template(
        "orders/index.html",
        mine=query(base + " WHERE o.buyer_id=? ORDER BY o.id DESC", (g.user["id"],)),
        incoming=query(base + " WHERE p.seller_id=? ORDER BY o.id DESC", (g.user["id"],)),
    )


@bp.route("/orders/<int:i>/status", methods=["POST"])
@need()
def status(i):
    o = query("SELECT o.*,p.seller_id,p.name pname,p.available_kg FROM orders o "
              "JOIN products p ON p.id=o.product_id WHERE o.id=?", (i,), one=True)
    if not o:
        abort(404)
    new = request.form.get("status")
    me = g.user["id"]
    allowed = {"pending": {"accepted", "rejected"}, "accepted": {"completed", "rejected"}}
    if me == o["buyer_id"] and new == "cancelled" and o["status"] in ("pending", "accepted"):
        who = "buyer"
    elif me == o["seller_id"] and new in allowed.get(o["status"], ()):
        who = "seller"
    else:
        abort(403)

    if new == "accepted":
        if o["qty_kg"] > o["available_kg"]:
            flash("الكمية المتاحة لا تكفي الآن.", "err")
            return redirect(url_for("orders.index"))
        execute("UPDATE products SET available_kg=available_kg-? WHERE id=?", (o["qty_kg"], o["product_id"]))
    elif o["status"] == "accepted" and new in ("rejected", "cancelled"):
        execute("UPDATE products SET available_kg=available_kg+? WHERE id=?", (o["qty_kg"], o["product_id"]))

    if new in ("accepted", "rejected", "cancelled"):
        execute("UPDATE products SET status='sold_out' WHERE id=? AND status='active' AND available_kg<=0",
                (o["product_id"],))
        execute("UPDATE products SET status='active' WHERE id=? AND status='sold_out' AND available_kg>0",
                (o["product_id"],))

    execute("UPDATE orders SET status=? WHERE id=?", (new, i))
    recipient = o["buyer_id"] if who == "seller" else o["seller_id"]
    notify(recipient, f"الطلب على {o['pname']} {LABELS[new]}.", url_for("orders.index"))
    return redirect(url_for("orders.index"))
