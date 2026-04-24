# Knowledge Hub

Minimal internal Flask service for storing project context, AI session logs, prompt templates, and snapshots.

The app now also has a first `workspace` foundation layer:

- every project belongs to a workspace
- a default personal workspace is created automatically
- imports can target a workspace when auto-creating projects
- each workspace now gets a default owner user automatically
- workspace members are stored separately from projects

This is the first clean step toward future multi-user SaaS separation without pulling in authentication too early.

The app now also has a first auth-ready access slice:

- every request resolves a current actor
- in development you can switch actor with `?as_user=email@example.com`
- the override is persisted in a dev cookie, so page navigation keeps the same actor
- workspace and project pages are now scoped by workspace membership
- owners/admins can add members directly from the workspace page or API

And there is now a first real login slice:

- `GET /auth/login` generates a one-time magic login link
- `GET /auth/magic/<token>` opens a confirmation page for the one-time link
- `POST /auth/magic/<token>` finishes sign-in and consumes the token
- `POST /auth/logout` clears the session

There is now a first auth-required mode too:

- set `KH_AUTH_REQUIRED=1` to require sign-in on private pages and APIs
- anonymous browser requests are redirected to `/auth/login?next=...`
- anonymous API requests get `401` plus a `login_url`
- magic-link sign-in now preserves the requested return path

There is now a first mail-delivery layer too:

- by default login emails are written into a file outbox under `data/knowledge_hub/mail_outbox/`
- the auth page shows the last outbox deliveries
- `GET /api/mail/status` shows current mail backend and recent outbox messages
- real SMTP delivery is supported too when you switch `KH_MAIL_BACKEND` to `smtp`

There is still no external email provider yet. The file outbox is the calm bridge between "show the link in HTML" and real delivery.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m flask --app run:app init-db
python run.py
```

Open `http://127.0.0.1:5001`

## Render deploy baseline

The repo now includes a first production-oriented Render baseline:

- `wsgi.py` for a stable Gunicorn entrypoint
- `render.yaml` for a Render Blueprint
- `gunicorn` in `requirements.txt`
- production config defaults for proxy-aware HTTPS deployment

Current Render start command:

```text
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4
```

Current Render data path:

```text
/var/data/knowledge_hub
```

This is a calm first deployment baseline for an internal service. It is not yet the final multi-user SaaS architecture.

There is now also a deploy setup guide:

- `GET /deploy-setup` shows a copy-friendly Render env plan
- `GET /deploy-env` shows the real current env status for production-facing variables
- `GET /api/deploy/setup` returns the same plan as JSON
- `GET /api/deploy/env-status` returns the current env status as JSON
- `python tools/deploy_setup.py` prints a two-phase rollout:
  - real SMTP delivery first
  - private `KH_AUTH_REQUIRED=1` mode second
- `python tools/deploy_env_status.py` prints what is still default, missing, or blocking right now

## Automation-first workflow

The web UI now includes safe ops buttons for:

- process inbox now
- rebuild all exports
- create a backup archive
- rebuild one project's exports
- dedupe dry run for a project
- dedupe apply for a project

So you can trigger the main maintenance actions from the browser without dropping back to the terminal.

For hands-off processing, use the inbox watcher. It keeps polling the `pending` folder, writes a heartbeat/status file, and shows its state in the home page UI.

The home page also shows:

- current inbox watcher heartbeat
- Windows Task Scheduler task status for the watcher and daily backup
- latest backup archive path and timestamp

For faster reuse in new AI chats, each project now also has a copy-friendly handoff page:

```text
/projects/<slug>/handoff
```

It shows the latest ready-to-chat text in a large textarea with a browser copy button.

Primary import endpoints:

