"""
Pipeline for CONLL-U formatting.
"""

import sys
import re
import pathlib
from collections import Counter

from core_utils.article.article import Article
from core_utils.article.io import from_raw, to_cleaned, from_meta, to_meta
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize
from core_utils.constants import ASSETS_PATH

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None
    print("No libraries installed. Failed to import.")

try:
    from spacy.language import Language
    from spacy.tokens import Doc
    import spacy_udpipe
    from spacy_conll import ConllFormatter
    from spacy_conll.parser import ConllParser
except ImportError:
    Language = None
    Doc = None
    print("No libraries installed. Failed to import.")


class EmptyDirectoryError(Exception):
    """Raised when dataset directory is empty."""

class InconsistentDatasetError(Exception):
    """Raised when dataset has missing files, gaps, empty files, etc."""

class EmptyFileError(Exception):
    """Raised when a required file is empty."""


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
        self._storage: dict[int, Article] = {}
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

        try:
            next(self._path.iterdir())
        except StopIteration as exc:
            raise EmptyDirectoryError(f"Directory is empty: {self._path}") from exc

        raw_files: dict[int, pathlib.Path] = {}
        meta_files: dict[int, pathlib.Path] = {}
        pattern_raw = re.compile(r'^(\d+)_raw\.txt$')
        pattern_meta = re.compile(r'^(\d+)_meta\.json$')

        for file_path in self._path.iterdir():
            if not file_path.is_file():
                continue
            name = file_path.name
            raw_match = pattern_raw.match(name)
            meta_match = pattern_meta.match(name)
            if raw_match:
                idx = int(raw_match.group(1))
                raw_files[idx] = file_path
            elif meta_match:
                idx = int(meta_match.group(1))
                meta_files[idx] = file_path

        if set(raw_files.keys()) != set(meta_files.keys()):
            raise InconsistentDatasetError("Mismatch between raw and meta file ids")
        if not raw_files:
            raise InconsistentDatasetError("No valid raw files found")

        ids = sorted(raw_files.keys())
        expected = list(range(1, max(ids) + 1))
        if ids != expected:
            raise InconsistentDatasetError(f"Article ids are not consecutive: {ids}")

        for idx, path in raw_files.items():
            if path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file {idx} is empty")
        for idx, path in meta_files.items():
            if path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Meta file {idx} is empty")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        pattern = re.compile(r'^(\d+)_raw\.txt$')
        for file_path in self._path.iterdir():
            if not file_path.is_file():
                continue
            match = pattern.match(file_path.name)
            if match:
                article_id = int(match.group(1))
                self._storage[article_id] = Article(url=None, article_id=article_id)

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
            from_raw(article)
            raw_text = article.text
            if not raw_text:
                continue

            cleaned_text = raw_text.lower()
            cleaned_text = re.sub(r'[^\w\s]', '', cleaned_text)
            article.text = cleaned_text
            to_cleaned(article)

            if self._analyzer is not None:
                conll_list = self._analyzer.analyze([raw_text])
                if conll_list:
                    article.set_conllu_info(conll_list[0])
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

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        current_dir = pathlib.Path(__file__).parent
        model_dir = current_dir / "assets" / "model"
        if not model_dir.exists():
            model_dir = pathlib.Path("assets/model")
        model_files = list(model_dir.glob("*.udpipe"))
        if not model_files:
            raise FileNotFoundError("UDPipe model not found in assets/model/")
        model_path = str(model_files[0])

        nlp = spacy_udpipe.load_from_path(model_path)
        nlp.add_pipe(ConllFormatter(nlp), last=True)
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
            results.append(doc._.conll_str)
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conll_info = article.get_conllu_info()
        if not conll_info:
            return
        raw_path = article.get_file_path(kind='raw')
        if raw_path:
            conllu_path = raw_path.parent / f"{article.article_id}_udpipe.conllu"
        else:
            conllu_path = pathlib.Path("tmp/articles") / f"{article.article_id}_udpipe.conllu"
        conllu_path.parent.mkdir(parents=True, exist_ok=True)
        conllu_path.write_text(conll_info, encoding='utf-8')

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        raw_path = article.get_file_path(kind='raw')
        if raw_path:
            conllu_path = raw_path.parent / f"{article.article_id}_udpipe.conllu"
        else:
            conllu_path = pathlib.Path("tmp/articles") / f"{article.article_id}_udpipe.conllu"

        if not conllu_path.exists():
            raise FileNotFoundError(f"CONLL-U file not found: {conllu_path}")
        content = conllu_path.read_text(encoding='utf-8')
        if not content.strip():
            raise EmptyFileError(f"CONLL-U file is empty: {conllu_path}")

        parser = ConllParser(self._analyzer)
        doc = parser.parse_conll_text_as_spacy(content)
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
        pos_counter = Counter()
        for token in doc:
            pos_counter[token.pos_] += 1
        return dict(pos_counter)

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        articles = self._corpus.get_articles()
        for article in articles.values():
            freq_dict = self._count_frequencies(article)

            meta = from_meta(article)
            if meta is None:
                meta = {}
            meta['pos_frequencies'] = freq_dict
            to_meta(article, meta)

            image_path = article.get_file_path(kind='raw').parent / f"{article.article_id}_image.png"
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
        graphs = []
        for sent in doc.sents:
            g = DiGraph()
            for token in sent:
                g.add_node(token.i, label=token.pos_)
            for token in sent:
                if token.dep_ != "ROOT" and token.head.i != token.i:
                    g.add_edge(token.head.i, token.i, label=token.dep_)
            graphs.append(g)
        return graphs

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
    try:
        corpus_manager = CorpusManager(ASSETS_PATH)
        analyzer = UDPipeAnalyzer()

        pattern_pipeline = PatternSearchPipeline(corpus_manager, analyzer, ("VERB", "NOUN", "ADP"))
        pattern_pipeline.run()

    except (FileNotFoundError, NotADirectoryError, EmptyDirectoryError,
            InconsistentDatasetError, EmptyFileError) as e:
        print(f"Pipeline error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
