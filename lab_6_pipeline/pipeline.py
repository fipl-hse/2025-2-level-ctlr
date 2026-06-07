"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable
import pathlib
import re
from typing import cast

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_meta, from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize

try:
    import spacy_udpipe
    from spacy.language import Language
    from spacy.tokens import Doc
    from spacy_conll import ConllParser
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    ConllParser = None  # type: ignore
    spacy_udpipe = None  # type: ignore

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None  # type: ignore
    DiGraphMatcher = None  # type: ignore


class EmptyDirectoryError(Exception):
    """
    Dataset directory is empty.
    """


class InconsistentDatasetError(Exception):
    """
    Dataset has missing, empty or inconsistently numbered files.
    """


class EmptyFileError(Exception):
    """
    CoNLL-U file is empty.
    """


class CorpusManager:
    """
    Work with articles and store them.
    """

    def __init__(self, path_to_raw_txt_data: pathlib.Path) -> None:
        """
        Initialize an instance of the CorpusManager class.

        Args:
            path_to_raw_txt_data (pathlib.Path): Path to raw txt data
        """
        self.path_to_raw_txt_data = path_to_raw_txt_data
        self._storage: dict[int, Article] = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError()
        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError()

        files = [path for path in self.path_to_raw_txt_data.iterdir() if path.is_file()]
        if not files:
            raise EmptyDirectoryError()

        raw_files = {}
        meta_files = {}
        for file_path in files:
            raw_match = re.fullmatch(r"(\d+)_raw\.txt", file_path.name)
            meta_match = re.fullmatch(r"(\d+)_meta\.json", file_path.name)
            if raw_match:
                raw_files[int(raw_match.group(1))] = file_path
            elif meta_match:
                meta_files[int(meta_match.group(1))] = file_path

        if not raw_files:
            raise EmptyDirectoryError()

        raw_ids = set(raw_files)
        meta_ids = set(meta_files)
        expected_ids = set(range(1, max(raw_ids) + 1))

        if raw_ids != expected_ids or raw_ids != meta_ids:
            raise InconsistentDatasetError()

        # Проверяем только файлы датасета, посторонние файлы по условию игнорируются.
        for file_path in [*raw_files.values(), *meta_files.values()]:
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError()

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for raw_path in sorted(self.path_to_raw_txt_data.glob("*_raw.txt")):
            article_id = int(raw_path.stem.split("_")[0])
            article = Article(url=None, article_id=article_id)
            meta_path = self.path_to_raw_txt_data / f"{article_id}_meta.json"

            # Сначала восстанавливаем metadata, потом добавляем текст из raw.
            from_meta(meta_path, article)
            from_raw(raw_path, article)
            self._storage[article_id] = article

    def get_articles(self) -> dict[int, Article]:
        """
        Get storage params.

        Returns:
            dict[int, Article]: Articles by their identifiers
        """
        return self._storage


class TextProcessingPipeline(PipelineProtocol):
    """
    Preprocess and morphologically annotate sentences into the CONLL-U format.
    """

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: LibraryWrapper | None = None
    ) -> None:
        """
        Initialize an instance of the TextProcessingPipeline class.

        Args:
            corpus_manager (CorpusManager): CorpusManager instance
            analyzer (LibraryWrapper | None, optional): Analyzer instance. Defaults to None.
        """
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def run(self) -> None:
        """
        Perform basic preprocessing and write processed text to files.
        """
        for article in self._corpus.get_articles().values():
            # to_cleaned внутри использует стандартный метод Article.get_cleaned_text.
            to_cleaned(article)

            if self._analyzer is None:
                continue

            analyzed_texts = self._analyzer.analyze([article.text])
            if analyzed_texts:
                article.set_conllu_info(analyzed_texts[0])
                self._analyzer.to_conllu(article)