```text
POST /api/session-logs/import
POST /api/chat-ingest/session
POST /api/prompt-templates/import
POST /api/snapshots/import
POST /api/project-packages/import
GET /api/workspaces
GET /api/workspaces/<slug>
GET /api/workspaces/<slug>/members
POST /api/workspaces/<slug>/members
GET /api/actor
GET /api/mail/status
GET /api/deploy/readiness
GET /api/deploy/env-status
GET /api/deploy/setup
```

API token UI:

```text
GET /settings/api-tokens/
POST /settings/api-tokens/
POST /settings/api-tokens/<id>/revoke
```

Authentication pages:

```text
GET /auth/login
GET /auth/magic/<token>
POST /auth/magic/<token>
POST /auth/logout
```

Context pack endpoints:

```text
GET /api/projects/<slug>/context-pack
GET /api/projects/<slug>/context-pack.txt
GET /api/projects/<slug>/chat-bootstrap
GET /api/projects/<slug>/chat-bootstrap.txt
GET /api/projects/<slug>/ready-for-next-chat
GET /api/projects/<slug>/ready-for-next-chat.txt
GET /api/projects/<slug>/assistant-ready
GET /api/projects/<slug>/assistant-ready.txt
GET /api/handoffs/latest
GET /api/automation-events/latest
GET /api/projects/<slug>/automation-events
GET /api/inbox/watcher-status
GET /api/scheduler/tasks
GET /api/backups/latest
POST /api/backups/create
```

Automatic export files are written under:

```text
data/knowledge_hub/exports/projects/<slug>/
```

Each refreshed project gets:

```text
chat_bootstrap.json
chat_bootstrap.txt
assistant_ready.json
assistant_ready.txt
context_pack.json
context_pack.txt
```

Backup archives are written under:

```text
data/knowledge_hub/backups/
```

Each archive currently includes:

- the SQLite database, when the app is using SQLite
- the generated `exports/` directory
- the `runtime/` directory, including inbox watcher status

## CLI import

Session log:

```powershell
python tools/import_session_log.py session.json
python tools/import_session_log.py session.json --workspace-slug personal
.\tools\import_session_log.ps1 -Path .\session.json
```

Project package:

```powershell
python tools/import_project_package.py --sample
python tools/import_project_package.py .\examples\project_package.sample.json
python tools/import_project_package.py --sample --workspace-slug personal
.\tools\import_project_package.ps1 -Path .\examples\project_package.sample.json
```

Session log dedupe:

```powershell
python tools/dedupe_session_logs.py sample-package-project
python tools/dedupe_session_logs.py sample-package-project --apply
python tools/dedupe_session_logs.py --all
.\tools\dedupe_session_logs.ps1 -ProjectSlug sample-package-project
```

Inbox processing:

```powershell
python tools/process_inbox.py
python tools/process_inbox.py --watch --interval 5
python tools/process_inbox.py --status
python tools/inbox_watcher_status.py
python tools/inbox_watcher_status.py --format json
.\tools\process_inbox.ps1
.\tools\process_inbox.ps1 -Watch -Interval 5
.\tools\start_inbox_watcher.ps1 -Interval 5
.\tools\stop_inbox_watcher.ps1
.\tools\inbox_watcher_status.ps1
.\tools\install_inbox_watcher_task.ps1 -Preview
.\tools\install_inbox_watcher_task.ps1 -Trigger OnLogon -Interval 5
.\tools\inbox_watcher_task_status.ps1
.\tools\remove_inbox_watcher_task.ps1
```

Backup automation:

```powershell
python tools/create_backup_archive.py
.\tools\create_backup_archive.ps1
.\tools\install_daily_backup_task.ps1 -Preview
.\tools\install_daily_backup_task.ps1 -Time 02:00
.\tools\daily_backup_task_status.ps1
.\tools\remove_daily_backup_task.ps1
```

Rebuild exports:

```powershell
python tools/rebuild_exports.py sample-package-project
python tools/rebuild_exports.py --all
.\tools\rebuild_exports.ps1 -ProjectSlug sample-package-project
.\tools\rebuild_exports.ps1 -All
```

