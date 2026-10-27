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

## Deploy to PythonAnywhere

GitHub only hosts the source code — to actually run the site you need a server.
[PythonAnywhere](https://www.pythonanywhere.com) hosts Flask apps directly (no
gunicorn/Docker needed) and its free "Beginner" tier has genuinely persistent
storage — the filesystem isn't rebuilt on restart like on most free container
hosts, so `dinkengine.sqlite3` survives.

1. Push this repo to GitHub (already done).
2. On PythonAnywhere, open a **Bash console** and clone it:
   ```bash
   git clone https://github.com/paulinemlchan/dinkEngine.git
   cd dinkEngine
   ```
3. Create a virtualenv and install dependencies:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.13 dinkengine-venv
   pip install -r requirements.txt
   ```
4. Go to the **Web** tab → **Add a new web app** → **Manual configuration** →
   pick the same Python version as your virtualenv.
5. In the web app's **Virtualenv** section, enter `dinkengine-venv`.
6. Open the **WSGI configuration file** link near the top of the Web tab and
   replace its Flask section with the contents of [`pythonanywhere_wsgi_template.py`](pythonanywhere_wsgi_template.py)
   (update the path and admin credentials for your account).
7. Hit the green **Reload** button on the Web tab.

Your site is now live at `https://yourusername.pythonanywhere.com`. To pull
later changes, `git pull` in the Bash console and hit **Reload** again.

**Admin credentials:** Beginner-tier manually-configured apps don't get a
dashboard environment-variables UI, so `pythonanywhere_wsgi_template.py` sets
`ADMIN_USERNAME`/`ADMIN_PASSWORD`/`SECRET_KEY` directly in the WSGI file. That
file lives only in your own PythonAnywhere account, not in this repo.
