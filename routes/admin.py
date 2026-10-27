from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from db import get_db
from randomizer import generate_match_schedule
from routes.auth import login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


def tournament_required(view):
    """Ensures an active tournament is selected in the session and makes it
    available as `g.tournament` for the view."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        db = get_db()
        tournament = None
        tournament_id = session.get("tournament_id")
        if tournament_id:
            tournament = db.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,)).fetchone()
        if tournament is None:
            session.pop("tournament_id", None)
            flash("Select or create a tournament first.", "error")
            return redirect(url_for("admin.tournaments"))
        g.tournament = tournament
        return view(*args, **kwargs)

    return wrapped


@bp.route("/")
@login_required
def index():
    if session.get("tournament_id"):
        return redirect(url_for("admin.players"))
    return redirect(url_for("admin.tournaments"))


# ---------- Tournaments ----------

@bp.route("/tournaments", methods=["GET", "POST"])
@login_required
def tournaments():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Tournament name cannot be empty.", "error")
            else:
                cur = db.execute("INSERT INTO tournaments (name) VALUES (?)", (name,))
                db.commit()
                session["tournament_id"] = cur.lastrowid
                flash(f"Tournament '{name}' created and selected.", "success")
                return redirect(url_for("admin.players"))

        elif action == "select":
            row = db.execute(
                "SELECT id FROM tournaments WHERE id = ?", (request.form.get("tournament_id"),)
            ).fetchone()
            if row:
                session["tournament_id"] = row["id"]
                flash("Switched active tournament.", "success")
                return redirect(url_for("admin.players"))
            flash("Tournament not found.", "error")

        elif action == "delete":
            tournament_id = request.form.get("tournament_id")
            db.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
            db.commit()
            if str(session.get("tournament_id")) == str(tournament_id):
                session.pop("tournament_id", None)
            flash("Tournament deleted.", "success")

        return redirect(url_for("admin.tournaments"))

    all_tournaments = db.execute("SELECT * FROM tournaments ORDER BY created_at DESC").fetchall()
    return render_template(
        "admin/tournaments.html",
        tournaments=all_tournaments,
        active_tournament_id=session.get("tournament_id"),
    )


# ---------- Players ----------

@bp.route("/players", methods=["GET", "POST"])
@login_required
@tournament_required
def players():
    db = get_db()
    tournament_id = g.tournament["id"]
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        count = db.execute(
            "SELECT COUNT(*) AS c FROM players WHERE tournament_id = ?", (tournament_id,)
        ).fetchone()["c"]
        if not name:
            flash("Player name cannot be empty.", "error")
        elif count >= current_app.config["MAX_PLAYERS"]:
            flash(f"Maximum of {current_app.config['MAX_PLAYERS']} players reached.", "error")
        else:
            try:
                db.execute("INSERT INTO players (tournament_id, name) VALUES (?, ?)", (tournament_id, name))
                db.commit()
            except Exception:
                flash("That player name already exists in this tournament.", "error")
        return redirect(url_for("admin.players"))

    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()
    return render_template(
        "admin/players.html",
        players=all_players,
        max_players=current_app.config["MAX_PLAYERS"],
        tournament=g.tournament,
    )


@bp.route("/players/<int:player_id>/delete", methods=["POST"])
@login_required
@tournament_required
def delete_player(player_id):
    db = get_db()
    db.execute("DELETE FROM players WHERE id = ? AND tournament_id = ?", (player_id, g.tournament["id"]))
    db.commit()
    return redirect(url_for("admin.players"))


# ---------- Courts ----------

@bp.route("/courts", methods=["GET", "POST"])
@login_required
@tournament_required
def courts():
    db = get_db()
    tournament_id = g.tournament["id"]
    if request.method == "POST":
        try:
            count = int(request.form.get("count", "0"))
        except ValueError:
            count = 0
        count = max(0, min(count, current_app.config["MAX_COURTS"]))

        existing = db.execute(
            "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
        ).fetchall()
        if count < len(existing):
            for court in existing[count:]:
                db.execute(
                    "DELETE FROM courts WHERE id = ? AND tournament_id = ?", (court["id"], tournament_id)
                )
        elif count > len(existing):
            for i in range(len(existing) + 1, count + 1):
                db.execute(
                    "INSERT INTO courts (tournament_id, name, sort_order) VALUES (?, ?, ?)",
                    (tournament_id, f"Court {i}", i),
                )
        db.commit()
        return redirect(url_for("admin.courts"))

    all_courts = db.execute(
        "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
    ).fetchall()
    return render_template(
        "admin/courts.html",
        courts=all_courts,
        max_courts=current_app.config["MAX_COURTS"],
        tournament=g.tournament,
    )


# ---------- Matches ----------

@bp.route("/matches")
@login_required
@tournament_required
def matches():
    db = get_db()
    tournament_id = g.tournament["id"]
    all_courts = db.execute(
        "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
    ).fetchall()
    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()
    max_slots = current_app.config["MAX_MATCHES_PER_COURT"]

    matches_by_court = {}
    for court in all_courts:
        rows = db.execute("SELECT * FROM matches WHERE court_id = ? ORDER BY slot", (court["id"],)).fetchall()
        by_slot = {row["slot"]: row for row in rows}
        matches_by_court[court["id"]] = [by_slot.get(slot) for slot in range(1, max_slots + 1)]

    return render_template(
        "admin/matches.html",
        courts=all_courts,
        players=all_players,
        matches_by_court=matches_by_court,
        slots=range(1, max_slots + 1),
        tournament=g.tournament,
    )


@bp.route("/matches/<int:court_id>/<int:slot>", methods=["POST"])
@login_required
@tournament_required
def save_match(court_id, slot):
    db = get_db()
    tournament_id = g.tournament["id"]

    court = db.execute(
        "SELECT id FROM courts WHERE id = ? AND tournament_id = ?", (court_id, tournament_id)
    ).fetchone()
    if court is None:
        flash("That court does not belong to the active tournament.", "error")
        return redirect(url_for("admin.matches"))

    def pid(field):
        value = request.form.get(field, "")
        return int(value) if value else None

    t1p1, t1p2 = pid("team1_player1"), pid("team1_player2")
    t2p1, t2p2 = pid("team2_player1"), pid("team2_player2")

    chosen = [p for p in (t1p1, t1p2, t2p1, t2p2) if p is not None]
    if len(chosen) != len(set(chosen)):
        flash("The same player cannot appear twice in one match.", "error")
        return redirect(url_for("admin.matches"))

    if chosen:
        placeholders = ",".join("?" for _ in chosen)
        count = db.execute(
            f"SELECT COUNT(*) AS c FROM players WHERE tournament_id = ? AND id IN ({placeholders})",
            (tournament_id, *chosen),
        ).fetchone()["c"]
        if count != len(chosen):
            flash("One or more players do not belong to the active tournament.", "error")
            return redirect(url_for("admin.matches"))

    existing = db.execute("SELECT id FROM matches WHERE court_id = ? AND slot = ?", (court_id, slot)).fetchone()
    if existing:
        db.execute(
            """UPDATE matches SET team1_player1_id=?, team1_player2_id=?,
               team2_player1_id=?, team2_player2_id=? WHERE id=?""",
            (t1p1, t1p2, t2p1, t2p2, existing["id"]),
        )
    else:
        db.execute(
            """INSERT INTO matches (court_id, slot, team1_player1_id, team1_player2_id,
               team2_player1_id, team2_player2_id) VALUES (?, ?, ?, ?, ?, ?)""",
            (court_id, slot, t1p1, t1p2, t2p1, t2p2),
        )
    db.commit()
    flash(f"Match {slot} saved.", "success")
    return redirect(url_for("admin.matches"))


# ---------- Randomizer ----------

@bp.route("/randomizer", methods=["GET", "POST"])
@login_required
@tournament_required
def randomizer():
    db = get_db()
    tournament_id = g.tournament["id"]
    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()
    max_exceptions = current_app.config["MAX_EXCEPTIONS"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_exception":
            p1 = request.form.get("player1")
            p2 = request.form.get("player2")
            count = db.execute(
                "SELECT COUNT(*) AS c FROM exceptions WHERE tournament_id = ?", (tournament_id,)
            ).fetchone()["c"]
            valid_players = {str(p["id"]) for p in all_players}
            if not p1 or not p2 or p1 == p2:
                flash("Choose two different players for an exception.", "error")
            elif p1 not in valid_players or p2 not in valid_players:
                flash("Choose players from the active tournament.", "error")
            elif count >= max_exceptions:
                flash(f"Maximum of {max_exceptions} exceptions reached.", "error")
            else:
                db.execute(
                    "INSERT INTO exceptions (tournament_id, player1_id, player2_id) VALUES (?, ?, ?)",
                    (tournament_id, p1, p2),
                )
                db.commit()
            return redirect(url_for("admin.randomizer"))

        if action == "delete_exception":
            db.execute(
                "DELETE FROM exceptions WHERE id = ? AND tournament_id = ?",
                (request.form.get("exception_id"), tournament_id),
            )
            db.commit()
            return redirect(url_for("admin.randomizer"))

        if action == "generate":
            max_slots = current_app.config["MAX_MATCHES_PER_COURT"]
            all_courts = db.execute(
                "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
            ).fetchall()
            try:
                rounds = int(request.form.get("rounds", "0"))
            except ValueError:
                rounds = 0

            if rounds < 1 or rounds > max_slots:
                flash(f"Enter a number of matches per player between 1 and {max_slots}.", "error")
            elif not all_courts:
                flash("Add at least one court first.", "error")
            elif len(all_players) < 4:
                flash("Add at least 4 players first.", "error")
            else:
                exception_rows = db.execute(
                    "SELECT player1_id, player2_id FROM exceptions WHERE tournament_id = ?", (tournament_id,)
                ).fetchall()
                exception_pairs = [(row["player1_id"], row["player2_id"]) for row in exception_rows]
                player_ids = [p["id"] for p in all_players]

                schedule = generate_match_schedule(player_ids, len(all_courts), rounds, exception_pairs)
                court_ids = [c["id"] for c in all_courts]

                db.execute(
                    "DELETE FROM matches WHERE court_id IN (SELECT id FROM courts WHERE tournament_id = ?)",
                    (tournament_id,),
                )
                for round_no, foursomes in enumerate(schedule, start=1):
                    for court_id, (team1, team2) in zip(court_ids, foursomes):
                        db.execute(
                            """INSERT INTO matches (court_id, slot, team1_player1_id, team1_player2_id,
                               team2_player1_id, team2_player2_id) VALUES (?, ?, ?, ?, ?, ?)""",
                            (court_id, round_no, team1[0], team1[1], team2[0], team2[1]),
                        )
                db.commit()
                flash("Matches generated and filled into the Scoring tab.", "success")
            return redirect(url_for("admin.randomizer"))

    exceptions = db.execute(
        """SELECT exceptions.id, p1.name AS player1_name, p2.name AS player2_name
           FROM exceptions
           JOIN players p1 ON p1.id = exceptions.player1_id
           JOIN players p2 ON p2.id = exceptions.player2_id
           WHERE exceptions.tournament_id = ?""",
        (tournament_id,),
    ).fetchall()

    courts_count = db.execute(
        "SELECT COUNT(*) AS c FROM courts WHERE tournament_id = ?", (tournament_id,)
    ).fetchone()["c"]
    return render_template(
        "admin/randomizer.html",
        players=all_players,
        exceptions=exceptions,
        max_exceptions=max_exceptions,
        max_rounds=current_app.config["MAX_MATCHES_PER_COURT"],
        courts_count=courts_count,
        tournament=g.tournament,
    )
