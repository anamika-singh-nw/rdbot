"""Amazon Bedrock access (Converse API) — runs on AWS credits, e.g. Amazon Nova Pro.

Credentials, in order:
- On Vercel: the request's Vercel OIDC token is exchanged for short-lived credentials of
  the IAM role in AWS_ROLE_ARN (no AWS keys are stored anywhere). That role can only call
  the configured model.
- Locally: boto3's default chain (e.g. after `aws login`).
"""

from __future__ import annotations

import os
import threading
import time

import boto3

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0")
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

_lock = threading.Lock()
_cached: dict = {"client": None, "expires": 0.0}


def client(oidc_token: str | None = None):
    role = os.environ.get("AWS_ROLE_ARN")
    if not (role and oidc_token):
        with _lock:
            if _cached["client"] is None:
                _cached["client"] = boto3.client("bedrock-runtime", region_name=REGION)
            return _cached["client"]
    with _lock:
        if _cached["client"] is not None and time.time() < _cached["expires"]:
            return _cached["client"]
        creds = boto3.client("sts", region_name=REGION).assume_role_with_web_identity(
            RoleArn=role, RoleSessionName="rxdxbot", WebIdentityToken=oidc_token, DurationSeconds=3600
        )["Credentials"]
        _cached["client"] = boto3.client(
            "bedrock-runtime",
            region_name=REGION,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        _cached["expires"] = creds["Expiration"].timestamp() - 300  # refresh 5 min early
        return _cached["client"]


def text_of(message: dict) -> str:
    return "".join(b.get("text", "") for b in message.get("content", [])).strip()
