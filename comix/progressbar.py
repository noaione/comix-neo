# flake8: noqa

from typing import Generator

try:
    import tqdm  # type: ignore noqa

    with_tqdm = True
except ImportError:
    with_tqdm = False


class ProgressBar:
    def __init__(self, maximum_page: int):
        self._current = 1
        self._maximum = maximum_page

    def make(self) -> Generator[int, None, None]:
        if with_tqdm:
            for page in tqdm.tqdm(list(range(0, self._maximum)), desc="Downloading", unit="page", ascii=True):
                yield page
        else:
            for page in list(range(0, self._maximum)):
                print(f"Downloading: {page + 1}/{self._maximum}\r", end="")
                yield page
        print()
