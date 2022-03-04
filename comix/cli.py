from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click

from .amz import AmazonAuth, AuthFailed
from .client import CmxClient
from .constants import USER_PATH, __version__
from .exporter import CBZMangaExporter, MangaExporter
from .key import ComixKey
from .logme import setup_logger
from .progressbar import ProgressBar

if TYPE_CHECKING:
    from requests import Session

    from .models import ComicData

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
CURRENT_DIR = Path.cwd().absolute()
logger = setup_logger(CURRENT_DIR)


def _get_user_or_fallback(username: Optional[str], password: Optional[str]) -> str:
    active_account: str = None
    if not username:
        for account in USER_PATH.glob("*.json"):
            if account.name.startswith("token_"):
                with account.open() as f:
                    account_test = json.load(f)
                    acc_email = account_test["email"]
                    acc_domain = account_test["domain"]
                    amz_test = AmazonAuth(acc_email, password, acc_domain)
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


def cmx_download_helper(comic: ComicData, output_dir: Path, session: Session, as_cbz: bool = False) -> None:
    if as_cbz:  # Export as .cbz
        cmx_export = CBZMangaExporter(comic, output_dir)
    else:
        cmx_export = MangaExporter(comic, output_dir)

    if cmx_export.is_existing():
        logger.info(f"{comic.release_name} already downloaded!")
        cmx_export.close()
        return

    logger.info(f"Downloading: {comic.release_name}")
    logger.info(f"Download path: {output_dir}")

    for (idx, image), _ in zip(enumerate(comic.images), ProgressBar(len(comic.images)).make()):
        image_key = ComixKey.calculate_key(image.digest, comic.int_id, comic.version, comic.publisher_id, idx)
        response = session.get(image.url)
        cmx_export.add_image(response.content, image_key)

    logger.info(f"Downloaded {comic.release_name}, cleaning up!")
    cmx_export.close()


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "--version", "-V")
@click.pass_context
def main(ctx: click.Context):
    """
    A backup tools for your Comixology library.
    """
    pass


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
    active_account: str = _get_user_or_fallback(username, password)

    neo_session = CmxClient(active_account, password, domain)
    comic = neo_session.get_comic(int(comic_id))
    if comic is None:
        logger.error(f"Comic not found in your account {active_account}")
        exit(1)

    comix_out = CURRENT_DIR / "comix_dl" / comic.release_name
    cmx_download_helper(comic, comix_out, neo_session.session, cbz)
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
    """
    List all available comics on your account.
    """
    active_account: str = _get_user_or_fallback(username, password)
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
    """
    Download all comics available on your account.
    """
    active_account: str = _get_user_or_fallback(username, password)
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
    for comic_raw in comics_list:
        logger.info(f"Fetching: {comic_raw.release_name}")
        comic = neo_session.get_comic(int(comic_raw.id))
        if comic is None:
            logger.error(f"Comic not found in your account {active_account}")
            continue

        comix_out = CURRENT_DIR / "comix_dl" / comic.release_name
        cmx_download_helper(comic, comix_out, neo_session.session, cbz)
    logger.info("Finished downloading all comics")
    neo_session.close()


if __name__ == "__main__":
    main()
