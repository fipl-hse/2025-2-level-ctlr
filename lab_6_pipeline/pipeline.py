"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re
import string

import spacy_udpipe # type: ignore

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode

try:
    import networkx # type: ignore
    import networkx.algorithms.isomorphism # type: ignore
except ImportError:
    networkx.DiGraph = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    import spacy.language # type: ignore
    import spacy.tokens # type: ignore
except ImportError:
    spacy.language.Language = None  # type: ignore
    spacy.tokens.Doc = None  # type: ignore
    print("No libraries installed. Failed to import.")


class InconsistentDatasetError(Exception):
    """
    Raised when IDs contain slips, number of meta and raw files is not equal, files are empty.
    """

class EmptyDirectoryError(Exception):
    """
    Raised when directory is empty.
    """
    
class EmptyFileError(Exception):
    """
    Raised when file is empty.
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
            raise FileNotFoundError("Path does not exist")
        if not self._path.is_dir():
            raise NotADirectoryError("Path does not lead to a directory")
        files = list(self._path.iterdir())
        if not files:
            raise EmptyDirectoryError("Directory is empty")
        raw_files = []
        meta_files = []
        for file in files:
            if file.name.endswith("_raw.txt"):
                raw_files.append(file)
            if file.name.endswith("_meta.json"):
                meta_files.append(file)
        if not raw_files:
            raise InconsistentDatasetError("No raw files found in dataset")
        if len(raw_files) != len(meta_files):
            raise InconsistentDatasetError(
                "Number of raw and meta files does not match"
            )
        raw_ids = []
        for file in raw_files:
            if not file.stat().st_size:
                raise InconsistentDatasetError("Raw file is empty")
            raw_ids.append(int(file.name.split("_")[0]))
        meta_ids = []
        for file in meta_files:
            if not file.stat().st_size:
                raise InconsistentDatasetError("Meta file is empty")
            meta_ids.append(int(file.name.split("_")[0]))
        raw_ids.sort()
        meta_ids.sort()
        expected_ids = list(range(1, len(raw_ids) + 1))
        if raw_ids != expected_ids:
            raise InconsistentDatasetError("Raw file IDs contain slips")
        if meta_ids != expected_ids:
            raise InconsistentDatasetError("Meta file IDs contain slips")
        if raw_ids != meta_ids:
            raise InconsistentDatasetError("Raw and meta file IDs do not match")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file in self._path.iterdir():
            if file.name.endswith("_raw.txt"):
                article = from_raw(file)
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
        articles = self._corpus.get_articles()
        for article in articles.values():
            path_to_raw = article.get_raw_text_path()
            article = from_raw(path_to_raw, article)
            original_text = article.text
            cleaned_text = original_text.lower()
            for char in string.punctuation:
                cleaned_text = cleaned_text.replace(char, "")
            cleaned_text = re.sub(r'[^a-zа-яё0-9\s]', '', cleaned_text)
            cleaned_text = ' '.join(cleaned_text.split())
            article.text = cleaned_text
            to_cleaned(article)
            if self._analyzer is not None:
                result = self._analyzer.analyze([original_text])
                if result is not None:
                    conllu_text = result[0]
                    article.set_conllu_info(conllu_text)
                    self._analyzer.to_conllu(article)


class UDPipeAnalyzer(LibraryWrapper):
    """
    Wrapper for udpipe library.
    """

    #: Analyzer
    _analyzer: spacy.language.Language

    def __init__(self) -> None:
        """
        Initialize an instance of the UDPipeAnalyzer class.
        """
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> spacy.language.Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        model_path = PROJECT_ROOT / "lab_6_pipeline" / "assets" / "model" / "russian-syntagrus-ud-2.0-170801.udpipe"
        model = spacy_udpipe.load_from_path(
            lang="ru",
            path=str(model_path),
        )
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
        results = []
        for text in texts:
            doc = self._analyzer(text)
            conllu = doc._.conll_str
            conllu = conllu.rstrip('\n') + '\n\n'
            results.append(conllu)
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(path, "w", encoding="utf-8") as file:
            file.write(article.get_conllu_info())

    def from_conllu(self, article: Article) -> spacy.tokens.Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        path = article.get_file_path(ArtifactType.CONLLU)
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

    def _make_graphs(self, doc: spacy.tokens.Doc) -> list[networkx.DiGraph]:
        """
        Make graphs for a document.

        Args:
            doc (Doc): Document for patterns searching

        Returns:
            list[DiGraph]: Graphs for the sentences in the document
        """

    def _add_children(
        self, graph: networkx.DiGraph, subgraph_to_graph: dict, node_id: int, tree_node: TreeNode
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


if __name__ == "__main__":
    main()
