"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import json
import pathlib
import re

from core_utils.article.article import Article
from core_utils.article.io import from_meta, from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    import spacy_udpipe
    from spacy.language import Language
    from spacy.tokens import Doc
    from spacy_conll import ConllParser
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    print("No libraries installed. Failed to import.")


class EmptyDirectoryError(Exception):
    """Raised when the directory is empty."""



class EmptyFileError(Exception):
    """Raised when a file is empty."""



class InconsistentDatasetError(Exception):
    """Raised when the dataset is inconsistent."""



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
        self._path = path_to_raw_txt_data
        self._storage = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"Path does not exist: {self._path}")
        if not self._path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._path}")
        raw_ids = set()
        meta_ids = set()
        for file_path in self._path.iterdir():
            if file_path.name.endswith("_raw.txt"):
                if file_path.stat().st_size == 0:
                    raise InconsistentDatasetError(f"Empty raw file: {file_path.name}")
                raw_id = int(file_path.stem.split("_")[0])
                raw_ids.add(raw_id)
            elif file_path.name.endswith("_meta.json"):
                if file_path.stat().st_size == 0:
                    raise InconsistentDatasetError(f"Empty meta file: {file_path.name}")
                meta_id = int(file_path.stem.split("_")[0])
                meta_ids.add(meta_id)

        if not raw_ids:
            raise EmptyDirectoryError("No raw files found in directory")
        if raw_ids != meta_ids:
            raise InconsistentDatasetError("Raw and meta file IDs do not match")
        expected_ids = set(range(1, len(raw_ids) + 1))
        if raw_ids != expected_ids:
            raise InconsistentDatasetError("Article IDs are not sequential from 1")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self._path.glob("*_raw.txt"):
            article = from_raw(file_path)
            self._storage[article.article_id] = article

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
            raw_text = article.text
            if not raw_text:
                continue

            cleaned = raw_text.lower()
            cleaned = re.sub(r'[^\w\s]', '', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            article.text = cleaned
            to_cleaned(article)

            if self._analyzer is not None:
                conllu_lines = self._analyzer.analyze([raw_text])
                if conllu_lines:
                    article.set_conllu_info(conllu_lines[0])
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
        model_folder = pathlib.Path(__file__).parent / "assets" / "model"
        model_files = list(model_folder.glob("*.udpipe"))
        if not model_files:
            raise FileNotFoundError("UDPipe model not found in assets/model/")
        model_path = str(model_files[0])
        nlp = spacy_udpipe.load_from_path("ru", model_path)
        if "conll_formatter" not in nlp.pipe_names:
            nlp.add_pipe(
                "conll_formatter",
                last=True,
                config={
                    "conversion_maps": {"XPOS": {"": "_"}},
                    "include_headers": True,
                    "ext_names": {},
                    "field_names": {},
                },
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
        results = []
        for doc in self._analyzer.pipe(texts):
            conll = doc._.conll_str
            conll = conll.rstrip('\n') + '\n\n'
            results.append(conll)
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        conllu_path.parent.mkdir(parents=True, exist_ok=True)
        with open(conllu_path, 'w', encoding='utf-8') as f:
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
        if not conllu_path.exists() or conllu_path.stat().st_size == 0:
            raise EmptyFileError(f"CoNLL-U file is empty or missing: {conllu_path}")
        parser = ConllParser(self._analyzer)
        with open(conllu_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return parser.parse_conll_text_as_spacy(content.strip())


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
        pos_freq = {}
        for token in doc:
            pos = token.pos_
            if pos:
                pos_freq[pos] = pos_freq.get(pos, 0) + 1
        return pos_freq

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        for article in self._corpus.get_articles().values():
            from_meta(article.get_meta_file_path(), article)
            pos_frequencies = self._count_frequencies(article)
            article.set_pos_info(pos_frequencies)
            to_meta(article)
            visualize(article, ASSETS_PATH / f"{article.article_id}_image.png")


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
        self._node_labels = pos

    def _make_graphs(self, _doc: Doc) -> list[DiGraph]:
        """
        Make graphs for a document.

        Args:
            doc (Doc): Document for patterns searching

        Returns:
            list[DiGraph]: Graphs for the sentences in the document
        """
        return []

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

    def _find_pattern(self, _doc_graphs: list) -> dict[int, list[TreeNode]]:
        """
        Search for the required pattern.

        Args:
            doc_graphs (list): A list of graphs for the document

        Returns:
            dict[int, list[TreeNode]]: A dictionary with pattern matches
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
    corpus_manager = CorpusManager(ASSETS_PATH)
    analyzer = UDPipeAnalyzer()
    text_pipeline = TextProcessingPipeline(corpus_manager, analyzer)
    text_pipeline.run()
    pos_pipeline = POSFrequencyPipeline(corpus_manager, analyzer)
    pos_pipeline.run()


if __name__ == "__main__":
    main()
