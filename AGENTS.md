# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a Python Flask + Selenium application ("Enterprise Scorecard Automation") that automates scorecard configuration on the external **e.fundamentals settings portal** (`settings.ef.uk.com`). There is no database, no Docker, and no test suite. The app is a single Flask server (`app1a.py`) serving a web UI and driving Chrome via Selenium.

### Running the Flask server

```bash
source /workspace/.venv/bin/activate
PORT=5005 HEADLESS=1 python3 app1a.py
```

The server runs on `0.0.0.0:<PORT>` (default `5003` if `PORT` is not set; README recommends `5005`). The UI is at `http://localhost:<PORT>`.

### Key setup gotchas

- **`requirements.txt`**: The README references it but the repo originally shipped without one. It was created during setup with the deps listed in the README: `Flask>=3.0.0`, `selenium>=4.15.2`, `pandas>=2.2.0`, `openpyxl>=3.1.2`, `webdriver-manager>=4.0.1`.
- **`templates/` directory**: Flask's `render_template('index.html')` expects a `templates/` folder, but `index.html` lives in the repo root. A symlink `templates/index.html -> /workspace/index.html` is needed. The update script handles this.
- **No automated tests**: There is no test suite. Testing is manual — run the server and use the web form, or hit API endpoints (`/status`, `/step_tracking`, `/monitoring`, `/monitoring/errors`, `/monitoring/summary`).
- **Selenium/Chrome**: The app requires Google Chrome and uses `webdriver-manager` to auto-download ChromeDriver. Set `HEADLESS=1` to run Chrome in headless mode (needed on servers without a display).
- **External portal dependency**: Full end-to-end automation requires access to `settings.ef.uk.com` with valid credentials. Without portal access, the app will start and accept form submissions but fail at the browser automation step.

### Linting

No linter is configured in the repo. For ad-hoc checking, use `python3 -m py_compile app1a.py` to verify syntax.
