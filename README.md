# maxbor

`maxbor` is a one-way bridge that reposts posts from a Telegram channel into a MAX chat.

## What it does

- Reads `channel_post` updates from Telegram via long polling.
- Filters posts from one configured Telegram source channel.
- Forwards text and supported attachments into one configured MAX chat.
- Groups Telegram media albums before sending them to MAX.

## Configuration

Create `.env` from `.env.example` and set:

- `TELEGRAM_BOT_TOKEN`
- `MAX_BOT_TOKEN`
- `SOURCE_TG_CHAT`
- `TARGET_MAX_CHAT`
- `INSTANCE_NAME`
- `MAX_ATTACHMENT_SIZE_BYTES`
- `HEALTHCHECK_ENABLED`
- `HEALTHCHECK_HOST`
- `HEALTHCHECK_PORT`
- `HEALTHCHECK_STALE_AFTER_SEC`

`SOURCE_TG_CHAT` can be a numeric chat id, `@username`, or Telegram link.

`TARGET_MAX_CHAT` can be a numeric chat id, `@username`, or MAX link.

`MAX_ATTACHMENT_SIZE_BYTES` is a safety limit for a single downloaded Telegram attachment before upload to MAX. Default: `52428800` bytes.

If `HEALTHCHECK_ENABLED=true`, the process starts a local endpoint at `/healthz`. Default bind: `0.0.0.0:8080`.

Use a unique `INSTANCE_NAME` and `STATE_FILE` for each bridge instance so logs and Telegram offsets do not overlap.

Current scope of `maxbor`:

- One-way delivery: `Telegram channel -> MAX chat`.
- One Telegram source and one MAX destination per process.
- Supported content: text, photo, document, video, audio, voice, animation, and Telegram media albums.
- Not supported in this version: reverse sync, edits, deletions, reactions, comments, and multi-route bridging.

## Run with Docker

```bash
docker compose up -d --build
```

Local `docker compose` will automatically read variables from `.env`.

## Run locally

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python app.py
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Deployment

See `VM_SETUP.md`.

## Deploy to Coolify

Use a Docker Compose deployment for this project. It is a background worker with persistent state and no public HTTP port.

The healthcheck endpoint is local to the container and does not require publishing a port.

In Coolify:

1. Create a new resource from the `maxbor` GitHub repository.
2. Select the `Docker Compose` deployment type.
3. Use `compose.yaml` from the repository.
4. Do not configure a domain or exposed port for this service.
5. Set these environment variables in Coolify:
   `TELEGRAM_BOT_TOKEN`, `MAX_BOT_TOKEN`, `SOURCE_TG_CHAT`, `TARGET_MAX_CHAT`, `INSTANCE_NAME`, `MAX_ATTACHMENT_SIZE_BYTES`, `HEALTHCHECK_ENABLED`, `HEALTHCHECK_HOST`, `HEALTHCHECK_PORT`, `HEALTHCHECK_STALE_AFTER_SEC`, `STATE_FILE`.
6. Leave `STATE_FILE` as `/app/data/maxbor-state.json` unless you have a reason to change it.
7. Deploy and verify logs contain `[maxbor] Telegram -> MAX bridge started`.
