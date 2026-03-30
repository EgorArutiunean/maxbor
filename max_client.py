import logging
import time
from typing import Any
from urllib.parse import urlparse

import requests


def normalize_max_target(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise RuntimeError("TARGET_MAX_CHAT is empty")

    if raw.lstrip("-").isdigit():
        return raw

    if raw.startswith("@"):
        return raw[1:].lower()

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        path = parsed.path.strip("/")
        if not path:
            raise RuntimeError(f"Invalid MAX link: {raw}")
        return path.lower()

    return raw.strip("/").lower()


class MaxClient:
    def __init__(
        self,
        bot_token: str,
        target_chat: str,
        instance_name: str,
        logger: logging.Logger,
    ) -> None:
        self.api = "https://platform-api.max.ru"
        self.target_chat = target_chat
        self.instance_name = instance_name
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"Authorization": bot_token})
        self.bot_token = bot_token
        self._target_recipient: dict[str, int] | None = None

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

    def iter_chats(self) -> list[dict[str, Any]]:
        chats: list[dict[str, Any]] = []
        marker: int | None = None

        while True:
            params: dict[str, Any] = {"count": 100}
            if marker is not None:
                params["marker"] = marker

            resp = self.session.get(
                f"{self.api}/chats",
                params=params,
                timeout=30,
            )
            if not resp.ok:
                payload = self._json_or_text_payload(resp)
                raise RuntimeError(
                    f"MAX chats lookup failed: status={resp.status_code}, body={payload}"
                )
            data = self._json_or_text_payload(resp)

            chats.extend(data.get("chats", []))
            marker = data.get("marker")
            if marker is None:
                return chats

    def resolve_recipient(self) -> dict[str, int]:
        normalized_target = normalize_max_target(self.target_chat)

        if normalized_target.lstrip("-").isdigit():
            return {"chat_id": int(normalized_target)}

        chats = self.iter_chats()

        for chat in chats:
            link = (chat.get("link") or "").strip()
            title = (chat.get("title") or "").strip().lower()
            dialog_user = chat.get("dialog_with_user") or {}
            dialog_username = (dialog_user.get("username") or "").strip().lower()

            candidates = {
                title,
                dialog_username,
                normalize_max_target(link) if link else "",
            }

            if normalized_target in candidates:
                return {"chat_id": int(chat["chat_id"])}

        self.logger.warning(
            "MAX target was not resolved. target=%s available_chats=%s",
            normalized_target,
            [
                {
                    "chat_id": chat.get("chat_id"),
                    "title": chat.get("title"),
                    "link": chat.get("link"),
                    "username": (chat.get("dialog_with_user") or {}).get("username"),
                }
                for chat in chats[:20]
            ],
        )

        raise RuntimeError(
            "Could not resolve TARGET_MAX_CHAT into chat_id. "
            "Open the dialog first or configure a numeric chat_id."
        )

    def get_target_recipient(self) -> dict[str, int]:
        if self._target_recipient is None:
            self._target_recipient = self.resolve_recipient()
            self.logger.info(
                "[%s] Resolved MAX recipient: %s",
                self.instance_name,
                self._target_recipient,
            )

        return self._target_recipient

    def get_upload_slot(self, kind: str) -> dict[str, Any]:
        resp = self.session.post(
            f"{self.api}/uploads",
            params={"type": kind},
            timeout=30,
        )
        if not resp.ok:
            payload = self._json_or_text_payload(resp)
            raise RuntimeError(
                f"MAX upload slot request failed: type={kind}, status={resp.status_code}, body={payload}"
            )
        data = self._json_or_text_payload(resp)

        if "url" not in data:
            raise RuntimeError(f"MAX /uploads did not return url: {data}")

        return data

    def upload_file(
        self,
        kind: str,
        filename: str,
        blob: bytes,
        mime_type: str | None,
    ) -> dict[str, Any]:
        slot = self.get_upload_slot(kind)
        upload_url = slot["url"]

        files = {
            "data": (filename, blob, mime_type or "application/octet-stream")
        }

        resp = requests.post(
            upload_url,
            headers={"Authorization": self.bot_token},
            files=files,
            timeout=300,
        )

        if resp.status_code in (400, 401, 403):
            resp = requests.post(
                upload_url,
                files=files,
                timeout=300,
            )

        if not resp.ok:
            payload = self._json_or_text_payload(resp)
            raise RuntimeError(
                f"MAX file upload failed: type={kind}, filename={filename}, "
                f"status={resp.status_code}, body={payload}"
            )
        upload_result = self._json_or_text_payload(resp)

        if "token" in upload_result:
            payload = upload_result
        elif "token" in slot:
            payload = {"token": slot["token"]}
        elif not upload_result:
            raise RuntimeError(
                f"MAX upload succeeded with empty response but no token was provided: "
                f"type={kind}, status={resp.status_code}"
            )
        else:
            payload = upload_result

        return {
            "type": kind,
            "payload": payload,
        }

    def send_message(
        self,
        text: str | None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        recipient = self.get_target_recipient()
        body: dict[str, Any] = {}

        if text:
            body["text"] = text[:4000]

        if attachments:
            body["attachments"] = attachments

        if not body:
            body["text"] = "[Empty post]"

        for attempt in range(6):
            resp = self.session.post(
                f"{self.api}/messages",
                params=recipient,
                json=body,
                timeout=60,
            )

            if resp.ok:
                return resp.json()

            err_text = resp.text
            try:
                err_json = resp.json()
            except Exception:
                err_json = {"raw": err_text}

            if err_json.get("code") == "attachment.not.ready":
                sleep_s = 1.5 * (attempt + 1)
                self.logger.warning(
                    "[%s] MAX attachment is not ready yet, retrying in %.1fs",
                    self.instance_name,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            raise RuntimeError(
                f"MAX send failed: chat_id={recipient.get('chat_id')}, status={resp.status_code}, body={err_json}"
            )

        raise RuntimeError("MAX attachment.not.ready after retries")
