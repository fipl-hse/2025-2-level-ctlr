"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    from spacy.language import Language
    from spacy.tokens import Doc
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    print("No libraries installed. Failed to import.")


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
        self._storage = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        path = self.path_to_raw_txt_data
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")
        raw_files = sorted(path.glob("*_raw.txt"))
        meta_files = sorted(path.glob("*_meta.json"))
        if not raw_files:
            raise EmptyDirectoryError(f"Directory is empty: {path}")
        raw_ids = []
        for f in raw_files:
            try:
                article_id = int(f.stem.split("_")[0])
                raw_ids.append(article_id)
            except (ValueError, IndexError):
                continue
        meta_ids = []
        for f in meta_files:
            try:
                article_id = int(f.stem.split("_")[0])
                meta_ids.append(article_id)
            except (ValueError, IndexError):
                continue
        if len(raw_ids) != len(meta_ids):
            raise InconsistentDatasetError(
                "Number of raw and meta files does not match"
            )
        raw_ids_sorted = sorted(raw_ids)
        expected_ids = list(range(1, len(raw_ids_sorted) + 1))
        if raw_ids_sorted != expected_ids:
            raise InconsistentDatasetError(
                "Article IDs contain slips or do not start from 1"
            )
        for f in raw_files:
            if f.stat().st_size == 0:
                raise InconsistentDatasetError(f"File is empty: {f}")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        path = self.path_to_raw_txt_data
        for raw_file in sorted(path.glob("*_raw.txt")):
            try:
                article_id = int(raw_file.stem.split("_")[0])
            except (ValueError, IndexError):
                continue
            article = Article(url=None, article_id=article_id)
            from_raw(raw_file, article)
            self._storage[article_id] = article

    def get_articles(self) -> dict:
        """
        Get storage params.

        Returns:
            dict: Storage params
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
            from_raw(article.get_raw_text_path(), article)
            to_cleaned(article)
            if self._analyzer:
                conllu_output = self._analyzer.analyze([article.get_raw_text()])
                if isinstance(conllu_output, list):
                    article.set_conllu_info("\n".join(conllu_output))
                else:
                    article.set_conllu_info(conllu_output)
                self._analyzer.to_conllu(article)


class UDPipeAnalyzer(LibraryWrapper):
    """
    Wrapper for udpipe library.
    """

    #: Analyzer
    _analyzer: Language

    def __init__(self) -> None:
        """
        Initialize an instance of the UDPipeAnalyzer class.
        """
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        model_path = pathlib.Path(__file__).parent / "assets" / "model"
        model_files = list(model_path.glob("*.udpipe"))
        if not model_files:
            raise FileNotFoundError(
                f"No .udpipe model found in {model_path}"
            )
        model_file = str(model_files[0])
        nlp = spacy_udpipe.load_from_path(lang="ru", path=model_file)
        if "conll_formatter" not in nlp.pipe_names:
            nlp.add_pipe(
                "conll_formatter",
                config={"conversion_maps": {"DEPREL": {"root": "ROOT"}},
                        "include_headers": True},
                last=True
            )
        return nlp

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        result = []
        for doc in self._analyzer.pipe(texts):
            result.append(doc._.conll_str)
        return result

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(conllu_path, "w", encoding="utf-8") as f:
            f.write(article.get_conllu_info())

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        conllu_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(conllu_path, "r", encoding="utf-8") as f:
            conllu_text = f.read()
        return self._analyzer(conllu_text)


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
        doc = self._analyzer.from_conllu(article)
        frequencies: dict[str, int] = {}
        for token in doc:
            pos = token.pos_
            if pos:
                frequencies[pos] = frequencies.get(pos, 0) + 1
        return frequencies

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """


class PatternSearchPipeline(PipelineProtocol):
    """
    Search for the required syntactic pattern.
    """

    def __init__(
        self, corpus_manager: CorpusManager, analyzer: LibraryWrapper, pos: tuple[str, ...]
    ) -> None:
        """
        Initialize an instance of the PatternSearchPipeline class.

        Args:
            corpus_manager (CorpusManager): CorpusManager instance
            analyzer (LibraryWrapper): Analyzer instance
            pos (tuple[str, ...]): Root, Dependency, Child part of speech
        """
        self._corpus = corpus_manager
        self._analyzer = analyzer
        self._pos = pos

    def _make_graphs(self, doc: Doc) -> list[DiGraph]:
        """
        Make graphs for a document.

        Args:
            doc (Doc): Document for patterns searching

        Returns:
            list[DiGraph]: Graphs for the sentences in the document
        """

    def _add_children(
        self, graph: DiGraph, subgraph_to_graph: dict, node_id: int, tree_node: TreeNode
    ) -> None:
        """
        Add children to TreeNode.

        Args:
            graph (DiGraph): Sentence graph to search for a pattern
            subgraph_to_graph (dict): Matched subgraph
            node_id (int): ID of root node of the match
            tree_node (TreeNode): Root node of the match
        """

    def _find_pattern(self, doc_graphs: list) -> dict[int, list[TreeNode]]:
        """
        Search for the required pattern.

        Args:
            doc_graphs (list): A list of graphs for the document

        Returns:
            dict[int, list[TreeNode]]: A dictionary with pattern matches
        """

    def run(self) -> None:
        """
        Search for a pattern in documents and writes found information to JSON file.
        """

class EmptyDirectoryError(Exception):
    """Raised when the dataset directory is empty."""
 
 
class InconsistentDatasetError(Exception):
    """Raised when the dataset structure is inconsistent."""


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(path_to_raw_txt_data=ASSETS_PATH)
    analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, analyzer)
    pipeline.run()


if __name__ == "__main__":
    main()