Context pack:

```powershell
python tools/context_pack.py sample-package-project
python tools/context_pack.py sample-package-project --format json
```

Assistant-ready export:

```powershell
python tools/assistant_ready.py sample-package-project
python tools/assistant_ready.py sample-package-project --format json
.\tools\assistant_ready.ps1 -ProjectSlug sample-package-project
```

Chat bootstrap export:

```powershell
python tools/chat_bootstrap.py sample-package-project
python tools/chat_bootstrap.py sample-package-project --format json
.\tools\chat_bootstrap.ps1 -ProjectSlug sample-package-project
```

Ready-for-next-chat export:

```powershell
python tools/ready_for_next_chat.py sample-package-project
python tools/ready_for_next_chat.py sample-package-project --format json
.\tools\ready_for_next_chat.ps1 -ProjectSlug sample-package-project
```

Deploy readiness:

```powershell
python tools/deploy_readiness.py
python tools/deploy_readiness.py --format json
.\tools\deploy_readiness.ps1
```

Deploy env status:

```powershell
python tools/deploy_env_status.py
python tools/deploy_env_status.py --format json
.\tools\deploy_env_status.ps1
```

Deploy setup guide:

```powershell
python tools/deploy_setup.py
python tools/deploy_setup.py --format json
.\tools\deploy_setup.ps1
```

Mail testing:

```powershell
python tools/send_test_email.py you@example.com
python tools/send_test_email.py you@example.com --subject "Knowledge Hub SMTP test"
.\tools\send_test_email.ps1 -ToEmail you@example.com
```

API token creation:

```powershell
python tools/create_api_token.py
python tools/create_api_token.py --email you@example.com --label "ChatGPT ingest token"
python tools/create_api_token.py --format json
.\tools\create_api_token.ps1 -Email you@example.com -Label "Codex token"
```

Latest handoffs index:

```powershell
python tools/latest_handoffs.py
python tools/latest_handoffs.py --limit 5 --format json
.\tools\latest_handoffs.ps1 -Limit 5
```

Latest automation events:

```powershell
python tools/latest_automation_events.py
python tools/latest_automation_events.py --project-slug sample-package-project
python tools/latest_automation_events.py --limit 5 --format json
.\tools\latest_automation_events.ps1 -Limit 5
```

## PowerShell API import example

```powershell
$body = Get-Content .\session.json -Raw
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/session-logs/import -Method Post -ContentType "application/json" -Body $body
```

## Chat integration flow

Create a token in the UI or CLI, then use it as a Bearer token.

Fetch project context before a new AI session:

```powershell
$headers = @{ Authorization = "Bearer khp_..." }
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/projects/sample-package-project/ready-for-next-chat -Headers $headers
```

Save a session summary after the AI work is done:

```powershell
$headers = @{ Authorization = "Bearer khp_..." }
$body = Get-Content .\examples\chat_ingest_session.sample.json -Raw
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/chat-ingest/session -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

Starter prompt templates for this flow live in:

```text
examples/chat_start_prompt.sample.txt
examples/chat_finish_prompt.sample.txt
```

Inbox API:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/inbox/status
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/inbox/watcher-status
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/inbox/process -Method Post
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/scheduler/tasks
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/backups/latest
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/backups/create -Method Post
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/projects/sample-package-project/chat-bootstrap
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/projects/sample-package-project/ready-for-next-chat
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/projects/sample-package-project/assistant-ready
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/handoffs/latest
Invoke-RestMethod -Uri http://127.0.0.1:5001/api/automation-events/latest
```

## Project package example

See the ready file:

```text
examples/project_package.sample.json
examples/knowledge_hub_internal_package.json
examples/chat_ingest_session.sample.json
examples/chat_start_prompt.sample.txt
examples/chat_finish_prompt.sample.txt
```

Example structure:

