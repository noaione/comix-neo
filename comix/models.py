"""
MIT License

Copyright (c) 2022-present noaione

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Type

__all__ = (
    "ComicImage",
    "ComicIssue",
    "ComicData",
    "AmazonDevice",
    "AmazonAccount",
)


@dataclass
class ComicImage:
    url: str
    digest: bytes


@dataclass
class ComicIssue:
    id: str
    title: str
    series_id: Optional[str]
    volume: Optional[int]
    issue: Optional[int]

    @classmethod
    def from_proto(cls: Type[ComicIssue], issue: Any):
        volume = None
        chapter = None
        series_id = None

        if issue.volume != "":
            volume = int(issue.volume)
        if issue.issue != "":
            chapter = int(issue.issue)
        if issue.series_id != "":
            series_id = issue.series_id

        return cls(issue.id, issue.title, series_id, volume, chapter)

    @property
    def release_name(self):
        regex = r"\.|\?|\\|/|<|>|\"|'|%|\*|\&|\+|\-|\#|\!"
        release_name = re.sub(r"\s+", " ", re.sub(regex, "", self.title).replace(":", "-"))
        if self.volume:
            release_name += f" - v{self.volume:02d}"
        elif self.issue:
            release_name += f" - {self.issue:03d}"
        return release_name


@dataclass
class ComicData:
    id: str
    title: str
    publisher_id: str
    version: str
    issue: Optional[ComicIssue]
    images: List[ComicImage]

    @property
    def release_name(self):
        if self.issue is not None:
            return self.issue.release_name

        regex = r"\.|\?|\\|/|<|>|\"|'|%|\*|\&|\+|\-|\#|\!"
        release_name = re.sub(r"\s+", " ", re.sub(regex, "", self.title).replace(":", "-"))
        return f"{release_name} ({self.id})"

    @property
    def int_id(self):
        if isinstance(self.id, int):
            return self.id
        return int(self.id)


@dataclass
class AmazonDevice:
    name: str
    serial: str
    type: str

    @classmethod
    def from_data(cls: Type[AmazonDevice], data: dict):
        return cls(data["device_name"], data["device_serial_number"], data["device_type"])

    @classmethod
    def from_dict(cls: Type[AmazonDevice], data: dict):
        return cls(data["name"], data["serial"], data["type"])

    def to_dict(self):
        return {
            "name": self.name,
            "serial": self.serial,
            "type": self.type,
        }


@dataclass
class AmazonAccount:
    id: str
    name: str
    email: str
    password: str
    region: str
    pool: Optional[str]
    domain: str
    device: AmazonDevice
    access_token: str
    refresh_token: str
    private_key: str
    adp_token: str
    expire_at: int

    def is_expired(self):
        return self.expire_at < int(datetime.now(timezone.utc).timestamp())

    def update_expiry(self, expires_in: int):
        self.expire_at = int(datetime.now(timezone.utc).timestamp()) + expires_in

    @classmethod
    def from_data(cls: Type[AmazonAccount], data: dict, email: str, password: str, domain: str):
        success_response = data.get("response", {}).get("success", {})
        if not success_response:
            raise ValueError("Invalid response")

        extensions = success_response.get("extensions", {})
        if not extensions:
            raise ValueError("Missing extensions data, needed for account info")

        device_info = extensions.get("device_info", {})
        if not device_info:
            raise ValueError("Missing device info")
        cust_info = extensions.get("customer_info", {})
        if not cust_info:
            raise ValueError("Missing customer info")
        tokens = success_response.get("tokens", {})
        if not tokens:
            raise ValueError("Missing tokens")
        bearer_token = tokens.get("bearer", {})
        if not bearer_token:
            raise ValueError("Missing bearer token")
        mac_dms = tokens.get("mac_dms", {})
        if not mac_dms:
            raise ValueError("Missing MAC DMS token")

        cust_id = cust_info["user_id"]
        cust_name = cust_info["name"]
        cust_region = cust_info["home_region"]
        cust_pool = cust_info.get("account_pool")

        tkn_access = bearer_token["access_token"]
        tkn_refresh = bearer_token["refresh_token"]

        device_priv_key = mac_dms["device_private_key"]
        adp_token = mac_dms["adp_token"]

        current_time = datetime.now(tz=timezone.utc).timestamp()
        expire_at = current_time + int(bearer_token["expires_in"])

        device_info_parsed = AmazonDevice.from_data(device_info)

        return cls(
            cust_id,
            cust_name,
            email,
            password,
            cust_region,
            cust_pool,
            domain,
            device_info_parsed,
            tkn_access,
            tkn_refresh,
            device_priv_key,
            adp_token,
            expire_at,
        )

    @classmethod
    def from_dict(cls: Type[AmazonAccount], data: dict):
        return cls(
            data["id"],
            data["name"],
            data["email"],
            data["password"],
            data["region"],
            data["pool"],
            data["domain"],
            AmazonDevice.from_dict(data["device"]),
            data["access_token"],
            data["refresh_token"],
            data["private_key"],
            data["adp_token"],
            data["expire_at"],
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "password": self.password,
            "region": self.region,
            "pool": self.pool,
            "domain": self.domain,
            "device": self.device.to_dict(),
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "private_key": self.private_key,
            "adp_token": self.adp_token,
            "expire_at": self.expire_at,
        }
