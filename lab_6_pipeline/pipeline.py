"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
"""
Pipeline for CONLL-U formatting.
"""
import pathlib

try:
    import spacy_udpipe
except ImportError:
    spacy_udpipe = None
    print("Warning: spacy_udpipe not installed")

try:
    from networkx import DiGraph
except ImportError:
    DiGraph = None
    print("Warning: networkx not installed")

try:
    from spacy import Language
    from spacy.tokens import Doc
except ImportError:
    Language = None
    Doc = None
    print("Warning: spacy not installed")

try:
    from spacy.training.converters import conllu_to_docs
except ImportError:
    conllu_to_docs = None
    print("Warning: conllu_to_docs not available (spacy version < 3.5)")

try:
    from spacy_conll import ConllFormatter, init_parser
    from spacy_conll.parser import ConllParser
except ImportError:
    ConllFormatter = None
    init_parser = None
    ConllParser = None
    print("Warning: spacy_conll not installed")

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_meta, from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize


class EmptyFileError(Exception):
    """Raised when a file is empty."""

class EmptyDirectoryError(Exception):
    """Raised when directory is empty."""


class InconsistentDatasetError(Exception):
    """Raised when dataset has inconsistencies."""


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
        self.path = path_to_raw_txt_data
        self._storage: dict[int, Article] = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"Path does not exist: {self.path}")

        if not self.path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self.path}")

        raw_files = list(self.path.glob("*_raw.txt"))

        if not raw_files:
            raise EmptyDirectoryError(f"Directory is empty: {self.path}")

        meta_files = list(self.path.glob("*_meta.json"))

        if len(raw_files) != len(meta_files):
            raise InconsistentDatasetError(
                f"Number of raw files ({len(raw_files)}) does not match "
                f"number of meta files ({len(meta_files)})"
            )

        ids = set()
        for file_path in raw_files:
            try:
                file_id = int(file_path.stem.split("_")[0])
                ids.add(file_id)
            except (ValueError, IndexError):
                continue

        if ids:
            expected_ids = set(range(1, max(ids) + 1))
            if ids != expected_ids:
                missing = expected_ids - ids
                raise InconsistentDatasetError(
                    f"IDs contain slips. Missing IDs: {missing}"
                )

        for file_path in raw_files:
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"File is empty: {file_path}")

        for file_path in meta_files:
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"File is empty: {file_path}")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        raw_files = self.path.glob("*_raw.txt")
        for file_path in raw_files:
            try:
                article_id = int(file_path.stem.split("_")[0])
            except (ValueError, IndexError):
                continue

            article = from_raw(file_path)
            article.article_id = article_id

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
        articles = self._corpus.get_articles()

        for article in articles.values():
            to_cleaned(article)

            if self._analyzer is not None:
                raw_text = article.get_raw_text()
                conllu_results = self._analyzer.analyze([raw_text])

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
        model_path = pathlib.Path("lab_6_pipeline/assets/model/ru-syntagrus.udpipe")

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")

        nlp = spacy_udpipe.load_from_path(
            lang="ru",
            path=str(model_path),
            meta={"description": "Russian UDPipe model"}
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
        conllu_outputs = []

        for text in texts:
            doc = self._analyzer(text)
            lines = []

            for sent_idx, sent in enumerate(doc.sents):
                lines.append(f"# sent_id = {sent_idx + 1}")
                lines.append(f"# text = {sent.text}")

                for token_idx, token in enumerate(sent, start=1):
                    lines.append(
                        f"{token_idx}\t{token.text}\t"
                        f"{token.lemma_ if token.lemma_ else '_'}\t"
                        f"{token.pos_ if token.pos_ else '_'}\t_\t"
                        f"{str(token.morph) if token.morph else '_'}\t"
                        f"{token.head.i - sent.start + 1 if token.head != token else 0}\t"
                        f"{token.dep_ if token.dep_ else '_'}\t_\t"
                        f"{'SpaceAfter=No' if not token.whitespace_ else '_'}"
                    )

                lines.append("")

            result = "\n".join(lines)
            if not result.endswith("\n\n"):
                result = result.rstrip('\n') + "\n\n"

            conllu_outputs.append(result)

        return conllu_outputs
        # conllu_outputs = []

        # for text in texts:
        #     doc = self._analyzer(text)
        #     conllu_outputs.append(doc._.conll_str)

        # return conllu_outputs


    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        if self._analyzer is None:
            return

        conllu_info = article.get_conllu_info()

        if conllu_info:
            file_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(conllu_info)


    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        file_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)

        if not file_path.exists():
            raise FileNotFoundError(f"CONLLU file not found: {file_path}")

        if file_path.stat().st_size == 0:
            raise EmptyFileError(f"CONLLU file is empty: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as source_file:
            conllu_content = source_file.read()

        docs = list(conllu_to_docs(conllu_content))

        if not docs:
            raise ValueError("No documents parsed from CONLLU content")

        return docs[0]

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

        pos_frequencies = {}

        for token in doc:
            pos_tag = token.pos_
            if pos_tag:
                pos_frequencies[pos_tag] = pos_frequencies.get(pos_tag, 0) + 1

        return pos_frequencies

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        articles = self._corpus.get_articles()

        for article in articles.values():
            pos_frequencies = self._count_frequencies(article)

            article.set_pos_info(pos_frequencies)

            to_meta(article)

            image_path = ASSETS_PATH / f"{article.article_id}_image.png"
            visualize(article=article, path_to_save=image_path)


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
    data_path = pathlib.Path("tmp/articles")
    data_path.mkdir(parents=True, exist_ok=True)

    corpus_manager = CorpusManager(path_to_raw_txt_data=data_path)

    udpipe_analyzer = UDPipeAnalyzer()

    text_pipeline = TextProcessingPipeline(corpus_manager)
    text_pipeline.run()

    udpipe_pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    udpipe_pipeline.run()

    pos_pipeline = POSFrequencyPipeline(corpus_manager, udpipe_analyzer)
    pos_pipeline.run()

if __name__ == "__main__":
    main()
