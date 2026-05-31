"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib

import spacy_udpipe

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
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

class InconsistentDatasetError(Exception):
    """
    IDs contain slips, number of meta and raw files is not equal, files are empty
    """
class EmptyDirectoryError(Exception):
    """
    Directory is empty
    """
class EmptyFileError(Exception):
    """
    File is empty
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
        self._path = path_to_raw_txt_data
        self._storage = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self._path.exists():
            raise FileNotFoundError()
        if not self._path.is_dir():
            raise NotADirectoryError()
        files = list(self._path.iterdir())
        if not files:
            raise EmptyDirectoryError()
        raw_files = [file for file in files if file.name.endswith('_raw.txt')]
        meta_files = [file for file in files if file.name.endswith('_meta.json')]
        if meta_files:
            if len(raw_files) != len(meta_files):
                raise InconsistentDatasetError()
            raw_ids = [int(file.name.split('_')[0]) for file in raw_files]
            meta_ids = [int(file.name.split('_')[0]) for file in meta_files]
            if raw_ids!=meta_ids:
                raise InconsistentDatasetError()
        for file in raw_files:
            if file.stat().st_size == 0:
                raise EmptyFileError("File is empty")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file in self._path.iterdir():
             if file.name.endswith("_raw.txt"):
                article_id = int(file.name.split('_')[0])
                article = Article(url=None, article_id=article_id)
                from_raw(file, article)
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
        articles=self._corpus.get_articles()
        for article in articles.values():
            raw_text = article.get_raw_text()
            if not raw_text:
                continue
            result_text = [char for char in raw_text if char.isalnum() or char.isspace()]
            cleaned_text = ''.join(result_text).lower()
            to_cleaned(article, cleaned_text)
            if self._analyzer:
                conllu_text = self._analyzer.analyze([raw_text])
                conllu_info = conllu_text[0]
                article.set_conllu_info(conllu_info)
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
        model_path = PROJECT_ROOT / "lab_6_pipeline"/ "assets"/ "model"/ "russian-syntagrus-ud-2.0-170801.udpipe"
        model = spacy_udpipe.load_from_path(lang="ru", path=str(model_path))
        model.add_pipe(
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
        return model

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        conllu_texts = []
        for text in texts:
            analyzed_text = self._analyzer(text)
            conllu_text = analyzed_text._.conll_str
            conllu_texts.append(conllu_text)
        return conllu_texts

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        path = article.get_file_path("conllu")
        with open(path, "w", encoding="utf-8") as file:
            file.write(article.get_conllu_info())

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(path, "r", encoding="utf-8") as file:
            return file.read()

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

    def _count_frequencies(self, article: Article) -> dict[str, int]:
        """
        Count POS frequency in Article.

        Args:
            article (Article): Article instance

        Returns:
            dict[str, int]: POS frequencies
        """

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
    udpipe_analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    pipeline.run()

if __name__ == "__main__":
    main()
