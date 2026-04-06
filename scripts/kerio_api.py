#!/usr/bin/env python3
from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API_TIMEOUT = 30
DEFAULT_KERIO_API_URL = "https://kerio.lo:4040/admin/api/jsonrpc/"
USER_MUTABLE_FIELDS = [
    "id",
    "domainId",
    "loginName",
    "fullName",
    "description",
    "isEnabled",
    "itemSource",
    "authType",
    "role",
    "emailAddresses",
    "emailForwarding",
    "userGroups",
    "itemLimit",
    "diskSizeLimit",
    "hasDomainRestriction",
    "outMessageLimit",
    "publishInGal",
    "cleanOutItems",
    "accessPolicy",
]


class KerioApiError(RuntimeError):
    pass


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def env_or_dotenv(name: str, env_file: Path, default: str | None = None) -> str | None:
    import os

    value = os.environ.get(name)
    if value:
        return value
    return load_env_file(env_file).get(name, default)


class KerioAdminClient:
    def __init__(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        verify_tls: bool = False,
        timeout: int = DEFAULT_API_TIMEOUT,
        application_name: str = "kerio-logstash managed provisioning",
        application_vendor: str = "OpenAI",
        application_version: str = "1.0",
    ) -> None:
        self.api_url = api_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.application_name = application_name
        self.application_vendor = application_vendor
        self.application_version = application_version
        self.context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
        self.token: str | None = None
        self.cookie: str | None = None
        self.request_id = 0

    def __enter__(self) -> "KerioAdminClient":
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.logout()

    def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json-rpc; charset=UTF-8",
            "Accept": "application/json-rpc",
        }
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        if self.token:
            request.add_header("X-Token", self.token)
        if self.cookie:
            request.add_header("Cookie", self.cookie)

        with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            if not self.cookie:
                cookies = response.headers.get_all("Set-Cookie") or []
                if cookies:
                    self.cookie = "; ".join(cookie.split(";", 1)[0] for cookie in cookies)
        return body

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        if self.token:
            payload["token"] = self.token

        response = self._make_request(payload)
        if "error" in response:
            raise KerioApiError(response["error"].get("message", json.dumps(response["error"], ensure_ascii=True)))
        return response.get("result", {})

    def login(self) -> None:
        if self.token:
            return
        result = self.call(
            "Session.login",
            {
                "userName": self.username,
                "password": self.password,
                "application": {
                    "name": self.application_name,
                    "vendor": self.application_vendor,
                    "version": self.application_version,
                },
            },
        )
        token = result.get("token")
        if not token:
            raise KerioApiError("Kerio Session.login did not return a token")
        self.token = token

    def logout(self) -> None:
        if not self.token:
            return
        try:
            self.call("Session.logout")
        finally:
            self.token = None
            self.cookie = None

    @staticmethod
    def raise_for_errors(label: str, errors: list[dict[str, Any]]) -> None:
        if not errors:
            return
        messages = []
        for error in errors:
            index = error.get("inputIndex")
            message = error.get("message", "Kerio API error")
            if index is None:
                messages.append(message)
            else:
                messages.append(f"input[{index}]: {message}")
        raise KerioApiError(f"{label} failed: {'; '.join(messages)}")

    def get_domain(self, domain_name: str) -> dict[str, Any]:
        result = self.call(
            "Domains.get",
            {
                "query": {
                    "fields": ["id", "name", "isPrimary"],
                    "start": 0,
                    "limit": -1,
                    "orderBy": [{"columnName": "name", "direction": "Asc"}],
                }
            },
        )
        for item in result.get("list", []):
            if item.get("name") == domain_name:
                return item
        raise KerioApiError(f"Kerio domain {domain_name} was not found")

    def list_users(self, domain_id: str, fields: list[str]) -> list[dict[str, Any]]:
        result = self.call(
            "Users.get",
            {
                "query": {
                    "fields": fields,
                    "start": 0,
                    "limit": -1,
                    "orderBy": [{"columnName": "loginName", "direction": "Asc"}],
                },
                "domainId": domain_id,
            },
        )
        return result.get("list", [])

    def create_users(self, users: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = self.call("Users.create", {"users": users})
        self.raise_for_errors("Users.create", result.get("errors", []))
        return result.get("result", [])

    def remove_users(self, user_ids: list[str]) -> None:
        if not user_ids:
            return
        result = self.call(
            "Users.remove",
            {
                "requests": [
                    {
                        "userId": user_id,
                        "method": "UDeleteFolder",
                        "removeReferences": True,
                        "targetUserId": "",
                        "mode": "DSModeDelete",
                    }
                    for user_id in user_ids
                ]
            },
        )
        self.raise_for_errors("Users.remove", result.get("errors", []))

    def users_by_login(self, domain_id: str, fields: list[str]) -> dict[str, dict[str, Any]]:
        return {
            item["loginName"]: item
            for item in self.list_users(domain_id, fields)
            if isinstance(item.get("loginName"), str)
        }

    def set_user_email_addresses(self, domain_id: str, user_id: str, email_local_parts: list[str]) -> None:
        users = self.list_users(domain_id, USER_MUTABLE_FIELDS)
        row = next((item for item in users if item.get("id") == user_id), None)
        if row is None:
            raise KerioApiError(f"Kerio user {user_id} was not found for alias update")

        pattern = dict(row)
        pattern.pop("id", None)
        access_policy = row.get("accessPolicy", {})
        pattern["accessPolicy"] = {"id": access_policy.get("id", "")}
        pattern["emailAddresses"] = sorted(dict.fromkeys(email_local_parts))

        result = self.call("Users.set", {"userIds": [user_id], "pattern": pattern})
        self.raise_for_errors("Users.set", result.get("errors", []))
