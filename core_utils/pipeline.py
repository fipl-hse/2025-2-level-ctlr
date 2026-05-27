"""
Interface definitions for text processing pipelines.
"""

# pylint: disable=too-few-public-methods, unused-argument
import pathlib
import re

from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import PipelineProtocol



from dataclasses import dataclass
from typing import Protocol

from quality_control.console_logging import get_child_logger

from core_utils.article.article import Article

logger = get_child_logger(__file__)
try:
    from spacy.language import Language
    from spacy.tokens import Doc
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    logger.warning("No libraries installed. Failed to import.")

class EmptyDirectoryError(Exception):
    """Raised when the directory is empty."""


class InconsistentDatasetError(Exception):
    """Raised when the dataset is inconsistent."""

class CorpusManager:
    """
    Work with articles and store them.

    Args:
        path_to_raw_txt_data (pathlib.Path):
            Path to raw txt data
    """

    def __init__(self, path_to_raw_txt_data: pathlib.Path):
        self.path_to_raw_txt_data = path_to_raw_txt_data
        self._storage: dict[int, Article] = {}

        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError(
                f"Path does not exist: {self.path_to_raw_txt_data}"
            )

        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError(
                "Path does not lead to directory"
            )

        raw_ids = []

        for file_path in self.path_to_raw_txt_data.iterdir():

            if file_path.is_dir():
                continue

            name = file_path.stem
            suffix = file_path.suffix

            parts = name.split("_")

            if len(parts) != 2:
                continue

            if not parts[0].isdigit():
                continue

            file_id = int(parts[0])

            if (
                parts[1] == "raw"
                and suffix == ".txt"
            ):

                if file_path.stat().st_size == 0:
                    raise InconsistentDatasetError(
                        f"Empty raw file: {file_path.name}"
                    )

                raw_ids.append(file_id)

        if not raw_ids:
            raise EmptyDirectoryError(
                "No raw files found"
            )

        expected_ids = list(
            range(1, len(raw_ids) + 1)
        )

        if sorted(raw_ids) != expected_ids:
            raise InconsistentDatasetError(
                "Raw file IDs contain gaps"
            )
        
    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            article_id = int(file_path.stem.split("_")[0])
            article = Article(url=None, article_id=article_id)
            from_raw(file_path, article)
            self._storage[article_id] = article

    def get_articles(self) -> dict:
        """
        Returns:
            dict: Storage params
        """
        return self._storage

class TextProcessingPipeline(PipelineProtocol):
    """
    Process texts.
    """

    def __init__(
            self,
            corpus_manager: CorpusManager
    ):
        self._corpus = corpus_manager
    
    def run(self) -> None:
        """
        Perform basic preprocessing and write processed text to files.
        """
        for article in self._corpus.get_articles().values():

            cleaned_text = article.text.lower()

            cleaned_text = re.sub(
            r"[^\w\s]",
            "",
                cleaned_text
            )

            article.text = cleaned_text

            to_cleaned(article)
    
class PipelineProtocol(Protocol):
    """
    Interface definition for pipeline.
    """

    def run(self) -> None:
        """
        Key API method.
        """


class LibraryWrapper(Protocol):
    """
    Interface definition for text analyzers.
    """

    _analyzer: Language

    def _bootstrap(self) -> Language:
        """
        Bootstrap analyzer with required models and settings.

        Returns:
            Language: Instance of analyzer.
        """

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Analyze given texts.

        Args:
            texts (list[str]): Texts to analyze.

        Returns:
            list[str]: Collection of processed documents.
        """

    def to_conllu(self, article: Article) -> None:
        """
        Write ConLLU content to a file.

        Args:
            article (Article): Article to save
        """

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """


@dataclass
class TreeNode:
    """
    Interface definition for node in the graph.
    """

    upos: str
    text: str
    children: list["TreeNode"]

def main():
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(
        path_to_raw_txt_data=ASSETS_PATH
    )

    pipeline = TextProcessingPipeline(
        corpus_manager
    )

    pipeline.run()



if __name__ == "__main__":
    main()