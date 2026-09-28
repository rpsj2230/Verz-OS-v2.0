"""Lark's event and API envelopes, as its documentation records them, and a sender that seals them.

**Where each shape comes from, since no request here reaches Lark.** The event envelope
(`schema` 2.0, a `header` with `event_type` and `token`, an `event` with `sender` and `message`) and
the `url_verification` challenge are the ones Lark's server SDK parses in
`larksuite/oapi-sdk-python`, `lark_oapi/event/dispatcher_handler.py`; the message fields, the
mention block and `sender_type` are those `chyroc/lark`'s generated `api_message_send.go` records
from Lark's "Receive message" and "Send message" pages; the members page is
`api_chat_member_get_list.go` (items of `member_id_type`, `member_id`, `name`, `tenant_key`, then
`page_token`, `has_more`, `member_total`), and the ephemeral answer `api_message_send_ephemeral.go`.

**The seal is written from the algorithm, not from `brain.channels.lark`.** AES-256-CBC under
sha256 of the Encrypt Key with a random IV first, PKCS#7, base64, and a signature of sha256 over
the time, the nonce, the key and the exact bytes, as `decryptor.py` and `_verify_sign` do it. A
test that sealed with the module's own functions would pass with both halves wrong the same way,
which is why the documented worked example ("test key" opening to "hello world") is held apart.

Task ids: M10.2.1, M10.2.2
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any, Final

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

#: Lark's own worked example for its event encryption, from the event subscription guide.
DOCUMENTED_KEY: Final = "test key"
DOCUMENTED_SEALED: Final = "P37w+VZImNgPEO1RBhJ6RtKl7n6zymIbEG1pReEzghk="
DOCUMENTED_OPENED: Final = b"hello world"

#: Test values for one app. Never real: a real app's values are pasted by its owner, into a vault.
APP_ID: Final = "cli_a1b2c3d4e5f6a7b8"
APP_SECRET: Final = "lark-app-secret-for-tests-0001"
ENCRYPT_KEY: Final = "lark-encrypt-key-for-tests-0001"
VERIFICATION_TOKEN: Final = "lark-verification-token-0001"
BOT_OPEN_ID: Final = "ou_bot0000000000000000000000001"


def seal(plain: bytes, encrypt_key: str = ENCRYPT_KEY, iv: bytes | None = None) -> str:
    """Encrypt as Lark does: the IV first, then the ciphertext, all in base64."""
    vector = iv if iv is not None else os.urandom(16)
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(vector)).encryptor()
    return base64.b64encode(vector + encryptor.update(padded) + encryptor.finalize()).decode()


def signed(
    event: Mapping[str, Any],
    *,
    encrypt_key: str = ENCRYPT_KEY,
    at: int | None = None,
    nonce: str = "nonce-0001",
    sign: bool = True,
) -> tuple[bytes, dict[str, str]]:
    """An event as Lark posts it: sealed into `{"encrypt": ...}`, with its three headers."""
    raw = json.dumps({"encrypt": seal(json.dumps(event).encode("utf-8"), encrypt_key)}).encode()
    headers = {"content-type": "application/json"}
    if sign:
        stamp = str(int(time.time()) if at is None else at)
        material = (stamp + nonce + encrypt_key).encode("utf-8") + raw
        headers |= {
            "x-lark-request-timestamp": stamp,
            "x-lark-request-nonce": nonce,
            "x-lark-signature": hashlib.sha256(material).hexdigest(),
        }
    return raw, headers


def challenge(token: str = VERIFICATION_TOKEN, value: str = "challenge-0001") -> dict[str, str]:
    """Lark's address check, as it arrives before any event: a challenge to echo, and the token."""
    return {"challenge": value, "token": token, "type": "url_verification"}


def mention(open_id: str, key: str = "@_user_1", name: str = "Brain") -> dict[str, Any]:
    """One mention as a received message carries it: a placeholder, the ids, a display name."""
    return {"key": key, "id": {"open_id": open_id, "union_id": "on_x", "user_id": ""}, "name": name}


def message(
    *,
    sender: str,
    text: str,
    chat_id: str = "oc_chat0000000000000000000000001",
    chat_type: str = "p2p",
    message_id: str = "om_0001",
    mentions: Sequence[Mapping[str, Any]] = (),
    token: str = VERIFICATION_TOKEN,
    sender_type: str = "user",
    event_type: str = "im.message.receive_v1",
    create_time: int | None = None,
) -> dict[str, Any]:
    """An `im.message.receive_v1` event, schema 2.0."""
    created = str((int(time.time()) if create_time is None else create_time) * 1000)
    return {
        "schema": "2.0",
        "header": {
            "event_id": f"ev_{message_id}",
            "event_type": event_type,
            "create_time": created,
            "token": token,
            "app_id": APP_ID,
            "tenant_key": "tenant-0001",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": sender, "union_id": "on_s", "user_id": "u_s"},
                "sender_type": sender_type,
                "tenant_key": "tenant-0001",
            },
            "message": {
                "message_id": message_id,
                "root_id": "",
                "parent_id": "",
                "create_time": created,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": text}),
                "mentions": list(mentions),
            },
        },
    }


def members_page(open_ids: Sequence[str], *, more: str = "") -> dict[str, Any]:
    """One page of a chat's members, as `GET /open-apis/im/v1/chats/:chat_id/members` answers."""
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "items": [
                {"member_id_type": "open_id", "member_id": one, "name": "N", "tenant_key": "t"}
                for one in open_ids
            ],
            "page_token": more,
            "has_more": bool(more),
            "member_total": len(open_ids),
        },
    }


#: What Lark answers a send it accepted, and one it refused inside a 200.
SENT: Final = {"code": 0, "msg": "success", "data": {"message_id": "om_reply0001"}}
REFUSED_IN_A_200: Final = {"code": 230002, "msg": "Bot is not in the chat"}
RATE_LIMITED: Final = {"code": 99991400, "msg": "request trigger frequency limit"}
