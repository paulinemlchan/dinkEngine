import random

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from db import get_db

bp = Blueprint("public", __name__)

SLAM_ROUND_SLOTS = {1: 16, 2: 8, 3: 4, 4: 2, 5: 1}
SLAM_ROUND_LABELS = {1: "Round 1", 2: "Round 2", 3: "Round 3", 4: "Semifinals", 5: "Final"}

AWARD_CATEGORIES = {"best_dressed": "Best Dressed", "spirit_of_the_haunt": "Spirit of the Haunt"}


@bp.app_context_processor
def inject_started_award_categories():
    """Makes the set of started award categories available to every template,
    so base.html can show/hide the Best Dressed / Spirit of the Haunt nav links
    without every route having to pass it in explicitly."""
    tournament_id = (request.view_args or {}).get("tournament_id") or session.get("tournament_id")
    if not tournament_id:
        return {"started_award_categories": set()}
    db = get_db()
    rows = db.execute(
        "SELECT category FROM award_rounds WHERE tournament_id = ? AND started = 1", (tournament_id,)
    ).fetchall()
    return {"started_award_categories": {row["category"] for row in rows}}


def _pick_server(player1_name, player2_name):
    """Randomly pick who serves first, or None when the pairing isn't a real match yet."""
    if not player1_name or not player2_name or "BYE" in (player1_name, player2_name):
        return None
    return random.choice([player1_name, player2_name])


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
    diffs = {}

    def add(pid, pts, diff):
        if pid is None:
            return
        totals[pid] = totals.get(pid, 0) + pts
        played[pid] = played.get(pid, 0) + 1
        diffs[pid] = diffs.get(pid, 0) + diff

    for m in matches:
        margin = m["team1_score"] - m["team2_score"]
        add(m["team1_player1_id"], m["team1_score"], margin)
        add(m["team1_player2_id"], m["team1_score"], margin)
        add(m["team2_player1_id"], m["team2_score"], -margin)
        add(m["team2_player2_id"], m["team2_score"], -margin)

    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()
    board = [
        {
            "name": p["name"],
            "total_score": totals.get(p["id"], 0),
            "matches_played": played.get(p["id"], 0),
            "point_difference": diffs.get(p["id"], 0),
        }
        for p in all_players
    ]
    board.sort(key=lambda row: (-row["total_score"], -row["point_difference"], row["name"]))
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


@bp.route("/t/<int:tournament_id>/report")
def report(tournament_id):
    """Lets any visitor pick their name and see their own matches and court."""
    db = get_db()
    tournament = _get_tournament(db, tournament_id)
    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()

    selected_player = None
    matches = []
    player_id = request.args.get("player_id", type=int)
    if player_id is not None:
        selected_player = db.execute(
            "SELECT * FROM players WHERE id = ? AND tournament_id = ?", (player_id, tournament_id)
        ).fetchone()
        if selected_player is not None:
            rows = db.execute(
                """SELECT courts.name AS court_name, matches.slot,
                          p1.name AS team1_player1_name, p2.name AS team1_player2_name,
                          p3.name AS team2_player1_name, p4.name AS team2_player2_name,
                          matches.team1_player1_id, matches.team1_player2_id,
                          matches.team2_player1_id, matches.team2_player2_id,
                          matches.team1_score, matches.team2_score
                   FROM matches
                   JOIN courts ON courts.id = matches.court_id
                   LEFT JOIN players p1 ON p1.id = matches.team1_player1_id
                   LEFT JOIN players p2 ON p2.id = matches.team1_player2_id
                   LEFT JOIN players p3 ON p3.id = matches.team2_player1_id
                   LEFT JOIN players p4 ON p4.id = matches.team2_player2_id
                   WHERE courts.tournament_id = ?
                     AND ? IN (matches.team1_player1_id, matches.team1_player2_id,
                               matches.team2_player1_id, matches.team2_player2_id)
                   ORDER BY matches.slot""",
                (tournament_id, player_id),
            ).fetchall()
            for row in rows:
                on_team1 = row["team1_player1_id"] == player_id or row["team1_player2_id"] == player_id
                if on_team1:
                    partner = row["team1_player2_name"] if row["team1_player1_id"] == player_id else row["team1_player1_name"]
                    opponents = [row["team2_player1_name"], row["team2_player2_name"]]
                    my_score, opp_score = row["team1_score"], row["team2_score"]
                else:
                    partner = row["team2_player2_name"] if row["team2_player1_id"] == player_id else row["team2_player1_name"]
                    opponents = [row["team1_player1_name"], row["team1_player2_name"]]
                    my_score, opp_score = row["team2_score"], row["team1_score"]
                matches.append(
                    {
                        "court_name": row["court_name"],
                        "slot": row["slot"],
                        "partner": partner or "?",
                        "opponents": [o or "?" for o in opponents],
                        "score": f"{my_score}-{opp_score}" if my_score is not None else None,
                    }
                )

    return render_template(
        "public/report.html",
        tournament=tournament,
        players=all_players,
        selected_player=selected_player,
        matches=matches,
    )


