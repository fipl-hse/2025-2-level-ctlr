"""
Pipeline for CONLL-U formatting.
"""

import pathlib
import re
from typing import Dict

from core_utils.article.article import Article
from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH


class EmptyDirectoryError(Exception):
    """Raised when dataset directory is empty."""


class InconsistentDatasetError(Exception):
    """Raised when dataset has structural inconsistencies."""


class EmptyFileError(Exception):
    """Raised when a file is empty (stub for mark 4)."""
    pass


class CorpusManager:
    """Work with articles and store them."""

    def __init__(self, path_to_raw_txt_data: pathlib.Path) -> None:
        self._storage: Dict[int, Article] = {}
        self._path = path_to_raw_txt_data
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """Validate folder with assets."""
        if not self._path.exists():
            raise FileNotFoundError(f"Path does not exist: {self._path}")
        if not self._path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._path}")

        files = list(self._path.glob("*.txt"))
        if not files:
            raise EmptyDirectoryError(f"Directory is empty: {self._path}")

        # Проверяем только raw файлы, мета-файлы не требуем для mark 4
        raw_files = []
        for file in self._path.glob("*_raw.txt"):
            try:
                idx = int(file.stem.split("_")[0])
                raw_files.append(idx)
            except ValueError:
                continue

        if not raw_files:
            raise InconsistentDatasetError("No raw files found")

        # Проверяем, что файлы не пусты
        for file in self._path.glob("*_raw.txt"):
            if file.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file is empty: {file}")

        # Проверяем, что номера идут подряд без пропусков
        ids = sorted(raw_files)
        expected = list(range(1, len(ids) + 1))
        if ids != expected:
            raise InconsistentDatasetError(f"Article IDs not consecutive: {ids}")

    def _scan_dataset(self) -> None:
        """Register each dataset entry."""
        for file in self._path.glob("*_raw.txt"):
            article_id = int(file.stem.split("_")[0])
            self._storage[article_id] = Article(url=None, article_id=article_id)

    def get_articles(self) -> Dict[int, Article]:
        """Get storage dict."""
        return self._storage


class TextProcessingPipeline:
    """Preprocess text: lowercase, remove punctuation (mark 4)."""

    def __init__(self, corpus_manager: CorpusManager) -> None:
        self._corpus = corpus_manager

    def run(self) -> None:
        """Perform cleaning and save cleaned text."""
        for article_id, article in self._corpus.get_articles().items():
            from_raw(article)
            raw_text = article.text
            if not raw_text:
                continue

            cleaned_text = re.sub(r'[^\w\s]', '', raw_text)
            cleaned_text = cleaned_text.lower()

            article.set_cleaned(cleaned_text)
            to_cleaned(article, ASSETS_PATH)


# Stub classes for higher marks (required for imports in tests)
class UDPipeAnalyzer:
    """Stub for UDPipeAnalyzer (not used in mark 4)."""
    def __init__(self) -> None:
        pass

    def analyze(self, texts):
        return [""] * len(texts)

    def to_conllu(self, article):
        pass

    def from_conllu(self, article):
        pass


class PatternSearchPipeline:
    """Stub for PatternSearchPipeline (not used in mark 4)."""
    def __init__(self, corpus_manager, analyzer, pos):
        pass

    def run(self):
        pass


def main() -> None:
    """Entrypoint for pipeline module."""
    corpus_manager = CorpusManager(ASSETS_PATH)
    pipeline = TextProcessingPipeline(corpus_manager)
    pipeline.run()


if __name__ == "__main__":
    main()
    