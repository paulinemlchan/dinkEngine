import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    _migrate(db)
    db.commit()


def _migrate(db):
    """Add columns introduced after a database already existed.

    schema.sql's CREATE TABLE IF NOT EXISTS only applies to brand new
    databases, so older ones need their missing columns added here.
    """
    existing_columns = {row["name"] for row in db.execute("PRAGMA table_info(players)")}
    if "is_kid" not in existing_columns:
        db.execute("ALTER TABLE players ADD COLUMN is_kid INTEGER NOT NULL DEFAULT 0")

    tournament_columns = {row["name"] for row in db.execute("PRAGMA table_info(tournaments)")}
    if "theme" not in tournament_columns:
        db.execute("ALTER TABLE tournaments ADD COLUMN theme TEXT NOT NULL DEFAULT 'normal'")
    if "banner_filename" not in tournament_columns:
        db.execute("ALTER TABLE tournaments ADD COLUMN banner_filename TEXT")

    slam_columns = {row["name"] for row in db.execute("PRAGMA table_info(slam_matches)")}
    if "server_name" not in slam_columns:
        db.execute("ALTER TABLE slam_matches ADD COLUMN server_name TEXT")

    vote_columns = {row["name"] for row in db.execute("PRAGMA table_info(award_votes)")}
    if "nominee_name" not in vote_columns:
        # Write-in nominees need nominee_player_id to allow NULL; SQLite can only change
        # that by rebuilding the table, so copy the existing votes into a new one.
        db.execute(
            """CREATE TABLE award_votes_new (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
                   category TEXT NOT NULL,
                   voter_player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                   nominee_player_id INTEGER REFERENCES players(id) ON DELETE CASCADE,
                   nominee_name TEXT,
                   UNIQUE(tournament_id, category, voter_player_id)
               )"""
        )
        db.execute(
            """INSERT INTO award_votes_new (id, tournament_id, category, voter_player_id, nominee_player_id)
               SELECT id, tournament_id, category, voter_player_id, nominee_player_id FROM award_votes"""
        )
        db.execute("DROP TABLE award_votes")
        db.execute("ALTER TABLE award_votes_new RENAME TO award_votes")


@click.command("init-db")
def init_db_command():
    """Create database tables if they don't already exist."""
    init_db()
    click.echo("Initialized the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
