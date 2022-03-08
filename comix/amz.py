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

import base64
import gzip
import hashlib
import hmac
import json
import logging
import time
from base64 import b64decode, b64encode
from datetime import datetime
from secrets import token_bytes, token_hex
from typing import Any, Optional, Union
from urllib.parse import urlparse
from uuid import uuid4

import requests
import xmltodict
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

from .constants import USER_PATH
from .models import AmazonAccount

logger = logging.getLogger("AmazonAuth")

APP_NAME = "com.iconology.comix"
APP_VERSION = "1221328936"
DEVICE_NAME = "walleye/google/Pixel 2"
DEVICE_TYPE = "A2A33MVZVPQKHY"
MANUFACTURER = "Google"
OS_VERSION = "google/walleye/walleye:8.1.0/OPM1.171019.021/4565141:user/release-keys"
PFM = "A1F83G8C2ARO7P"
SW_VERSION = "1221328936"


class AuthFailed(Exception):
    pass


class AmazonAuth:
    def __init__(self, email: str, password: str, domain: str = "com"):
        self._email: str = email
        self._password: str = password
        self._domain: str = domain
        self._account: Optional[AmazonAccount] = None

        USER_PATH.mkdir(exist_ok=True, parents=True)
        email_hash = b64encode(self._email.encode()).decode()
        self._token_path = USER_PATH / f"token_{email_hash}.{self._domain}.json"
        device_id_path = USER_PATH / "comix_device_id"
        if device_id_path.exists() and device_id_path.is_file():
            read_device_id = device_id_path.read_text().strip()
            if len(read_device_id) != 16:
                # Regenerate device ID
                device_id = token_hex(16)
                device_id_path.write_text(device_id, "utf-8")
            else:
                device_id = read_device_id
        else:
            device_id = token_hex(16)
            device_id_path.write_text(device_id, "utf-8")
        self._device_id: str = device_id

        self._PID = hashlib.sha256(self._device_id.encode()).hexdigest()[23:31].upper()

        self._ip_address_frc: str = None

    @property
    def ip_address(self):
        if self._ip_address_frc is None:
            self._ip_address_frc = requests.get("https://api.ipify.org").text
        return self._ip_address_frc

    def _pkcs7_pad(self, data: Union[str, bytes]) -> bytes:
        padsize = 16 - len(data) % 16
        return data + bytes([padsize]) * padsize

    def _pkcs7_unpad(self, data: bytes) -> bytes:
        offset = data[-1]
        return data[:-offset]

    def _get_auth_headers(self):
        return {
            "Accept-Charset": "utf-8",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Pixel 2 Build/OPM1.171019.021)",
            "x-amzn-identity-auth-domain": f"api.amazon.{self._domain}",
            "x-amzn-requestid": str(uuid4()).replace("-", ""),
        }

    def _get_api_headers(self):
        return {
            "accept": "*/*",
            "accept-encoding": "gzip",
            "accept-language": "en-US",
            "currenttransportmethod": "WiFi",
            "is_archived_items": "1",
            "software_rev": SW_VERSION,
            "user-agent": "okhttp/3.12.1",
            "x-adp-app-id": APP_NAME,
            "x-adp-app-sw": SW_VERSION,
            "x-adp-attemptcount": "1",
            "x-adp-cor": "US",
            "x-adp-country": "US",
            "x-adp-lto": "0",
            "x-adp-pfm": PFM,
            "x-adp-reason": "ArchivedItems",
            "x-adp-sw": SW_VERSION,
            "x-adp-transport": "WiFi",
            "x-amzn-accept-type": "application/x.amzn.digital.deliverymanifest@1.0",
        }

    def _generate_frc(self):
        cookies = json.dumps(
            {
                "ApplicationName": APP_NAME,
                "ApplicationVersion": APP_VERSION,
                "DeviceLanguage": "en",
                "DeviceName": DEVICE_NAME,
                "DeviceOSVersion": OS_VERSION,
                "IpAddress": self.ip_address,
                "ScreenHeightPixels": "1920",
                "ScreenWidthPixels": "1280",
                "TimeZone": "00:00",
            }
        )

        compressed = gzip.compress(cookies.encode())

        key = PBKDF2(self._device_id, b"AES/CBC/PKCS7Padding")
        iv = token_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(self._pkcs7_pad(compressed))

        hmac_ = hmac.new(PBKDF2(self._device_id, b"HmacSHA256"), iv + ciphertext, hashlib.sha256).digest()

        return base64.b64encode(b"\0" + hmac_[:8] + iv + ciphertext).decode()

    @property
    def hash_pass(self):
        if not self._password:
            return "[???]"
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
                "user_id_password": {"password": self._password, "user_id": self._email},
            },
            "registration_data": {
                "domain": "DeviceLegacy",
                "device_type": DEVICE_TYPE,
                "device_serial": self._device_id,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_model": DEVICE_NAME,
                "os_version": OS_VERSION,
                "software_version": SW_VERSION,
            },
            "requested_token_type": ["bearer", "mac_dms", "store_authentication_cookie", "website_cookies"],
            "cookies": {"domain": f"amazon.{self._domain}", "website_cookies": []},
            "user_context_map": {"frc": self._generate_frc()},
            "device_metadata": {
                "device_os_family": "android",
                "device_type": DEVICE_TYPE,
                "device_serial": self._device_id,
                "manufacturer": MANUFACTURER,
                "model": DEVICE_NAME,
                "os_version": "30",
                "android_id": "e97690019ccaab2b",
                "product": DEVICE_NAME,
            },
            "requested_extensions": ["device_info", "customer_info"],
        }
        logger.info(f"Authenticating with {self._email} and {self.hash_pass}")

        response_json = requests.post(
            f"https://api.amazon.{self._domain}/auth/register", headers=self._get_auth_headers(), json=body
        ).json()
        try:
            amz_account = AmazonAccount.from_data(response_json, self._email, self._password, self._domain)
            logger.info(f"Authenticated to {amz_account.name} (Device: {amz_account.device.name})")
            self._account = amz_account
            self.register_device()
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
            "https://api.amazon.com/auth/token", headers=self._get_auth_headers(), json=body
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
                try:
                    self._account = AmazonAccount.from_dict(json.load(f))
                except (ValueError, TypeError, KeyError):
                    logger.warning("Failed to load token from file, re-authenticating")
                    self.authenticate()
                    with token_path.open("w") as f:
                        logger.info("Saving token to file")
                        json.dump(self._account.to_dict(), f)

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

    def signed_request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        body: Any = None,
        asin: Optional[str] = None,
        request_id: Optional[str] = None,
        request_type: Optional[str] = None,
    ) -> requests.PreparedRequest:
        """
        Modified from https://github.com/athrowaway2021/comix/blob/main/amazon_api.py
        Which is modified from https://github.com/mkb79/Audible/blob/master/src/audible/auth.py
        """

        if not self._account:
            self.authenticate()

        unix_time = int(time.time())
        if not request_id:
            request_id = str(uuid4()).replace("-", "")
        else:
            request_id += str(unix_time) + "420"

        if not body:
            body = ""

        current_date = datetime.utcnow().isoformat("T")[:-7] + "Z"
        u = urlparse(url)
        path = f"{u.path}"
        if u.query != "":
            path += f"{u.params}?{u.query}"
        data = f"{method}\n{path}\n{current_date}\n{body}\n{self._account.adp_token}"

        key = RSA.import_key(b64decode(self._account.private_key))
        signed_encoded = b64encode(pkcs1_15.new(key).sign(SHA256.new(data.encode())))
        signature = f"{signed_encoded.decode()}:{current_date}"

        if not headers:
            headers = self._get_api_headers()
        if asin:
            headers["x-adp-correlationid"] = f"{asin}-{unix_time}420.kindle.ebook"
        if request_type == "DRM_VOUCHER":
            headers["accept"] = "application/x-com.amazon.drm.Voucher@1.0"

        headers.update(
            {
                "x-adp-token": self._account.adp_token,
                "x-adp-alg": "SHA256WithRSA:1.0",
                "x-adp-signature": signature,
                "x-amzn-requestid": request_id,
            }
        )

        return requests.Request(method, url, headers, data=body).prepare()

    def register_device(self):
        if not self._account:
            raise ValueError("No account set")

        logger.info(f"Registering device {self._account.device.name}")

        url = "https://firs-ta-g7g.amazon.com/FirsProxy/registerAssociatedDevice"
        headers = {
            "Content-Type": "text/xml",
            "Expect": "",
        }
        # secret = "AAAA"
        body = f'<?xml version="1.0" encoding="UTF-8"?><request><parameters><deviceType>{DEVICE_TYPE}</deviceType><deviceSerialNumber>{self._device_id}</deviceSerialNumber><pid>{self._PID}</pid><deregisterExisting>false</deregisterExisting><softwareVersion>{SW_VERSION}</softwareVersion><softwareComponentId>{APP_NAME}</softwareComponentId><authToken>{self._account.access_token}</authToken><authTokenType>ACCESS_TOKEN</authTokenType></parameters></request>'  # noqa

        request = self.signed_request("POST", url, headers, body)
        resp = requests.Session().send(request)

        if resp.status_code == 200:
            parsed_response = xmltodict.parse(resp.text)
            logger.info(f"Registered device {self._account.device.name}")
            self._account.private_key = parsed_response["response"]["device_private_key"]
            self._account.adp_token = parsed_response["response"]["adp_token"]

        with self._token_path.open("w") as f:
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
    amz = AmazonAuth(args.email, args.password, args.domain)
    amz.login()
    print(amz.account)
