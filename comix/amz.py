from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import logging
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_bytes, token_hex
from typing import Optional, Type, Union
from uuid import uuid4

import requests
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

from .constants import USER_PATH

logger = logging.getLogger("AmazonAuth")

APP_NAME = "com.amazon.avod.thirdpartyclient"
APP_VERSION = "296016847"
DEVICE_NAME = "walleye/google/Pixel 2"
MANUFACTURER = "Google"
OS_VERSION = "google/walleye/walleye:8.1.0/OPM1.171019.021/4565141:user/release-keys"


class AuthFailed(Exception):
    pass


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
    region: str
    pool: Optional[str]
    domain: str
    device: AmazonDevice
    access_token: str
    refresh_token: str
    expire_at: int

    def is_expired(self):
        return self.expire_at < int(datetime.now(timezone.utc).timestamp())

    def update_expiry(self, expires_in: int):
        self.expire_at = int(datetime.now(timezone.utc).timestamp()) + expires_in

    @classmethod
    def from_data(cls: Type[AmazonAccount], data: dict, email: str, domain: str):
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

        cust_id = cust_info["user_id"]
        cust_name = cust_info["name"]
        cust_region = cust_info["home_region"]
        cust_pool = cust_info.get("account_pool")

        tkn_access = bearer_token["access_token"]
        tkn_refresh = bearer_token["refresh_token"]

        current_time = datetime.now(tz=timezone.utc).timestamp()
        expire_at = current_time + int(bearer_token["expires_in"])

        device_info_parsed = AmazonDevice.from_data(device_info)

        return cls(
            cust_id,
            cust_name,
            email,
            cust_region,
            cust_pool,
            domain,
            device_info_parsed,
            tkn_access,
            tkn_refresh,
            expire_at,
        )

    @classmethod
    def from_dict(cls: Type[AmazonAccount], data: dict):
        return cls(
            data["id"],
            data["name"],
            data["email"],
            data["region"],
            data["pool"],
            data["domain"],
            AmazonDevice.from_dict(data["device"]),
            data["access_token"],
            data["refresh_token"],
            data["expire_at"],
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "region": self.region,
            "pool": self.pool,
            "domain": self.domain,
            "device": self.device.to_dict(),
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expire_at": self.expire_at,
        }


