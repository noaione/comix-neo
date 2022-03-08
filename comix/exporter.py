from __future__ import annotations

import os
from enum import Enum
from io import BytesIO
from os.path import basename, splitext
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Type, Union
from zipfile import ZipFile

from pyzipper import AESZipFile

from .models import ComicData

if TYPE_CHECKING:
    from zipfile import ZipInfo

__all__ = (
    "MangaExporter",
    "CBZMangaExporter",
    "EPUBMangaExporter",
    "ExporterType",
    "exporter_factory",
)
VALID_IMAGES = [".jpg", ".jpeg", "jpg", "jpeg", ".png", "png"]
TEMPLATES_DIR = Path(__file__).absolute().parent / "templates"


class ExporterType(Enum):
    raw = 0
    cbz = 1
    epub = 2

    @classmethod
    def from_choice(cls: Type[ExporterType], ext: str):
        ext = ext.lower()
        if ext == "cbz":
            return cls.cbz
        elif ext == "epub":
            return cls.epub
        else:
            return cls.raw


class MangaExporter:
    TYPE = ExporterType.raw

    def __init__(self, comic: ComicData, output_directory: Path):
        self._comic = comic
        self._out_dir = output_directory
        self._image_count = 0

        self._out_dir.mkdir(parents=True, exist_ok=True)

    def is_existing(self):
        if self._out_dir.exists():
            all_valid_images = list(
                filter(lambda file: splitext(file.name)[1] in VALID_IMAGES, self._out_dir.rglob("*"))
            )
            if len(all_valid_images) == len(self._comic.images):
                return True
        return False

    def add_image(self, zip_bita: Union[bytes, BytesIO], image_key: bytes) -> List[str]:
        if not isinstance(zip_bita, BytesIO):
            zip_bita = BytesIO(zip_bita)
        zip_bita.seek(0)

        temporary_extract: List[str] = []
        with AESZipFile(zip_bita) as zf:
            zf.extractall(self._out_dir, pwd=image_key)
            zf_files: List[ZipInfo] = zf.filelist
            for zfile in zf_files:
                if zfile.is_dir():
                    continue
                fext = splitext(basename(zfile.filename))[1]
                if fext in VALID_IMAGES:
                    temporary_extract.append(zfile.filename)

        actual_filenames: List[str] = []
        for img in temporary_extract:
            full_path = self._out_dir / img
            fext = splitext(img)[1]
            target_name = self._out_dir / f"{self._comic.release_name} - p{self._image_count:03d}{fext}"
            full_path.rename(target_name)
            self._image_count += 1
            actual_filenames.append(target_name.name)

        zip_bita.close()

        return actual_filenames

    def close(self):
        pass


def self_destruct_folder(folder: Path):
    if not folder.exists() or not folder.is_dir():
        return
    for folder in folder.iterdir():
        if folder.is_dir():
            self_destruct_folder(folder)
        else:
            folder.unlink(missing_ok=True)
    folder.rmdir()


class CBZMangaExporter(MangaExporter):
    TYPE = ExporterType.cbz

    def __init__(self, comic: ComicData, output_directory: Path):
        super().__init__(comic, output_directory)

        self._target_cbz: Optional[ZipFile] = None

    def is_existing(self):
        parent_dir = self._out_dir.parent
        target_cbz = parent_dir / f"{self._comic.release_name}.cbz"
        if target_cbz.exists():
            return True
        return super().is_existing()

    def add_image(self, zip_bita: Union[bytes, BytesIO], image_key: bytes) -> List[str]:
        if self._target_cbz is None:
            parent_dir = self._out_dir.parent
            self._target_cbz = ZipFile(parent_dir / f"{self._comic.release_name}.cbz", "w")
        images_list = super().add_image(zip_bita, image_key)

        for image in images_list:
            img_path = self._out_dir / image
            inject_bytes = img_path.read_bytes()
            self._target_cbz.writestr(image, inject_bytes)
            os.remove(str(img_path))
        return images_list

    def close(self):
        if self._target_cbz is not None:
            self._target_cbz.close()
        self_destruct_folder(self._out_dir)


class EPUBMangaExporter(MangaExporter):
    TYPE = ExporterType.epub

    def __init__(self, comic: ComicData, output_directory: Path):
        super().__init__(comic, output_directory)

        self._target_epub: Optional[ZipFile] = None
        self._meta_injected: bool = False

        self._page_counter = 1

    def is_existing(self):
        parent_dir = self._out_dir.parent
        target_cbz = parent_dir / f"{self._comic.release_name}.epub"
        if target_cbz.exists():
            return True
        return super().is_existing()

    def _initialize_meta(self):
        if self._meta_injected:
            return
        if self._target_epub is None:
            parent_dir = self._out_dir.parent
            self._target_epub = ZipFile(parent_dir / f"{self._comic.release_name}.cbz", "w")
        styles = TEMPLATES_DIR / "epub_styles.css"
        styles_bytes = styles.read_bytes()
        self._target_epub.writestr("epub_styles.css", styles_bytes)
        container = TEMPLATES_DIR / "epub_container.xml"
        container_bytes = container.read_bytes()
        self._target_epub.writestr(Path("META-INF/container.xml"), container_bytes)
        self._meta_injected = True

    def _inject_meta(self, number: int, filename: str):
        page_title = f"{self._comic.release_name} - Page #{number}"
        if number == 1:
            page_title = f"{self._comic.release_name} - Cover Page"

        page_xhtml = TEMPLATES_DIR / "epub_page.xhtml"
        page_xhtml_text = page_xhtml.read_text()
        page_xhtml_text = (
            page_xhtml_text.replace(
                r"{{title}}",
                page_title,
            )
            .replace(r"{{number}}", str(number))
            .replace(
                r"{{filename}}",
                filename,
            )
        )
        self._target_epub.writestr(f"page_{number:03d}.xhtml", page_xhtml_text.encode("utf-8"))

    def add_image(self, zip_bita: Union[bytes, BytesIO], image_key: bytes) -> List[str]:
        if self._target_epub is None:
            parent_dir = self._out_dir.parent
            self._target_epub = ZipFile(parent_dir / f"{self._comic.release_name}.cbz", "w")
        images_list = super().add_image(zip_bita, image_key)

        for image in images_list:
            img_path = self._out_dir / image
            inject_bytes = img_path.read_bytes()
            self._target_epub.writestr(image, inject_bytes)
            self._inject_meta(self._page_counter, image)
            os.remove(str(img_path))
            self._page_counter += 1

        return images_list


def exporter_factory(
    comic: ComicData, output_directory: Path, mode: Union[str, ExporterType] = ExporterType.raw
):
    if isinstance(mode, str):
        mode = ExporterType.from_choice(mode)
    if mode == ExporterType.raw:
        return MangaExporter(comic, output_directory)
    elif mode == ExporterType.cbz:
        return CBZMangaExporter(comic, output_directory)
    elif mode == ExporterType.epub:
        return EPUBMangaExporter(comic, output_directory)
    raise ValueError(f"Unknown mode: {mode}")
