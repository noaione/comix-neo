from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import click
from pyzipper import AESZipFile

from .amz import AmazonAuth, AuthFailed
from .client import CmxClient
from .constants import DEVICE_ID, USER_PATH, __version__
from .key import ComixKey
from .logme import setup_logger
from .progressbar import ProgressBar

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], ignore_unknown_options=True)
CURRENT_DIR = Path(__file__).absolute().parent
logger = setup_logger(CURRENT_DIR)


def _get_user_or_fallback(username: Optional[str]) -> str:
    active_account: str = None
    if not username:
        for account in USER_PATH.glob("*.json"):
            if account.name.startswith("token_"):
                with account.open() as f:
                    account_test = json.load(f)
                    acc_email = account_test["email"]
                    acc_domain = account_test["domain"]
                    amz_test = AmazonAuth(acc_email, None, DEVICE_ID, acc_domain)
                    try:
                        amz_test.login()
                        active_account = acc_email
                        break
                    except AuthFailed:
                        continue
    else:
        active_account = username
    return active_account


def empty_folders(folders: Path):
    if not folders.exists() or not folders.is_dir():
        return
    for folder in folders.iterdir():
        if folders.is_dir():
            empty_folders(folder)
        else:
            folder.unlink(missing_ok=True)
    folders.rmdir()


def existing_dl(path: Path):
    if path.exists():
        return True
    fname = path.name
    cbz_file = path.parent / f"{fname}.cbz"
    return cbz_file.exists()


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--version", "-V", is_flag=True, help="Show current version")
def main(version=False):
    """
    A backup tools for your Comixology library.
    """
    if version:
        print("comix-neo v{} - Created by noaione".format(__version__))
        exit(0)


@main.command("dl", short_help="Download comic by ID")
@click.argument("comic_id", metavar="<comic id>")
@click.option(
    "--username",
    "-U",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--password",
    "-P",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--domain",
    "-d",
    required=False,
    default="com",
    help="The domain tld of your account, default is com.",
)
@click.option("--cbz", is_flag=True, help="Merge as CBZ after finish downloading")
def comix_neo_download(
    comic_id: str, username: Optional[str], password: Optional[str], domain: str, cbz: bool
):
    """
    Download comic by ID.
    """
    if not comic_id.isdigit():
        logger.error("Invalid comic id")
        exit(1)
    active_account: str = _get_user_or_fallback(username)

    neo_session = CmxClient(active_account, password, domain)
    comic = neo_session.get_comic(int(comic_id))
    if comic is None:
        logger.error(f"Comic not found in your account {active_account}")
        exit(1)

    comix_out = CURRENT_DIR / "comix_dl" / comic.release_name
    if existing_dl(comix_out):
        logger.info(f"{comic.release_name} already downloaded, skipping!")
        exit(0)
    comix_out.mkdir(parents=True, exist_ok=True)
    VALID_IMAGES = [".jpg", ".jpeg", "jpg", "jpeg", ".png", "png"]

    logger.info(f"Downloading: {comic.release_name}")
    for (idx, image), _ in zip(enumerate(comic.images), ProgressBar(len(comic.images)).make()):
        image_key = ComixKey.calculate_key(
            image.digest, int(comic_id), comic.version, comic.publisher_id, idx
        )
        response = neo_session.session.get(image.url)
        with AESZipFile(BytesIO(response.content)) as zf:
            zf.extractall(comix_out, pwd=image_key)

    for idx, file in enumerate(comix_out.rglob("*")):
        extension = os.path.splitext(file)[1]
        if extension in VALID_IMAGES:
            os.rename(file, comix_out / f"{comic.release_name} - p{idx:03d}{extension}")

    if cbz:
        logger.info(f"Merging {comic.title}")
        with ZipFile(comix_out.parent / f"{comic.release_name}.cbz", "w") as zipf:
            for filepath in comix_out.rglob("*"):
                extension = os.path.splitext(file)[1]
                if extension in VALID_IMAGES:
                    zipf.write(filepath, filepath.name)

        empty_folders(comix_out)

    neo_session.close()


