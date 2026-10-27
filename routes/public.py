from flask import Blueprint, abort, redirect, render_template, request, url_for

from db import get_db

bp = Blueprint("public", __name__)


def _get_tournament(db, tournament_id):
    tournament = db.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,)).fetchone()
    if tournament is None:
        abort(404)
    return tournament


@bp.route("/")
def index():
    db = get_db()
    all_tournaments = db.execute("SELECT * FROM tournaments ORDER BY created_at DESC").fetchall()
    return render_template("public/tournaments.html", tournaments=all_tournaments)


@bp.route("/t/<int:tournament_id>/scoring")
def scoring(tournament_id):
    db = get_db()
    tournament = _get_tournament(db, tournament_id)
    all_courts = db.execute(
        "SELECT * FROM courts WHERE tournament_id = ? ORDER BY sort_order", (tournament_id,)
    ).fetchall()
    matches_by_court = {}
    for court in all_courts:
        rows = db.execute(
            """SELECT matches.*,
                      p1.name AS team1_player1_name, p2.name AS team1_player2_name,
                      p3.name AS team2_player1_name, p4.name AS team2_player2_name
               FROM matches
               LEFT JOIN players p1 ON p1.id = matches.team1_player1_id
               LEFT JOIN players p2 ON p2.id = matches.team1_player2_id
               LEFT JOIN players p3 ON p3.id = matches.team2_player1_id
               LEFT JOIN players p4 ON p4.id = matches.team2_player2_id
               WHERE matches.court_id = ? ORDER BY matches.slot""",
            (court["id"],),
        ).fetchall()
        matches_by_court[court["id"]] = rows
    return render_template(
        "public/scoring.html", tournament=tournament, courts=all_courts, matches_by_court=matches_by_court
    )


@bp.route("/t/<int:tournament_id>/scoring/<int:match_id>", methods=["POST"])
def submit_score(tournament_id, match_id):
    db = get_db()
    _get_tournament(db, tournament_id)

    match = db.execute(
        """SELECT matches.id FROM matches
           JOIN courts ON courts.id = matches.court_id
           WHERE matches.id = ? AND courts.tournament_id = ?""",
        (match_id, tournament_id),
    ).fetchone()
    if match is None:
        abort(404)

    def score(field):
        value = request.form.get(field, "").strip()
        return int(value) if value else None

    db.execute(
        "UPDATE matches SET team1_score = ?, team2_score = ? WHERE id = ?",
        (score("team1_score"), score("team2_score"), match_id),
    )
    db.commit()
    return redirect(url_for("public.scoring", tournament_id=tournament_id))


@bp.route("/t/<int:tournament_id>/rankings")
def rankings(tournament_id):
    db = get_db()
    tournament = _get_tournament(db, tournament_id)
    matches = db.execute(
        """SELECT matches.team1_player1_id, matches.team1_player2_id,
                  matches.team2_player1_id, matches.team2_player2_id,
                  matches.team1_score, matches.team2_score
           FROM matches
           JOIN courts ON courts.id = matches.court_id
           WHERE courts.tournament_id = ?
             AND matches.team1_score IS NOT NULL AND matches.team2_score IS NOT NULL""",
        (tournament_id,),
    ).fetchall()

    totals = {}
    played = {}

    def add(pid, pts):
        if pid is None:
            return
        totals[pid] = totals.get(pid, 0) + pts
        played[pid] = played.get(pid, 0) + 1

    for m in matches:
        add(m["team1_player1_id"], m["team1_score"])
        add(m["team1_player2_id"], m["team1_score"])
        add(m["team2_player1_id"], m["team2_score"])
        add(m["team2_player2_id"], m["team2_score"])

    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()
    board = [
        {
            "name": p["name"],
            "total_score": totals.get(p["id"], 0),
            "matches_played": played.get(p["id"], 0),
        }
        for p in all_players
    ]
    board.sort(key=lambda row: (-row["total_score"], row["name"]))
    return render_template("public/rankings.html", tournament=tournament, board=board)


@bp.route("/t/<int:tournament_id>/schedule")
def schedule(tournament_id):
    """Matches grouped by court, read-only (score entry happens on the Scoring page)."""
    db = get_db()
    tournament = _get_tournament(db, tournament_id)
    rows = db.execute(
        """SELECT courts.id AS court_id, courts.name AS court_name, matches.slot,
                  p1.name AS team1_player1_name, p2.name AS team1_player2_name,
                  p3.name AS team2_player1_name, p4.name AS team2_player2_name
           FROM matches
           JOIN courts ON courts.id = matches.court_id
           LEFT JOIN players p1 ON p1.id = matches.team1_player1_id
           LEFT JOIN players p2 ON p2.id = matches.team1_player2_id
           LEFT JOIN players p3 ON p3.id = matches.team2_player1_id
           LEFT JOIN players p4 ON p4.id = matches.team2_player2_id
           WHERE courts.tournament_id = ?
           ORDER BY courts.sort_order, matches.slot""",
        (tournament_id,),
    ).fetchall()

    courts_by_id = {}
    for row in rows:
        court = courts_by_id.setdefault(
            row["court_id"], {"name": row["court_name"], "matches": []}
        )
        court["matches"].append(row)

    return render_template("public/schedule.html", tournament=tournament, courts=courts_by_id.values())