class UDPipeAnalyzer(LibraryWrapper):
    """
    Wrapper for udpipe library.
    """

    _analyzer: Language

    def __init__(self) -> None:
        """
        Initialize an instance of the UDPipeAnalyzer class.
        """
        self._analyzer = self._bootstrap()
        self._parser = ConllParser(self._analyzer)

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        if spacy_udpipe is None or ConllParser is None:
            raise ImportError("spacy-udpipe and spacy-conll must be installed")

        model_path = (
            PROJECT_ROOT
            / "lab_6_pipeline"
            / "assets"
            / "model"
            / "russian-syntagrus-ud-2.0-170801.udpipe"
        )
        if not model_path.exists():
            raise FileNotFoundError(f"UDPipe model is not found: {model_path}")

        analyzer = spacy_udpipe.load_from_path(lang="ru", path=str(model_path))
        analyzer.add_pipe(
            "conll_formatter",
            last=True,
            config={
                "conversion_maps": {"XPOS": {"": "_"}},
                "include_headers": True,
                "field_names": {
                    "ID": "ID",
                    "FORM": "FORM",
                    "LEMMA": "LEMMA",
                    "UPOS": "UPOS",
                    "XPOS": "XPOS",
                    "FEATS": "FEATS",
                    "HEAD": "HEAD",
                    "DEPREL": "DEPREL",
                    "DEPS": "DEPS",
                    "MISC": "MISC",
                },
            },
        )
        analyzer.max_length = 2_000_000
        return analyzer

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        analyzed_texts = []
        for text in texts:
            document = self._analyzer(text)
            analyzed_texts.append(document._.conll_str)
        return analyzed_texts

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        conllu_text = article.get_conllu_info().rstrip("\n") + "\n\n"
        conllu_path.write_text(conllu_text, encoding="utf-8")

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        conllu_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        conllu_text = conllu_path.read_text(encoding="utf-8")
        if not conllu_text.strip():
            raise EmptyFileError()

        # Новая версия spacy-conll ожидает root в нижнем регистре.
        parser_text = conllu_text.replace("\tROOT\t", "\troot\t").rstrip("\n")
        return cast(Doc, self._parser.parse_conll_text_as_spacy(parser_text))


class POSFrequencyPipeline:
    """
    Count frequencies of each POS in articles, update meta info and produce graphic report.
    """

    def __init__(self, corpus_manager: CorpusManager, analyzer: LibraryWrapper) -> None:
        """
        Initialize an instance of the POSFrequencyPipeline class.

        Args:
            corpus_manager (CorpusManager): CorpusManager instance
            analyzer (LibraryWrapper): Analyzer instance
        """
        self._corpus = corpus_manager
        self._analyzer = analyzer

    def _count_frequencies(self, article: Article) -> dict[str, int]:
        """
        Count POS frequency in Article.

        Args:
            article (Article): Article instance

        Returns:
            dict[str, int]: POS frequencies
        """
        frequencies: dict[str, int] = {}
        document = self._analyzer.from_conllu(article)
        for token in document:
            frequencies[token.pos_] = frequencies.get(token.pos_, 0) + 1
        return frequencies

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        for article in self._corpus.get_articles().values():
            frequencies = self._count_frequencies(article)
            article.set_pos_info(frequencies)

            # Article уже содержит metadata из пятой лабы, поэтому они не теряются.
            to_meta(article)
            image_path = ASSETS_PATH / f"{article.article_id}_image.png"
            visualize(article=article, path_to_save=image_path)


class PatternSearchPipeline(PipelineProtocol):
    """
    Search for the required syntactic pattern.

    This class belongs to the mark 10 task and is not used in main.
    """

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: LibraryWrapper, pos: tuple[str, ...]
    ) -> None:
        """
        Initialize an instance of the PatternSearchPipeline class.
        """
        self._corpus = corpus_manager
        self._analyzer = analyzer
        self._node_labels = pos

    def _make_graphs(self, _doc: Doc) -> list[DiGraph]:
        """
        Make graphs for a document.
        """
        return []

    def _add_children(
        self, graph: DiGraph, subgraph_to_graph: dict, node_id: int, tree_node: TreeNode
    ) -> None:
        """
        Add children to TreeNode.
        """

    def _find_pattern(self, _doc_graphs: list) -> dict[int, list[TreeNode]]:
        """
        Search for the required pattern.
        """
        return {}

    def run(self) -> None:
        """
        Search for a pattern in documents and writes found information to JSON file.
        """


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(path_to_raw_txt_data=ASSETS_PATH)
    analyzer = UDPipeAnalyzer()

    text_pipeline = TextProcessingPipeline(corpus_manager, analyzer)
    text_pipeline.run()

    pos_pipeline = POSFrequencyPipeline(corpus_manager, analyzer)
    pos_pipeline.run()


if __name__ == "__main__":
    main()
