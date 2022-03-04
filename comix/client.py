from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import requests
from google.protobuf.message import DecodeError

import comix.comix_pb2 as comix_pb2

from .amz import AmazonAuth
from .constants import API_DOWNLOAD_URL, API_HEADERS, API_ISSUE_URL, API_LIST_URL
from .models import ComicData, ComicImage, ComicIssue

logger = logging.getLogger("ComixClient")
CURRENT_DIR = Path.cwd().absolute()
DOWNLOAD_DIR = CURRENT_DIR / "comix_dl"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


class CmxClient:
    def __init__(self, email: str, password: str, domain: str = "com"):
        self._session = requests.session()
        self._session.headers.update(API_HEADERS)

        self.amz = AmazonAuth(email, password, domain)
        self.amz.login()

    @property
    def session(self):
        return self._session

    def close(self):
        self._session.close()

    def _get_comic_issue_info(self, issue_ids: List[int]):
        base_issue = {"amz_access_token": self.amz.token, "account_type": "amazon"}
        for idx, issue in enumerate(issue_ids):
            base_issue[f"ids[{idx}]"] = issue

        response = self._session.post(API_ISSUE_URL, data=base_issue)

        issue_proto = comix_pb2.IssueResponse()
        issue_proto.ParseFromString(response.content)

        issue_infos: List[ComicIssue] = []
        for issue in issue_proto.issues.issues:
            issue_infos.append(ComicIssue.from_proto(issue))
        return issue_infos

    def get_comic(self, item_id: int) -> Optional[ComicData]:
        logger.info(f"Trying to get comic {item_id}")
        post_data = {
            "amz_access_token": self.amz.token,
            "account_type": "amazon",
            "comic_format": "IPAD_PROVISIONAL_HD",
            "item_id": item_id,
        }
        resp = self._session.post(API_DOWNLOAD_URL, data=post_data)

        comic_proto = comix_pb2.ComicResponse()
        try:
            comic_proto.ParseFromString(resp.content)
        except DecodeError:
            logger.error("Unable to parse protobuf response, dumping response...")
            dump_dir = DOWNLOAD_DIR / f"{item_id}_comic_proto.bin"
            with dump_dir.open("wb") as f:
                f.write(resp.content)
            return None

        if comic_proto.error.errormsg != "":
            logger.error(f"Error: {comic_proto.error.errormsg}")
            return None

        if comic_proto.comic.comic_id == "" or len(comic_proto.comic.book.pages) == 0:
            logger.error("Could not acquire the content info")
            return None

        receive_issue = self._get_comic_issue_info([item_id])
        final_issue = None
        if not receive_issue:
            logger.warning("Unable to obtain issue information, using temporary stop-gap")
        else:
            final_issue = receive_issue[0]

        publisher_id = comic_proto.comic.issue.publisher.publisher_id
        if publisher_id == "274" or publisher_id == "281":
            publisher_id = "6670"

        image_list: List[ComicImage] = []
        for page in comic_proto.comic.book.pages:
            for image in page.pageinfo.images:
                if image.type != image.Type.FULL:
                    continue
                image_list.append(ComicImage(image.uri, image.digest.data))

        return ComicData(
            comic_proto.comic.comic_id,
            comic_proto.comic.issue.title,
            publisher_id,
            comic_proto.comic.version,
            final_issue,
            image_list,
        )

    def get_comics(self):
        list_form = {"amz_access_token": self.amz.token, "account_type": "amazon", "sinceDate": "0"}
        logger.info("Getting list of comics from your account")
        response = self._session.post(API_LIST_URL, data=list_form)

        list_proto = comix_pb2.IssueResponse2()
        list_proto.ParseFromString(response.content)
        if len(list_proto.issues.issues) == 0:
            return []

        fetch_ids = []
        for issue in list_proto.issues.issues:
            issue_id = issue.id
            if not isinstance(issue_id, int):
                issue_id = int(issue_id)
            fetch_ids.append(issue_id)

        issue_infos = self._get_comic_issue_info(fetch_ids)
        return issue_infos
