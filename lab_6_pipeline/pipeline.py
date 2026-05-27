"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re
from collections import Counter

import spacy_udpipe
from spacy_conll import init_parser
from networkx import DiGraph
from spacy import Language
from spacy.tokens import Doc

from core_utils.article.article import Article
from core_utils.article.io import from_raw, to_cleaned, to_meta, from_meta
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize
from core_utils.constants import ASSETS_PATH


class InconsistentDatasetError(Exception):
    """dataset is inconsistent"""
    pass


class EmptyDirectoryError(Exception):
    """directory is empty"""
    pass


class EmptyFileError(Exception):
    """file is empty"""
    pass

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
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError
        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError
        files = list(self.path_to_raw_txt_data.glob("*_raw.txt"))
        if not files:
            raise EmptyDirectoryError
        ids = []
        for file_path in files:
            try:
                article_id = int(file_path.stem.split("_")[0])
                ids.append(article_id)
            except (ValueError, IndexError):
                continue
        if not ids:
            raise InconsistentDatasetError
        ids.sort()
        expected_ids = list(range(1, max(ids) + 1))
        if ids != expected_ids:
            raise InconsistentDatasetError
        for article_id in ids:
            raw_path = self.path_to_raw_txt_data / f"{article_id}_raw.txt"
            meta_path = self.path_to_raw_txt_data / f"{article_id}_meta.json"
            if not meta_path.exists():
                raise InconsistentDatasetError
            if raw_path.stat().st_size == 0:
                raise InconsistentDatasetError
            if meta_path.stat().st_size == 0:
                raise InconsistentDatasetError

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            try:
                article_id = int(file_path.stem.split("_")[0])
            except (ValueError, IndexError):
                continue
            article = Article(url=None, article_id=article_id)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    article.text = f.read()
            except Exception:
                article.text = ""
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
        for _, article in articles.items():
            raw_path = article.get_raw_text_path()
            raw_text = from_raw(raw_path)
            if raw_text is None:
                continue
            cleaned_text = raw_text.lower()
            cleaned_text = re.sub(r'[^\w\s]', '', cleaned_text)
            to_cleaned(article, cleaned_text)
            if self._analyzer is not None:
                try:
                    conllu_results = self._analyzer.analyze([raw_text])
                    if conllu_results and conllu_results[0]:
                        article.set_conllu_info(conllu_results[0])
                        self._analyzer.to_conllu(article)
                except Exception:
                    continue


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
        nlp = spacy_udpipe.load("ru")
        nlp = init_parser(nlp, "spacy_conll")
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
        for text in texts:
            doc = self._analyzer(text)
            conllu = doc._.conllu
            results.append(conllu)
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_content = article.get_conllu_info()
        if not conllu_content:
            return
        file_path = article.get_file_path("udpipe")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(conllu_content)

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        file_path = article.get_file_path("udpipe")
        if not file_path.exists():
            raise FileNotFoundError
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            raise EmptyFileError
        doc = self._analyzer(content)
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
        pos_tags = []
        for token in doc:
            pos_tags.append(token.pos_)
        return dict(Counter(pos_tags))

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        articles = self._corpus.get_articles()
        for _, article in articles.items():
            try:
                pos_freq = self._count_frequencies(article)
                meta = from_meta(article) or {}
                meta["pos_frequencies"] = pos_freq
                article.set_pos_info(pos_freq)
                to_meta(article, meta)
                image_path = article.get_file_path("image")
                visualize(article=article, path_to_save=image_path)
            except (FileNotFoundError, EmptyFileError):
                continue
            except Exception:
                continue


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

    def _make_graphs(self, doc: Doc) -> list[DiGraph]:
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
        pass

    def _find_pattern(self, doc_graphs: list) -> dict[int, list[TreeNode]]:
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
        pass


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(ASSETS_PATH)
    udpipe_analyzer = UDPipeAnalyzer()
    text_pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    text_pipeline.run()
    pos_pipeline = POSFrequencyPipeline(corpus_manager, udpipe_analyzer)
    pos_pipeline.run()


if __name__ == "__main__":
    main()
