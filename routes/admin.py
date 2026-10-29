import itertools
import os
from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from db import get_db
from randomizer import generate_match_schedule
from routes.auth import login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

THEMES = ["normal", "halloween", "christmas", "chinese_new_year"]

# Minimal magic-byte check so a renamed non-image file can't be stored as a "banner".
_IMAGE_SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),  # followed by size (4 bytes) then b"WEBP"; checked separately below
}


def _save_theme_banner(tournament_id, file_storage):
    """Validate and store an uploaded banner, returning its filename, or None if no file was given."""
    if not file_storage or not file_storage.filename:
        return None

    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    allowed = current_app.config["THEME_BANNER_ALLOWED_EXTENSIONS"]
    if "." not in file_storage.filename or ext not in allowed:
        raise ValueError(f"Banner must be one of: {', '.join(sorted(allowed))}.")

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if ext == "webp":
        valid = header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    else:
        valid = any(header.startswith(sig) for sig in _IMAGE_SIGNATURES[ext])
    if not valid:
        raise ValueError("That file doesn't look like a valid image.")

    upload_folder = current_app.config["THEME_BANNER_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"tournament_{tournament_id}.{ext}"
    file_storage.save(os.path.join(upload_folder, filename))
    return filename




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
            row = db.execute(
                "SELECT banner_filename FROM tournaments WHERE id = ?", (tournament_id,)
            ).fetchone()
            db.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
            db.commit()
            if row and row["banner_filename"]:
                banner_path = os.path.join(current_app.config["THEME_BANNER_UPLOAD_FOLDER"], row["banner_filename"])
                if os.path.exists(banner_path):
                    os.remove(banner_path)
            if str(session.get("tournament_id")) == str(tournament_id):
                session.pop("tournament_id", None)
            flash("Tournament deleted.", "success")

        elif action == "rename":
            tournament_id = request.form.get("tournament_id")
            name = request.form.get("name", "").strip()
            if not name:
                flash("Tournament name cannot be empty.", "error")
            else:
                db.execute("UPDATE tournaments SET name = ? WHERE id = ?", (name, tournament_id))
                db.commit()
                flash("Tournament renamed.", "success")

        elif action == "set_theme":
            tournament_id = request.form.get("tournament_id")
            theme = request.form.get("theme", "")
            if theme not in THEMES:
                flash("Unknown theme.", "error")
            else:
                row = db.execute(
                    "SELECT banner_filename FROM tournaments WHERE id = ?", (tournament_id,)
                ).fetchone()
                try:
                    new_filename = _save_theme_banner(tournament_id, request.files.get("banner"))
                except ValueError as e:
                    flash(str(e), "error")
                else:
                    if new_filename is not None:
                        old_filename = row["banner_filename"] if row else None
                        if old_filename and old_filename != new_filename:
                            old_path = os.path.join(current_app.config["THEME_BANNER_UPLOAD_FOLDER"], old_filename)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        db.execute(
                            "UPDATE tournaments SET theme = ?, banner_filename = ? WHERE id = ?",
                            (theme, new_filename, tournament_id),
                        )
                    else:
                        db.execute("UPDATE tournaments SET theme = ? WHERE id = ?", (theme, tournament_id))
                    db.commit()
                    flash("Tournament theme updated.", "success")

        return redirect(url_for("admin.tournaments"))

    all_tournaments = db.execute("SELECT * FROM tournaments ORDER BY created_at DESC").fetchall()
    return render_template(
        "admin/tournaments.html",
        tournaments=all_tournaments,
        active_tournament_id=session.get("tournament_id"),
        themes=THEMES,
    )


# ---------- Players ----------

@bp.route("/players", methods=["GET", "POST"])
@login_required
@tournament_required
def players():
    db = get_db()
    tournament_id = g.tournament["id"]
    max_players = current_app.config["MAX_PLAYERS"]

    if request.method == "POST":
        action = request.form.get("action", "add")
        count = db.execute(
            "SELECT COUNT(*) AS c FROM players WHERE tournament_id = ?", (tournament_id,)
        ).fetchone()["c"]

        if action == "add_bulk":
            raw = request.form.get("names", "")
            candidates = []
            seen = set()
            for line in raw.replace(",", "\n").splitlines():
                name = line.strip()
                if name and name not in seen:
                    seen.add(name)
                    candidates.append(name)

            if not candidates:
                flash("Enter at least one player name.", "error")
            else:
                added = 0
                skipped = []
                for name in candidates:
                    if count + added >= max_players:
                        skipped.append(name)
                        continue
                    try:
                        db.execute("INSERT INTO players (tournament_id, name) VALUES (?, ?)", (tournament_id, name))
                        db.commit()
                        added += 1
                    except Exception:
                        skipped.append(name)
                if added:
                    flash(f"Added {added} player(s).", "success")
                if skipped:
                    flash(
                        f"Skipped (duplicate name or over the {max_players}-player limit): {', '.join(skipped)}",
                        "error",
                    )
        else:
            name = request.form.get("name", "").strip()
            is_kid = 1 if request.form.get("is_kid") else 0
            if not name:
                flash("Player name cannot be empty.", "error")
            elif count >= max_players:
                flash(f"Maximum of {max_players} players reached.", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO players (tournament_id, name, is_kid) VALUES (?, ?, ?)",
                        (tournament_id, name, is_kid),
                    )
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
        max_players=max_players,
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


@bp.route("/players/<int:player_id>/kid", methods=["POST"])
@login_required
@tournament_required
def update_player_kid(player_id):
    db = get_db()
    is_kid = 1 if request.form.get("is_kid") else 0
    db.execute(
        "UPDATE players SET is_kid = ? WHERE id = ? AND tournament_id = ?",
        (is_kid, player_id, g.tournament["id"]),
    )
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


@bp.route("/courts/<int:court_id>/rename", methods=["POST"])
@login_required
@tournament_required
def rename_court(court_id):
    db = get_db()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Court name cannot be empty.", "error")
    else:
        db.execute(
            "UPDATE courts SET name = ? WHERE id = ? AND tournament_id = ?",
            (name, court_id, g.tournament["id"]),
        )
        db.commit()
    return redirect(url_for("admin.courts"))


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
    # Grid grows past the default if the randomizer already generated more rounds than that.
    highest_slot = db.execute(
        """SELECT MAX(matches.slot) AS m FROM matches
           JOIN courts ON courts.id = matches.court_id
           WHERE courts.tournament_id = ?""",
        (tournament_id,),
    ).fetchone()["m"]
    max_slots = max(current_app.config["MAX_MATCHES_PER_COURT"], highest_slot or 0)

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

        # Prevent the same player being on two courts in the same slot (round).
        other_matches = db.execute(
            """SELECT matches.team1_player1_id, matches.team1_player2_id,
                      matches.team2_player1_id, matches.team2_player2_id
               FROM matches
               JOIN courts ON courts.id = matches.court_id
               WHERE courts.tournament_id = ? AND matches.slot = ? AND matches.court_id != ?""",
            (tournament_id, slot, court_id),
        ).fetchall()
        busy_players = set()
        for row in other_matches:
            busy_players.update(
                p for p in (row["team1_player1_id"], row["team1_player2_id"],
                            row["team2_player1_id"], row["team2_player2_id"]) if p is not None
            )
        conflicts = busy_players & set(chosen)
        if conflicts:
            names = db.execute(
                f"SELECT name FROM players WHERE id IN ({','.join('?' for _ in conflicts)})",
                tuple(conflicts),
            ).fetchall()
            names = ", ".join(row["name"] for row in names)
            flash(f"Match {slot} already has {names} playing on another court.", "error")
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
    if session.get("is_superuser"):
        flash("Superusers cannot access the Randomizer.", "error")
        return redirect(url_for("admin.tournaments"))

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
            all_courts = db.execute(
                "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
            ).fetchall()
            try:
                matches_per_player = int(request.form.get("rounds", "0"))
            except ValueError:
                matches_per_player = 0

            if matches_per_player < 1:
                flash("Enter a number of matches per player of at least 1.", "error")
            elif not all_courts:
                flash("Add at least one court first.", "error")
            elif len(all_players) < 4:
                flash("Add at least 4 players first.", "error")
            else:
                exception_rows = db.execute(
                    "SELECT player1_id, player2_id FROM exceptions WHERE tournament_id = ?", (tournament_id,)
                ).fetchall()
                exception_pairs = [(row["player1_id"], row["player2_id"]) for row in exception_rows]

                # Kids can never partner another kid, on top of the manual exceptions above.
                kid_ids = [p["id"] for p in all_players if p["is_kid"]]
                exception_pairs.extend(itertools.combinations(kid_ids, 2))

                player_ids = [p["id"] for p in all_players]

                try:
                    schedule = generate_match_schedule(
                        player_ids, len(all_courts), matches_per_player, exception_pairs
                    )
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("admin.randomizer"))

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
                flash(
                    f"Matches generated ({len(schedule)} round(s)) — every player got exactly "
                    f"{matches_per_player} matches, filled into the Scoring tab.",
                    "success",
                )
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
        courts_count=courts_count,
        tournament=g.tournament,
    )


