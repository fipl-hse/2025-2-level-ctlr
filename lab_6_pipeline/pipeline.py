"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib

from core_utils.article.article import Article, ArtifactType
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
    from spacy.language import Language
    from spacy.tokens import Doc
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    import spacy_udpipe
    from spacy_conll import ConllParser  # type: ignore
except ImportError:
    spacy_udpipe = None  # type: ignore
    ConllParser = None  # type: ignore
    print("No libraries installed. Failed to import.")


class EmptyDirectoryError(Exception):
    """
    Raised when the directory is empty.
    """


class EmptyFileError(Exception):
    """
    Raised when a file is empty.
    """


class InconsistentDatasetError(Exception):
    """
    Raised when the dataset is inconsistent.
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
            raise FileNotFoundError(f"Path does not exist: {self.path_to_raw_txt_data}")

        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError("Path does not lead to directory")

        raw_ids = []
        meta_ids = []

        patterns = {"*_raw.txt": raw_ids, "*_meta.json": meta_ids}
        for pattern, id_list in patterns.items():
            for file_path in self.path_to_raw_txt_data.glob(pattern):
                if not file_path.stat().st_size:
                    raise InconsistentDatasetError(f"File is empty: {file_path.name}")
                parts = file_path.stem.split("_")
                if len(parts) == 2 and parts[0].isdigit():
                    id_list.append(int(parts[0]))

        if not raw_ids and not meta_ids:
            raise EmptyDirectoryError("No valid files found in directory")

        if not raw_ids:
            raise EmptyDirectoryError("No raw files found")

        expected_ids = list(range(1, len(raw_ids) + 1))
        if sorted(raw_ids) != expected_ids:
            raise InconsistentDatasetError("Raw file IDs contain gaps or are not sequential")

        expected_meta_ids = list(range(1, len(meta_ids) + 1))
        if sorted(meta_ids) != expected_meta_ids:
            raise InconsistentDatasetError("Meta file IDs contain gaps or are not sequential")

        if sorted(meta_ids) != sorted(raw_ids):
            raise InconsistentDatasetError(
                "Number of meta and raw files is not equal or IDs do not match"
            )

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            article_id = int(file_path.stem.split("_")[0])
            article = from_raw(file_path)
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
            to_cleaned(article)

            if self._analyzer is not None:
                raw_path = (
                    self._corpus.path_to_raw_txt_data
                    / f"{article.article_id}_raw.txt"
                )
                from_raw(raw_path, article)
                conllu_results = self._analyzer.analyze([article.text])
                if conllu_results:
                    article.set_conllu_info(conllu_results[0])
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
            raise FileNotFoundError("UDPipe model file not found in assets/model/")
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
            conll = conll.strip() + "\n\n"
            results.append(conll)
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(path, "w", encoding="utf-8") as conllu_file:
            conllu_file.write(article.get_conllu_info())

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        if not path.stat().st_size:
            raise EmptyFileError(f"CoNLL-U file is empty: {path}")

        parser = ConllParser(self._analyzer)
        with open(path, encoding="utf-8") as conllu_file:
            content = conllu_file.read()
        doc: Doc = parser.parse_conll_text_as_spacy(content.strip())
        return doc


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
        pos_freq: dict[str, int] = {}
        for token in doc:
            if token.pos_:
                pos_freq[token.pos_] = pos_freq.get(token.pos_, 0) + 1
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
            visualize(
                article=article,
                path_to_save=ASSETS_PATH / f"{article.article_id}_image.png",
            )


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


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(path_to_raw_txt_data=ASSETS_PATH)
    analyzer = UDPipeAnalyzer()

    pipeline = TextProcessingPipeline(corpus_manager, analyzer)
    pipeline.run()

    corpus_manager = CorpusManager(path_to_raw_txt_data=ASSETS_PATH)
    pos_pipeline = POSFrequencyPipeline(corpus_manager, analyzer)
    pos_pipeline.run()




if __name__ == "__main__":
    main()
