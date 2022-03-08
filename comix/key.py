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

from base64 import b64encode
from binascii import hexlify
from hashlib import md5
from typing import Union


class ComixKey:
    @staticmethod
    def hash(a: Union[str, bytes]) -> str:
        return hexlify(md5(a).digest()).decode("utf-8").lower()

    @staticmethod
    def reverse(a: str):
        i = 0
        for idx in range(len(a) - 1, i, -1):
            b = a[idx]
            a[idx] = a[i]
            a[i] = b
            i += 1
        return a

    @staticmethod
    def expand(a: str):
        len_mul = len(a) * 2
        len_base = len(a)
        b = bytearray(len_mul)
        b[:len_base] = a[:len_base]
        for j in range(len(a), len_mul, 1):
            len_base -= 1
            b[j] = b[len_base]
        return b

    @staticmethod
    def calculate_key(digest: str, item_id: int, version: str, publisher_id: str, index: int):
        i = int(publisher_id) + 1

        if item_id % 2 == 0:
            i += 1

        data_to_hash = (
            str(index % 10).encode()
            + version[::-1].encode()
            + str(item_id % 10).encode()
            + str(index * i).encode()
            + digest
            + version.encode()
            + str(int(publisher_id) % 10).encode()
        )

        e = ComixKey.expand(data_to_hash)

        b = index % 256
        for j in range(0, len(e), 1):
            e[j] = e[j] ^ b
        a = ComixKey.hash(e)
        e = ComixKey.reverse(e)

        return b64encode((a + ComixKey.hash(e)).encode())[:50]
