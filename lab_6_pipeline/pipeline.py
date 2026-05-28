"""
Pipeline for CONLL-U formatting.
"""


import json
import pathlib
import re
from typing import Any, Dict, List, Optional

from core_utils.article.article import Article
from core_utils.article.io import from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize


class EmptyDirectoryError(Exception):
    """Raised when dataset directory is empty."""


class InconsistentDatasetError(Exception):
    """Raised when dataset has structural inconsistencies."""


class EmptyFileError(Exception):
    """Raised when file is empty."""


class CorpusManager:
    """Work with articles and store them."""

    def __init__(self, path_to_raw_txt_data: pathlib.Path) -> None:
        self._storage: Dict[int, Article] = {}
        self._path = path_to_raw_txt_data
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
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

        for file in raw_files.values():
            if file.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file {file.name} is empty")

        ids = sorted(raw_files.keys())
        expected = list(range(1, len(ids) + 1))
        if ids != expected:
            raise InconsistentDatasetError(f"Article IDs not consecutive: {ids}")

    def _scan_dataset(self) -> None:
        for file in self._path.glob("*_raw.txt"):
            name = file.stem
            idx = int(name.split("_")[0])
            article = Article(url=None, article_id=idx)
            from_raw(article)
            self._storage[idx] = article

    def get_articles(self) -> Dict[int, Article]:
        return self._storage


class TextProcessingPipeline(PipelineProtocol):
    """Preprocess and morphologically annotate sentences into the CONLL-U format."""

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: Optional[LibraryWrapper] = None
    ) -> None:
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def run(self) -> None:
        for article in self._corpus.get_articles().values():
            raw_text = article.text
            if not raw_text:
                continue
            cleaned = re.sub(r'[^\w\s]', '', raw_text)
            cleaned = cleaned.lower()
            article.set_cleaned(cleaned)
            to_cleaned(article, ASSETS_PATH)


class UDPipeAnalyzer(LibraryWrapper):
    """Wrapper for udpipe library."""

    _analyzer: Any

    def __init__(self) -> None:
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> Any:
        return None

    def analyze(self, texts: List[str]) -> List[str]:
        return [""] * len(texts)

    def to_conllu(self, article: Article) -> None:
        pass

    def from_conllu(self, article: Article) -> None:
        pass


class POSFrequencyPipeline:
    """Count frequencies of each POS in articles, update meta info and produce graphic report."""

    def __init__(self, corpus_manager: CorpusManager, analyzer: LibraryWrapper) -> None:
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def _count_frequencies(self, article: Article) -> Dict[str, int]:
        return {}

    def run(self) -> None:
        for article in self._corpus.get_articles().values():
            meta = article.get_meta()
            meta["pos_frequencies"] = {}
            article.set_pos_info(meta)
            to_meta(article, ASSETS_PATH)
            visualize(article, ASSETS_PATH / f"{article.get_article_id()}_image.png")


class PatternSearchPipeline(PipelineProtocol):
    """Search for the required syntactic pattern."""

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: LibraryWrapper, pos: tuple[str, ...]
    ) -> None:
        self._corpus = corpus_manager
        self._analyzer = analyzer
        self._node_labels = pos

    def _make_graphs(self, doc: Any) -> List[Any]:
        return []

    def _add_children(
        self, graph: Any, subgraph_to_graph: dict, node_id: int, tree_node: TreeNode
    ) -> None:
        pass

    def _find_pattern(self, doc_graphs: list) -> Dict[int, List[TreeNode]]:
        return {}

    def run(self) -> None:
        for article in self._corpus.get_articles().values():
            meta = article.get_meta()
            meta["pattern_matches"] = {}
            article.set_pos_info(meta)
            to_meta(article, ASSETS_PATH)


def main() -> None:
    corpus_manager = CorpusManager(ASSETS_PATH)
    pipeline = TextProcessingPipeline(corpus_manager)
    pipeline.run()


if __name__ == "__main__":
    main()
