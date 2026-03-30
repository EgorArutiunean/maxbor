import json
import mimetypes
from typing import Any

import requests


class TelegramClient:
    def __init__(self, bot_token: str, poll_timeout: int) -> None:
        self.poll_timeout = poll_timeout
        self.allowed_updates = ["channel_post"]
        self.api = f"https://api.telegram.org/bot{bot_token}"
        self.file_api = f"https://api.telegram.org/file/bot{bot_token}"
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def _json_or_text_payload(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"payload": payload}
        except ValueError:
            return {"raw": response.text}

    def _ensure_ok(self, response: requests.Response, action: str) -> dict[str, Any]:
        if not response.ok:
            payload = self._json_or_text_payload(response)
            raise RuntimeError(
                f"Telegram {action} failed: status={response.status_code}, body={payload}"
            )

        data = self._json_or_text_payload(response)
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {action} failed: {data}")

        return data

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        params = {
            "timeout": self.poll_timeout,
            "allowed_updates": json.dumps(self.allowed_updates),
        }
        if offset is not None:
            params["offset"] = offset

        resp = self.session.get(
            f"{self.api}/getUpdates",
            params=params,
            timeout=self.poll_timeout + 10,
        )
        data = self._ensure_ok(resp, "getUpdates")
        return data["result"]

    def get_webhook_info(self) -> dict[str, Any]:
        resp = self.session.get(f"{self.api}/getWebhookInfo", timeout=30)
        data = self._ensure_ok(resp, "getWebhookInfo")
        return data["result"]

    def delete_webhook(self) -> None:
        resp = self.session.post(
            f"{self.api}/deleteWebhook",
            params={"drop_pending_updates": "false"},
            timeout=30,
        )
        self._ensure_ok(resp, "deleteWebhook")

    def get_file_info(self, file_id: str) -> dict[str, Any]:
        resp = self.session.get(
            f"{self.api}/getFile",
            params={"file_id": file_id},
            timeout=30,
        )
        data = self._ensure_ok(resp, "getFile")
        return data["result"]

    def download_file(self, file_id: str) -> tuple[bytes, str, str | None, int | None]:
        info = self.get_file_info(file_id)
        file_path = info.get("file_path")
        if not file_path:
            raise RuntimeError(f"Telegram getFile returned no file_path for file_id={file_id}")
        filename = file_path.split("/")[-1]
        mime_type, _ = mimetypes.guess_type(filename)
        file_size = info.get("file_size")

        resp = self.session.get(f"{self.file_api}/{file_path}", timeout=180)
        if not resp.ok:
            payload = self._json_or_text_payload(resp)
            raise RuntimeError(
                f"Telegram file download failed: file_id={file_id}, "
                f"status={resp.status_code}, body={payload}"
            )

        return resp.content, filename, mime_type, file_size