@bp.route("/t/<int:tournament_id>/slam")
def slam(tournament_id):
    db = get_db()
    tournament = _get_tournament(db, tournament_id)
    rows = db.execute(
        "SELECT * FROM slam_matches WHERE tournament_id = ? ORDER BY round, slot", (tournament_id,)
    ).fetchall()

    by_round = {}
    for row in rows:
        by_round.setdefault(row["round"], {})[row["slot"]] = row

    rounds = []
    for round_num, slot_count in SLAM_ROUND_SLOTS.items():
        slots = [by_round.get(round_num, {}).get(slot) for slot in range(slot_count)]
        rounds.append({"number": round_num, "label": SLAM_ROUND_LABELS[round_num], "slots": slots})

    champion = None
    final_match = by_round.get(5, {}).get(0)
    if final_match is not None:
        champion = final_match["winner_name"]

    return render_template(
        "public/slam.html",
        tournament=tournament,
        rounds=rounds,
        started=1 in by_round,
        champion=champion,
    )


@bp.route("/t/<int:tournament_id>/slam/start", methods=["POST"])
def slam_start(tournament_id):
    db = get_db()
    _get_tournament(db, tournament_id)

    already_started = db.execute(
        "SELECT 1 FROM slam_matches WHERE tournament_id = ? LIMIT 1", (tournament_id,)
    ).fetchone()
    if already_started and not session.get("is_admin"):
        flash("Only an admin can restart the bracket once it has started.", "error")
        return redirect(url_for("public.slam", tournament_id=tournament_id))

    names = [row["name"] for row in db.execute(
        "SELECT name FROM players WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()]

    if not names:
        flash("Add players to this tournament before starting a 1-Point Slam.", "error")
        return redirect(url_for("public.slam", tournament_id=tournament_id))
    if len(names) > 32:
        flash("A 1-Point Slam bracket supports at most 32 players.", "error")
        return redirect(url_for("public.slam", tournament_id=tournament_id))

    random.shuffle(names)
    names += ["BYE"] * (32 - len(names))

    db.execute("DELETE FROM slam_matches WHERE tournament_id = ?", (tournament_id,))
    for slot in range(16):
        player1_name, player2_name = names[slot * 2], names[slot * 2 + 1]
        db.execute(
            """INSERT INTO slam_matches (tournament_id, round, slot, player1_name, player2_name, server_name)
               VALUES (?, 1, ?, ?, ?, ?)""",
            (tournament_id, slot, player1_name, player2_name, _pick_server(player1_name, player2_name)),
        )
    db.commit()
    return redirect(url_for("public.slam", tournament_id=tournament_id))


@bp.route("/t/<int:tournament_id>/slam/pick", methods=["POST"])
def slam_pick(tournament_id):
    db = get_db()
    _get_tournament(db, tournament_id)

    if not session.get("is_admin"):
        abort(403)

    round_num = request.form.get("round", type=int)
    slot = request.form.get("slot", type=int)
    winner = request.form.get("winner", "").strip()

    if round_num not in SLAM_ROUND_SLOTS or slot is None or not (0 <= slot < SLAM_ROUND_SLOTS[round_num]):
        abort(400)

    match = db.execute(
        "SELECT * FROM slam_matches WHERE tournament_id = ? AND round = ? AND slot = ?",
        (tournament_id, round_num, slot),
    ).fetchone()
    if match is None or winner not in (match["player1_name"], match["player2_name"]):
        abort(400)

    db.execute("UPDATE slam_matches SET winner_name = ? WHERE id = ?", (winner, match["id"]))

    if round_num < 5:
        next_slot = slot // 2
        db.execute(
            """INSERT INTO slam_matches (tournament_id, round, slot, player1_name, player2_name)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(tournament_id, round, slot) DO UPDATE SET
                 player1_name = COALESCE(slam_matches.player1_name, excluded.player1_name),
                 player2_name = COALESCE(slam_matches.player2_name, excluded.player2_name)""",
            (
                tournament_id,
                round_num + 1,
                next_slot,
                winner if slot % 2 == 0 else None,
                winner if slot % 2 == 1 else None,
            ),
        )

        next_match = db.execute(
            "SELECT * FROM slam_matches WHERE tournament_id = ? AND round = ? AND slot = ?",
            (tournament_id, round_num + 1, next_slot),
        ).fetchone()
        if next_match["server_name"] is None:
            server_name = _pick_server(next_match["player1_name"], next_match["player2_name"])
            if server_name is not None:
                db.execute("UPDATE slam_matches SET server_name = ? WHERE id = ?", (server_name, next_match["id"]))

    db.commit()
    return redirect(url_for("public.slam", tournament_id=tournament_id))


@bp.route("/t/<int:tournament_id>/awards/<category>")
def awards(tournament_id, category):
    if category not in AWARD_CATEGORIES:
        abort(404)
    db = get_db()
    tournament = _get_tournament(db, tournament_id)

    started = db.execute(
        "SELECT started FROM award_rounds WHERE tournament_id = ? AND category = ?", (tournament_id, category)
    ).fetchone()
    started = bool(started and started["started"])

    all_players = db.execute(
        "SELECT * FROM players WHERE tournament_id = ? ORDER BY name", (tournament_id,)
    ).fetchall()

    voter = None
    nominees = []
    already_voted_for = None
    voter_id = request.args.get("voter_id", type=int)
    if started and voter_id is not None:
        voter = db.execute(
            "SELECT * FROM players WHERE id = ? AND tournament_id = ?", (voter_id, tournament_id)
        ).fetchone()
        if voter is not None:
            existing_vote = db.execute(
                """SELECT players.name FROM award_votes
                   JOIN players ON players.id = award_votes.nominee_player_id
                   WHERE award_votes.tournament_id = ? AND award_votes.category = ? AND award_votes.voter_player_id = ?""",
                (tournament_id, category, voter_id),
            ).fetchone()
            if existing_vote is not None:
                already_voted_for = existing_vote["name"]
            else:
                nominees = [p for p in all_players if p["id"] != voter_id]

    return render_template(
        "public/awards.html",
        tournament=tournament,
        category=category,
        category_label=AWARD_CATEGORIES[category],
        started=started,
        players=all_players,
        voter=voter,
        nominees=nominees,
        already_voted_for=already_voted_for,
    )


@bp.route("/t/<int:tournament_id>/awards/<category>/vote", methods=["POST"])
def awards_vote(tournament_id, category):
    if category not in AWARD_CATEGORIES:
        abort(404)
    db = get_db()
    _get_tournament(db, tournament_id)

    started = db.execute(
        "SELECT started FROM award_rounds WHERE tournament_id = ? AND category = ?", (tournament_id, category)
    ).fetchone()
    if not (started and started["started"]):
        abort(400)

    voter_id = request.form.get("voter_id", type=int)
    nominee_id = request.form.get("nominee_id", type=int)
    if voter_id is None or nominee_id is None or voter_id == nominee_id:
        abort(400)

    voter = db.execute("SELECT id FROM players WHERE id = ? AND tournament_id = ?", (voter_id, tournament_id)).fetchone()
    nominee = db.execute("SELECT id FROM players WHERE id = ? AND tournament_id = ?", (nominee_id, tournament_id)).fetchone()
    if voter is None or nominee is None:
        abort(400)

    already_voted = db.execute(
        "SELECT 1 FROM award_votes WHERE tournament_id = ? AND category = ? AND voter_player_id = ?",
        (tournament_id, category, voter_id),
    ).fetchone()
    if already_voted:
        flash("You've already voted in this category.", "error")
        return redirect(url_for("public.awards", tournament_id=tournament_id, category=category, voter_id=voter_id))

    db.execute(
        """INSERT INTO award_votes (tournament_id, category, voter_player_id, nominee_player_id)
           VALUES (?, ?, ?, ?)""",
        (tournament_id, category, voter_id, nominee_id),
    )
    db.commit()
    flash("Your vote has been recorded. Thank you!", "success")
    return redirect(url_for("public.awards", tournament_id=tournament_id, category=category, voter_id=voter_id))
