from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        valid = username == current_app.config["ADMIN_USERNAME"] and check_password_hash(
            current_app.config["ADMIN_PASSWORD_HASH"], password
        )
        if valid:
            session.clear()
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin.tournaments"))
        return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