class AmazonAuth:
    def __init__(self, email: str, password: str, device_id: str, domain: str = "com"):
        self._email: str = email
        self._password: str = password
        self._domain: str = domain
        self._device_id: str = device_id
        self._account: Optional[AmazonAccount] = None

        USER_PATH.mkdir(exist_ok=True, parents=True)
        email_hash = b64encode(self._email.encode()).decode()
        self._token_path = USER_PATH / f"token_{email_hash}.{self._domain}.json"

    def _pkcs7_pad(self, data: Union[str, bytes]) -> bytes:
        padsize = 16 - len(data) % 16
        return data + bytes([padsize]) * padsize

    def _pkcs7_unpad(self, data: bytes) -> bytes:
        offset = data[-1]
        return data[:-offset]

    def _get_headers(self):
        return {
            "Accept-Charset": "utf-8",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Pixel 2 Build/OPM1.171019.021)",
            "x-amzn-identity-auth-domain": f"api.amazon.{self._domain}",
            "x-amzn-requestid": str(uuid4()),
        }

    def _generate_frc(self):
        cookies = json.dumps(
            {
                "ApplicationName": APP_NAME,
                "ApplicationVersion": APP_VERSION,
                "DeviceLanguage": "en",
                "DeviceName": DEVICE_NAME,
                "DeviceOSVersion": OS_VERSION,
                "IpAddress": requests.get("https://api.ipify.org").text,
                "ScreenHeightPixels": "1920",
                "ScreenWidthPixels": "1280",
                "TimeZone": "00:00",
            }
        )

        compressed = gzip.compress(cookies.encode())

        key = PBKDF2(self._device_id, b"AES/CBC/PKCS7Padding")
        iv = token_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        ciphertext = cipher.encrypt(self._pkcs7_pad(compressed))

        hmac_ = hmac.new(PBKDF2(self._device_id, b"HmacSHA256"), iv + ciphertext, hashlib.sha256).digest()

        return base64.b64encode(b"\0" + hmac_[:8] + iv + ciphertext).decode()

    @property
    def hash_pass(self):
        first = self._password[0]
        last = self._password[-1]
        length = len(self._password) - 2
        if length < 0:
            return "**"
        return f"{first}{'*' * length}{last}"

    def authenticate(self) -> None:
        body = {
            "auth_data": {
                "use_global_authentication": "true",
                "user_id_password": {
                    "password": self._password,
                    "user_id": self._email,
                },
            },
            "registration_data": {
                "domain": "DeviceLegacy",
                "device_type": "A43PXU4ZN2AL1",
                "device_serial": self._device_id,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_model": DEVICE_NAME,
                "os_version": OS_VERSION,
                "software_version": "130050002",
            },
            "requested_token_type": ["bearer", "mac_dms", "store_authentication_cookie", "website_cookies"],
            "cookies": {"domain": f"amazon.{self._domain}", "website_cookies": []},
            "user_context_map": {"frc": self._generate_frc()},
            "device_metadata": {
                "device_os_family": "android",
                "device_type": "A43PXU4ZN2AL1",
                "device_serial": self._device_id,
                "mac_address": token_hex(64).upper(),
                "manufacturer": MANUFACTURER,
                "model": DEVICE_NAME,
                "os_version": "30",
                "android_id": "f1c56f6030b048a7",
                "product": DEVICE_NAME,
            },
            "requested_extensions": ["device_info", "customer_info"],
        }
        logger.info(f"Authenticating with {self._email} and {self.hash_pass}")

        response_json = requests.post(
            f"https://api.amazon.{self._domain}/auth/register", headers=self._get_headers(), json=body
        ).json()
        try:
            amz_account = AmazonAccount.from_data(response_json, self._email, self._domain)
            logger.info(f"Authenticated to {amz_account.name} (Device: {amz_account.device.name})")
            self._account = amz_account
        except (KeyError, TypeError, ValueError):
            print(json.dumps(response_json, indent=2))
            raise

    def refresh_token(self):
        if self._account is None:
            self.authenticate()
            return

        if self._password is None:
            logger.warning("No password set, cannot refresh token")
            raise AuthFailed("Missing password")

        body = {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "source_token_type": "refresh_token",
            "source_token": self._account.refresh_token,
            "requested_token_type": "access_token",
        }

        logger.info(f"Refreshing token for {self._account.name}")
        response_json = requests.post(
            "https://api.amazon.com/auth/token", headers=self._get_headers(), json=body
        ).json()
        try:
            self._account.access_token = response_json["access_token"]
            # TODO: Get actual expiry time
            logger.info(f"Refreshed token for {self._account.name}")
            self._account.update_expiry(3600)
            with self._token_path.open("w") as f:
                json.dump(self._account.to_dict(), f)
        except (ValueError, TypeError, KeyError):
            print(json.dumps(response_json))
            raise

    def login(self):
        token_path = self._token_path
        if token_path.exists():
            logger.info("Loading token from file")
            with token_path.open() as f:
                self._account = AmazonAccount.from_dict(json.load(f))

            if self._account.is_expired():
                try:
                    self.refresh_token()
                except Exception:
                    self.authenticate()
                    with token_path.open("w") as f:
                        logger.info("Saving token to file")
                        json.dump(self._account.to_dict(), f)
            return

        self.authenticate()
        with token_path.open("w") as f:
            logger.info("Saving token to file")
            json.dump(self._account.to_dict(), f)

    @property
    def account(self):
        return self._account

    @property
    def token(self):
        if self._account is None:
            self.login()
        if self._account.is_expired():
            self.refresh_token()
        return self._account.access_token


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("email", help="email")
    parser.add_argument("password", help="password")
    parser.add_argument("-d", "--domain", default="com", help="domain")
    args = parser.parse_args()

    print("Login...")
    amz = AmazonAuth(args.email, args.password, "f245bb5cce9f2e7fb6bb9b6d7dfe85fa", args.domain)
    amz.login()
    print(amz.account)
