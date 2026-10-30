CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    theme TEXT NOT NULL DEFAULT 'normal',
    banner_filename TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_kid INTEGER NOT NULL DEFAULT 0,
    UNIQUE(tournament_id, name)
);

CREATE TABLE IF NOT EXISTS courts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    court_id INTEGER NOT NULL REFERENCES courts(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL,
    team1_player1_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    team1_player2_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    team2_player1_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    team2_player2_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    team1_score INTEGER,
    team2_score INTEGER,
    UNIQUE(court_id, slot)
);

CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player1_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    player2_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE
);

-- 1-Point Slam: a 32-player single-elimination bracket, random seeding, winner takes all.
-- round: 1=Round 1 (16 matchups), 2=Round 2 (8), 3=Round 3 (4), 4=Semifinals (2), 5=Final (1).
CREATE TABLE IF NOT EXISTS slam_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    player1_name TEXT,
    player2_name TEXT,
    winner_name TEXT,
    server_name TEXT,
    UNIQUE(tournament_id, round, slot)
);

-- Award voting (e.g. "Best Dressed", "Spirit of the Haunt"): one vote per player per category.
-- category is a slug, e.g. 'best_dressed' or 'spirit_of_the_haunt'.
CREATE TABLE IF NOT EXISTS award_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    started INTEGER NOT NULL DEFAULT 0,
    UNIQUE(tournament_id, category)
);

CREATE TABLE IF NOT EXISTS award_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    voter_player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    nominee_player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    UNIQUE(tournament_id, category, voter_player_id)
);

-- Knockout round: opened by the admin once all matches are complete.
-- status: 'selecting' (points tie at the top-8 cut-off, admin picks the 8) or 'started'.
CREATE TABLE IF NOT EXISTS knockout_state (
    tournament_id INTEGER PRIMARY KEY REFERENCES tournaments(id) ON DELETE CASCADE,
    status TEXT NOT NULL
);

-- The 8 qualified players. Team k (1..4) is seed k with seed 9-k: 1+8, 2+7, 3+6, 4+5.
CREATE TABLE IF NOT EXISTS knockout_seeds (
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    seed INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    PRIMARY KEY (tournament_id, seed)
);

-- round: 1=Semifinals (slot 0: team 1 vs team 4, slot 1: team 2 vs team 3), 2=Final.
CREATE TABLE IF NOT EXISTS knockout_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    team1 INTEGER,
    team2 INTEGER,
    winner INTEGER,
    UNIQUE(tournament_id, round, slot)
);

