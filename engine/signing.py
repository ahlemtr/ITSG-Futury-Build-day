"""Signing: SHA-256 of each input file and of the report JSON, Ed25519 signature."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def load_key(path: str | Path | None = None) -> Ed25519PrivateKey:
    """Key at SIGNING_KEY_PATH, created if missing."""
    p = Path(path or os.environ.get("SIGNING_KEY_PATH", "data/keys/ed25519.pem"))
    if p.exists():
        return serialization.load_pem_private_key(p.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return key


def _pub_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def sign(report: dict, key: Ed25519PrivateKey | None = None) -> dict:
    """-> {"report": ..., "signature": {algorithm, json_sha256, value, public_key}}"""
    key = key or load_key()
    body = canonical(report)
    return {"report": report, "signature": {"algorithm": "Ed25519", "json_sha256": sha256(body),
                                            "value": base64.b64encode(key.sign(body)).decode(),
                                            "public_key": _pub_b64(key)}}


def verify(signed: dict, public_key_b64: str | None = None) -> bool:
    sig = signed["signature"]
    body = canonical(signed["report"])
    if sha256(body) != sig["json_sha256"]:
        return False
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64 or sig["public_key"]))
    try:
        pub.verify(base64.b64decode(sig["value"]), body)
        return True
    except InvalidSignature:
        return False


def verify_bytes(signed_json: bytes) -> bool:
    try:
        return verify(json.loads(signed_json))
    except (ValueError, KeyError):
        return False
