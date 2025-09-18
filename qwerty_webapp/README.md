# Qwerty WebApp (Flet)

A Flet-based desktop/web UI for the existing FastAPI backend (`qwerty_assistant`).

## Features
- Login, Register, Refresh token flow
- Token-based auth (Bearer)
- Stores refresh token in Flet `client_storage`; keeps access token in memory
- Displays `/me` (id, email, active)
- Logout current session or all sessions

## Configure
Create `.env` or set env var:

```
API_BASE_URL=http://localhost:8000
```

Backend runs on 8000 per `docker-compose.yml`.

## Install
```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```
python -m flet run qwerty_webapp/qwerty_webapp/app.py  # or
python qwerty_webapp/qwerty_webapp/app.py
```

## Notes
- Access token lives in memory and is rotated via `/refresh` when expired/401.
- Refresh token is persisted using Flet `page.client_storage` and rotated on refresh.
- Endpoints expected:
  - POST `/register` { email, password } -> { access_token, refresh_token }
  - POST `/login` { email, password } -> { access_token, refresh_token }
  - POST `/refresh` { refresh_token } -> { access_token, refresh_token }
  - GET `/me` (Authorization: Bearer <access>) -> profile
  - POST `/logout` (Authorization) + `all_sessions` query or `{refresh_token}`
