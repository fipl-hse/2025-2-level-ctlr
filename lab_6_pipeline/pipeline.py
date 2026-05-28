"""
Pipeline for CONLL-U formatting.
"""


import pathlib
import re
from typing import Dict, List, Optional, Any

from core_utils.article.article import Article
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode


class EmptyDirectoryError(Exception):
    """Raised when dataset directory is empty."""


class InconsistentDatasetError(Exception):
    """Raised when dataset has structural inconsistencies."""


class EmptyFileError(Exception):
    """Raised when file is empty (stub for mark 4)."""


class UDPipeAnalyzer(LibraryWrapper):
    """Wrapper for udpipe library."""

    _analyzer: Any = None

    def __init__(self) -> None:
        """Initialize an instance of the UDPipeAnalyzer class."""
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> Any:
        """Load and set up the UDPipe model."""
        # Stub for mark 4
        return None

    def analyze(self, texts: List[str]) -> List[str]:
        """Process texts into CoNLL-U formatted markup."""
        return [""] * len(texts)

    def to_conllu(self, article: Article) -> None:
        """Save content to CoNLL-U format."""
        pass

    def from_conllu(self, article: Article) -> None:
        """Load CoNLL-U content from article stored on disk."""
        pass


class POSFrequencyPipeline:
    """Count frequencies of each POS in articles, update meta info and produce graphic report."""

    def __init__(self, corpus_manager: 'CorpusManager', analyzer: LibraryWrapper) -> None:
        """Initialize an instance of the POSFrequencyPipeline class."""
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def _count_frequencies(self, article: Article) -> dict[str, int]:
        """Count POS frequency in Article."""
        return {}

    def run(self) -> None:
        """Visualize the frequencies of each part of speech."""
        pass


class PatternSearchPipeline(PipelineProtocol):
    """Search for the required syntactic pattern."""

    def __init__(
        self, corpus_manager: 'CorpusManager', analyzer: LibraryWrapper, pos: tuple[str, ...]
    ) -> None:
        """Initialize an instance of the PatternSearchPipeline class."""
        self._corpus = corpus_manager
        self._analyzer = analyzer
        self._node_labels = pos

    def _make_graphs(self, doc: Any) -> list:
        """Make graphs for a document."""
        return []

    def _add_children(
        self, graph: Any, subgraph_to_graph: dict, node_id: int, tree_node: TreeNode
    ) -> None:
        """Add children to TreeNode."""
        pass

    def _find_pattern(self, doc_graphs: list) -> dict[int, list[TreeNode]]:
        """Search for the required pattern."""
        return {}

    def run(self) -> None:
        """Search for a pattern in documents and write found information to JSON file."""
        pass


class CorpusManager:
    """Work with articles and store them."""

    def __init__(self, path_to_raw_txt_data: pathlib.Path) -> None:
        """Initialize an instance of the CorpusManager class."""
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

        raw_files = {}
        for file in self._path.glob("*_raw.txt"):
            name = file.stem
            idx = int(name.split("_")[0])
            raw_files[idx] = file

        if not raw_files:
            raise EmptyDirectoryError(f"No valid raw files found in {self._path}")

        for idx, file in raw_files.items():
            if file.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file {file.name} is empty")

        ids = sorted(raw_files.keys())
        expected = list(range(1, len(ids) + 1))
        if ids != expected:
            raise InconsistentDatasetError(f"Article IDs not consecutive: {ids}")

    def _scan_dataset(self) -> None:
        """Register each dataset entry."""
        for file in self._path.glob("*_raw.txt"):
            name = file.stem
            idx = int(name.split("_")[0])
            article = Article(url=None, article_id=idx)
            article.text = file.read_text(encoding='utf-8')
            self._storage[idx] = article

    def get_articles(self) -> Dict[int, Article]:
        """Get storage params."""
        return self._storage


class TextProcessingPipeline(PipelineProtocol):
    """Preprocess and morphologically annotate sentences into the CONLL-U format."""

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: Optional[LibraryWrapper] = None
    ) -> None:
        """Initialize an instance of the TextProcessingPipeline class."""
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def run(self) -> None:
        """Perform basic preprocessing and write processed text to files."""
        for article_id, article in self._corpus.get_articles().items():
            raw_text = article.text
            if not raw_text:
                continue

            cleaned_text = re.sub(r'[^\w\s]', '', raw_text)
            cleaned_text = cleaned_text.lower()

            cleaned_path = self._corpus._path / f"{article_id}_cleaned.txt"
            cleaned_path.write_text(cleaned_text, encoding='utf-8')


def main() -> None:
    """Entrypoint for pipeline module."""
    corpus_manager = CorpusManager(ASSETS_PATH)
    pipeline = TextProcessingPipeline(corpus_manager)
    pipeline.run()


if __name__ == "__main__":
    main()
