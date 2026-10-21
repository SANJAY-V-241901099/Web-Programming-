# FitTrack - Fitness Trainer and Workout Progress

Full-stack web app: HTML, CSS, JavaScript (Chart.js) + Python Flask + SQLite.

## Two different accounts
**User** (registers on the login page): Dashboard, Exercises, Workouts, My Plans, Progress.
**Trainer** (`admin@fittrack.com` / `Admin@123`, dark "TRAINER PANEL" theme): Clients, Exercises + Videos, Plans.

Trainer can: see every client with workouts, activity this week, last workout, weight change and goals;
open a client to see charts, workouts and goals; assign a plan; send feedback notes;
create plans; add or edit exercises and their video links.
Clients see the assigned plan and the trainer's notes on their dashboard.

## Run on Windows
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 (Mac/Linux: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python app.py`).
If you already ran an older version, keep `fittrack.db`; it upgrades automatically.

## Exercise videos (one exact video, no search page)
Channel: **ScottHermanFitness** (https://www.youtube.com/@ScottHermanFitness).
Fill `video_links.txt` (`Exercise name | https://www.youtube.com/watch?v=...`) and restart,
or log in as trainer > Exercises > Edit and paste the link. The video plays in a popup.
Your own `.mp4` in `static/videos/` also works (`/static/videos/squat.mp4`).

## Files
`app.py` (routes, validation, SQLite), `index.html`, `static/app.js`, `static/style.css`,
`video_links.txt` and `fittrack.db` (created automatically).
Local use only. Before hosting: set SECRET_KEY, turn off debug, use HTTPS and a production server.
