# dinkEngine

A small Flask + SQLite app for running a doubles pickleball/tennis session:
admin sets up players, courts and matches; scores are entered per match;
players are ranked by total score; and an admin-only randomizer generates a
fair partner schedule. Admin can run multiple tournaments side by side — each
tournament keeps its own players, courts, matches and schedule.

## Setup

```powershell
git clone https://github.com/paulinemlchan/dinkEngine.git
cd dinkEngine
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

The site runs at http://127.0.0.1:5000. The database file (`dinkengine.sqlite3`)
is created automatically on first run.

## Admin login

Default credentials are `admin` / `changeme123`. Override them with environment
variables before starting the app:

```powershell
$env:ADMIN_USERNAME = "yourname"
$env:ADMIN_PASSWORD = "your-strong-password"
$env:SECRET_KEY = "a-random-secret-string"
python app.py
```

## Pages

- `/login` — admin login
- `/admin/tournaments` — create tournaments and switch which one is active for the other admin tabs
- `/admin/players` — add/remove up to 32 players in the active tournament
- `/admin/courts` — set the number of courts in the active tournament
- `/admin/matches` — for each court, assign up to 5 matches (two pairs of players each)
- `/admin/randomizer` — generate matches across all courts (choose matches per player, add up to 5 "don't pair" exceptions); this replaces any existing matches/scores in the active tournament
- `/` — public page listing all tournaments
- `/t/<id>/scoring` — public page, one tab per court, enter each match's score
- `/t/<id>/rankings` — public page, players ranked by total score
- `/t/<id>/schedule` — public page, the player x round partner view for that tournament
