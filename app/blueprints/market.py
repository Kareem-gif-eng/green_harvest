from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import execute, query
from ..helpers import notify, owned_row, positive_number, save_image
from ..security import need

bp = Blueprint("market", __name__)


@bp.route("/market")
def index():
    a = request.args
    sql = ("SELECT p.*,u.name seller FROM products p JOIN users u ON u.id=p.seller_id "
           "WHERE p.status='active'")
    params = []
    if a.get("q"):
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params += [f"%{a['q']}%"] * 2
    if a.get("crop"):
        sql += " AND p.crop LIKE ?"
        params.append(f"%{a['crop']}%")
    if a.get("city"):
        sql += " AND p.city LIKE ?"
        params.append(f"%{a['city']}%")
    if positive_number(a.get("max_price")):
        sql += " AND p.price_per_kg<=?"
        params.append(positive_number(a["max_price"]))
    rows = query(sql + " ORDER BY p.id DESC", params)
    return render_template("market/index.html", rows=rows, a=a)


@bp.route("/market/new", methods=["GET", "POST"])
@bp.route("/market/<int:i>/edit", methods=["GET", "POST"])
@need("farmer")
def product_form(i=None):
    pr = owned_row("SELECT * FROM products WHERE id=?", i, "seller_id", g.user["id"]) if i else None
    if request.method == "POST":
        f = request.form
        qty = positive_number(f.get("quantity_kg"))
        try:
            price = float(f.get("price_per_kg", ""))
            price_ok = price >= 0
        except ValueError:
            price, price_ok = 0.0, False
        if not f.get("name", "").strip() or not qty or not price_ok:
            flash("الاسم والكمية (أكبر من صفر) والسعر مطلوبة.", "err")
            return render_template("market/form.html", p=pr)
        upload = request.files.get("image")
        new_img = save_image(upload, "p")
        if upload and upload.filename and not new_img:
            flash("الصورة غير صالحة. ارفع ملف png أو jpg أو webp.", "err")
            return render_template("market/form.html", p=pr)
        img = new_img or (pr["image"] if pr else None)
        name = f["name"].strip()
        harvest = f.get("harvest_date") or None
        if pr:
            # تعديل الكمية بيحافظ على الجزء اللي اتباع (المتاح = المتاح + الفرق)
            execute(
                "UPDATE products SET name=?,crop=?,quantity_kg=?,available_kg=MAX(0,available_kg+?-quantity_kg),"
                "price_per_kg=?,city=?,harvest_date=?,description=?,image=? WHERE id=?",
                (name, f.get("crop"), qty, qty, price, f.get("city"), harvest, f.get("description"), img, i),
            )
        else:
            execute(
                "INSERT INTO products(name,crop,quantity_kg,available_kg,price_per_kg,city,harvest_date,"
                "description,image,seller_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (name, f.get("crop"), qty, qty, price, f.get("city"), harvest, f.get("description"), img, g.user["id"]),
            )
        flash("تم حفظ المنتج.", "ok")
        return redirect(url_for("market.index"))
    return render_template("market/form.html", p=pr)


@bp.route("/market/<int:i>")
def detail(i):
    p = query("SELECT p.*,u.name seller FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?",
              (i,), one=True)
    if not p:
        abort(404)
    return render_template("market/detail.html", p=p)


@bp.route("/market/<int:i>/delete", methods=["POST"])
@need("farmer")
def product_delete(i):
    owned_row("SELECT * FROM products WHERE id=?", i, "seller_id", g.user["id"])
    execute("DELETE FROM products WHERE id=?", (i,))
    return redirect(url_for("market.index"))


@bp.route("/market/<int:i>/order", methods=["POST"])
@need()
def order_add(i):
    p = query("SELECT * FROM products WHERE id=? AND status='active'", (i,), one=True)
    if not p:
        abort(404)
    if p["seller_id"] == g.user["id"] or g.user["role"] == "admin":
        abort(403)
    qty = positive_number(request.form.get("qty_kg"))
    if not qty or qty > p["available_kg"]:
        flash("الكمية غير صالحة أو أكبر من المتاح.", "err")
        return redirect(url_for("market.detail", i=i))
    execute("INSERT INTO orders(product_id,buyer_id,qty_kg,note) VALUES(?,?,?,?)",
            (i, g.user["id"], qty, request.form.get("note")))
    notify(p["seller_id"], f"طلب شراء جديد على {p['name']} ({qty:g} كجم).", url_for("orders.index"))
    flash("أُرسل طلبك للبائع. الدفع والتسليم يتمان بينكما مباشرة (لا يوجد دفع إلكتروني).", "ok")
    return redirect(url_for("orders.index"))