# ---------- Awards ----------

@bp.route("/awards", methods=["GET", "POST"])
@login_required
@tournament_required
def awards():
    from routes.public import AWARD_CATEGORIES

    db = get_db()
    tournament_id = g.tournament["id"]

    if request.method == "POST":
        if session.get("is_superuser"):
            flash("Only an admin can start or restart voting.", "error")
            return redirect(url_for("admin.awards"))

        action = request.form.get("action")
        category = request.form.get("category")
        if category not in AWARD_CATEGORIES:
            flash("Unknown award category.", "error")
            return redirect(url_for("admin.awards"))

        if action == "start_voting":
            db.execute(
                """INSERT INTO award_rounds (tournament_id, category, started) VALUES (?, ?, 1)
                   ON CONFLICT(tournament_id, category) DO UPDATE SET started = 1""",
                (tournament_id, category),
            )
            db.commit()
            flash(f"Voting started for {AWARD_CATEGORIES[category]}.", "success")
        elif action == "restart_voting":
            db.execute(
                "DELETE FROM award_votes WHERE tournament_id = ? AND category = ?", (tournament_id, category)
            )
            db.execute(
                """INSERT INTO award_rounds (tournament_id, category, started) VALUES (?, ?, 1)
                   ON CONFLICT(tournament_id, category) DO UPDATE SET started = 1""",
                (tournament_id, category),
            )
            db.commit()
            flash(f"Voting restarted for {AWARD_CATEGORIES[category]}.", "success")
        elif action == "end_voting":
            db.execute(
                "UPDATE award_rounds SET started = 0 WHERE tournament_id = ? AND category = ?",
                (tournament_id, category),
            )
            db.commit()
            flash(f"Voting ended for {AWARD_CATEGORIES[category]}.", "success")
        return redirect(url_for("admin.awards"))

    categories = []
    for category, label in AWARD_CATEGORIES.items():
        started_row = db.execute(
            "SELECT started FROM award_rounds WHERE tournament_id = ? AND category = ?", (tournament_id, category)
        ).fetchone()
        results = db.execute(
            """SELECT players.name AS name, COUNT(*) AS points
               FROM award_votes
               JOIN players ON players.id = award_votes.nominee_player_id
               WHERE award_votes.tournament_id = ? AND award_votes.category = ?
               GROUP BY players.id
               ORDER BY points DESC, players.name""",
            (tournament_id, category),
        ).fetchall()
        categories.append(
            {
                "slug": category,
                "label": label,
                "started": bool(started_row and started_row["started"]),
                "results": results,
            }
        )

    return render_template("admin/awards.html", tournament=g.tournament, categories=categories)