```json
{
  "project": {
    "workspace_slug": "personal",
    "slug": "automation-lab",
    "name": "Automation Lab",
    "current_goal": "Keep a reusable external memory for AI work"
  },
  "session_logs": [
    {
      "source": "chatgpt",
      "task": "Define the package import format",
      "summary": "Use one package import for project + logs + prompts + snapshots",
      "next_step": "Add another package with real project notes"
    }
  ],
  "prompt_templates": [
    {
      "type": "new_chat",
      "title": "New chat prompt",
      "content": "Read the context pack first and keep the response compact."
    }
  ],
  "snapshots": [
    {
      "title": "Current state",
      "content": "The project already supports automatic import and context pack export."
    }
  ]
}
```

## Notes

- UTF-8 with BOM is supported.
- On Windows, prefer importing from a file path instead of piping raw JSON straight into Python from PowerShell.
- If a file is missing, `import_project_package.py` now shows a friendly message and points to the bundled sample.
- Use the ready-for-next-chat export when you want one stable handoff endpoint without deciding between multiple export types.
- Use the chat bootstrap export when you want the shortest possible ready-to-paste handoff for a new AI chat.
- Use the assistant-ready export when you need the shortest practical brief for a new AI chat.
- Use `examples/knowledge_hub_internal_package.json` if you want to dogfood the service and store Knowledge Hub's own project state inside itself.
- `workspace_slug` is optional in imports right now. If you omit it, the project falls back to the default workspace.
- the default owner is bootstrapped automatically from config. By default it uses `owner@knowledge-hub.local`, but you can override it with `KH_DEFAULT_OWNER_EMAIL` and `KH_DEFAULT_OWNER_NAME`.
- actor override is development-only. In production, `?as_user=` and the actor override cookie are ignored.
- signed-in sessions now take priority over the default owner fallback, but in development you can still override the actor for testing.
- when `KH_AUTH_REQUIRED=1`, the default-owner fallback stops being used for private pages and APIs.
- `KH_MAIL_BACKEND=file` is the default mail delivery mode right now. It is great for local testing and staging-like inspection.
- when you are ready for real delivery, switch to `KH_MAIL_BACKEND=smtp` and set:
  - `KH_PUBLIC_BASE_URL`
  - `KH_SMTP_HOST`
  - `KH_SMTP_PORT`
  - `KH_SMTP_USERNAME`
  - `KH_SMTP_PASSWORD`
  - `KH_SMTP_USE_TLS` or `KH_SMTP_USE_SSL`
- `GET /api/mail/status` now shows whether SMTP is configured cleanly, without exposing the password.
- `KH_PUBLIC_BASE_URL` is now used for magic-link email URLs when it is set. This is the safest production path on Render or a custom domain.
- do not enable `KH_AUTH_REQUIRED=1` in production while mail delivery is still `file` or `console`, or you can lock yourself out of the app.
- Exact duplicate session log imports are skipped automatically, so re-importing the same JSON payload does not keep growing the timeline.
- Imports now refresh export files automatically, so the latest assistant-ready brief and context pack stay on disk without a second command.
- Automation events are stored in the database, so you can inspect recent imports, rebuilds, dedupe runs, and inbox failures from the UI, API, or CLI.
- The inbox watcher status file lives at `data/knowledge_hub/runtime/inbox_watcher_status.json` by default.
- If you stop the watcher with `Stop-Process`, the last known state may remain `running` until the heartbeat becomes stale. This is expected and keeps the implementation simple.
- The Task Scheduler helper scripts do not install anything automatically. Use `install_inbox_watcher_task.ps1 -Preview` first if you want to inspect the exact command.
- The daily backup task helper scripts also default to preview-first. Use `install_daily_backup_task.ps1 -Preview` before creating the real scheduled task.
- Inbox folders live under `data/knowledge_hub/inbox/` by default:
  - `pending`
  - `processed`
  - `failed`
