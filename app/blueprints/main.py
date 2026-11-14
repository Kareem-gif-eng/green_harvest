from flask import Blueprint, render_template

from ..stats import impact

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("public/index.html", s=impact())


@bp.route("/impact")
def impact_page():
    return render_template("public/impact.html", s=impact())
