# VM setup

Assumption: Ubuntu or Debian VM with outbound HTTPS access.

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

## 2. Copy project to VM

Create target directory:

```bash
sudo mkdir -p /opt/maxbor
sudo chown $USER:$USER /opt/maxbor
```

Copy these files into `/opt/maxbor`:

- `app.py`
- `.env`
- `.env.example`
- `requirements.txt`
- `maxbor-bridge.service`

Recommended `.env` values for this instance:

```env
INSTANCE_NAME=maxbor
STATE_FILE=/opt/maxbor/state.json
```

## 3. Create virtualenv and install deps

```bash
cd /opt/maxbor
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 4. Quick manual run

```bash
cd /opt/maxbor
./venv/bin/python app.py
```

Expected startup log:

```text
[maxbor] Telegram -> MAX bridge started
```

Stop with `Ctrl+C`.

## 5. Configure systemd

Replace `YOUR_LINUX_USER` in `maxbor-bridge.service` with your actual VM user.

Install service:

```bash
sudo cp /opt/maxbor/maxbor-bridge.service /etc/systemd/system/maxbor-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable maxbor-bridge
sudo systemctl start maxbor-bridge
```

## 6. Check logs

```bash
sudo systemctl status maxbor-bridge
sudo journalctl -u maxbor-bridge -f
```

## 7. Common checks

- Telegram bot must be admin in the source channel.
- MAX bot must have access to the target chat/dialog.
- `TARGET_MAX_CHAT` in `.env` can be a link, username, or numeric `chat_id`.
- Use a unique `STATE_FILE` for each deployed bridge instance.
- VM must allow outbound HTTPS to `api.telegram.org` and `platform-api.max.ru`.