@main.command("list", short_help="List purchased comics on your account!")
@click.option(
    "--username",
    "-U",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--password",
    "-P",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--domain",
    "-d",
    required=False,
    default="com",
    help="The domain tld of your account, default is com.",
)
def comix_neo_list(username: Optional[str], password: Optional[str], domain: str):
    active_account: str = _get_user_or_fallback(username)
    if active_account is None:
        logger.error("No active account found, please login first")
        exit(1)

    neo_session = CmxClient(active_account, password, domain)
    comics_list = neo_session.get_comics()
    if not comics_list:
        logger.warning("No comics found in your account")
        exit(0)

    logger.info("Found {} comics in your account".format(len(comics_list)))
    comics_list.sort(key=lambda x: x.release_name)
    print("[Position] Comic ID - Title")
    for idx, comic in enumerate(comics_list, 1):
        print(f"[{idx}] {comic.id} - {comic.release_name}")
    neo_session.close()


@main.command("dlall", short_help="Download all purchased comics to current directory")
@click.option(
    "--username",
    "-U",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--password",
    "-P",
    required=False,
    default=None,
    help="Use username/password to download, you can ignore this if you already authenticated before.",
)
@click.option(
    "--domain",
    "-d",
    required=False,
    default="com",
    help="The domain tld of your account, default is com.",
)
@click.option("--cbz", is_flag=True, help="Merge as CBZ after finish downloading")
def comix_neo_dlall(username: Optional[str], password: Optional[str], domain: str, cbz: bool):
    active_account: str = _get_user_or_fallback(username)
    if active_account is None:
        logger.error("No active account found, please login first")
        exit(1)

    neo_session = CmxClient(active_account, password, domain)
    comics_list = neo_session.get_comics()
    if not comics_list:
        logger.warning("No comics found in your account")
        exit(0)
    VALID_IMAGES = [".jpg", ".jpeg", "jpg", "jpeg", ".png", "png"]

    logger.info("Found {} comics in your account".format(len(comics_list)))
    comics_list.sort(key=lambda x: x.release_name)
    for comic_raw in comics_list:
        logger.info(f"Fetching: {comic_raw.release_name}")
        comic = neo_session.get_comic(int(comic_raw.id))
        if comic is None:
            logger.error(f"Comic not found in your account {active_account}")
            continue

        comix_out = CURRENT_DIR / "comix_dl" / comic.release_name
        if existing_dl(comix_out):
            logger.info(f"{comic.release_name} already downloaded, skipping!")
            continue
        comix_out.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading: {comic.release_name}")
        for (idx, image), _ in zip(enumerate(comic.images), ProgressBar(len(comic.images)).make()):
            image_key = ComixKey.calculate_key(
                image.digest, int(comic_raw.id), comic.version, comic.publisher_id, idx
            )
            response = neo_session.session.get(image.url)
            with AESZipFile(BytesIO(response.content)) as zf:
                zf.extractall(comix_out, pwd=image_key)

        for idx, file in enumerate(comix_out.rglob("*")):
            extension = os.path.splitext(file)[1]
            if extension in VALID_IMAGES:
                os.rename(file, comix_out / f"{comic.release_name} - p{idx:03d}{extension}")

        if cbz:
            logger.info(f"Merging {comic.title}")
            with ZipFile(comix_out.parent / f"{comic.release_name}.cbz", "w") as zipf:
                for filepath in comix_out.rglob("*"):
                    extension = os.path.splitext(file)[1]
                    if extension in VALID_IMAGES:
                        zipf.write(filepath, filepath.name)

            empty_folders(comix_out)
    logger.info("Finished downloading all comics")
    neo_session.close()


if __name__ == "__main__":
    main()
