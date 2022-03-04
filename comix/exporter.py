from __future__ import annotations
import os

from pathlib import Path
from io import BytesIO
from typing import TYPE_CHECKING, List, Optional, Union

from pyzipper import AESZipFile
from zipfile import ZipFile
from os.path import basename, splitext

from .models import ComicData

if TYPE_CHECKING:
    from zipfile import ZipInfo

__all__ = ("MangaExporter", "CBZMangaExporter")
VALID_IMAGES = [".jpg", ".jpeg", "jpg", "jpeg", ".png", "png"]


class MangaExporter:
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
    def __init__(self, comic: ComicData, output_directory: Path):
        super().__init__(comic, output_directory)

        self._target_cbz: Optional[ZipFile] = None

    def is_existing(self):
        parent_test = super().is_existing()
        parent_dir = self._out_dir.parent
        target_cbz = parent_dir / f"{self._comic.release_name}.cbz"
        return target_cbz.exists() or parent_test

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
