"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re

from core_utils.article.article import Article
from core_utils.article.io import from_raw, to_cleaned, to_meta
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


class EmptyDirectoryError(Exception):
    """
    Exception raised when directory is empty.
    """

class InconsistentDatasetError(Exception):
    """
    Exception raised when dataset has inconsistencies.
    """

class EmptyFileError(Exception):
    """
    Exception raised when file is empty.
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
        self._storage = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError(f"Path does not exist: {self.path_to_raw_txt_data}")

        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError(f"Path does not lead to a directory: {self.path_to_raw_txt_data}")

        raw_files = {}
        meta_files = {}

        for file_path in self.path_to_raw_txt_data.iterdir():
            if not file_path.is_file():
                continue

            file_name = file_path.name
            if file_name.endswith('_raw.txt'):
                try:
                    article_id = int(file_name.split('_')[0])
                    raw_files[article_id] = file_path
                except ValueError:
                    continue
            elif file_name.endswith('_meta.json'):
                try:
                    article_id = int(file_name.split('_')[0])
                    meta_files[article_id] = file_path
                except ValueError:
                    continue

        if not raw_files:
            raise EmptyDirectoryError(f"No valid _raw.txt files found in {self.path_to_raw_txt_data}")

        if set(raw_files.keys()) != set(meta_files.keys()):
            raise InconsistentDatasetError(
                f"Raw and meta files mismatch. Raw IDs: {sorted(raw_files.keys())}, "
                f"Meta IDs: {sorted(meta_files.keys())}"
            )

        for article_id, file_path in raw_files.items():
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file {file_path.name} is empty")

        for article_id, file_path in meta_files.items():
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Meta file {file_path.name} is empty")

        expected_ids = set(range(1, max(raw_files.keys()) + 1))
        if raw_files.keys() != expected_ids:
            raise InconsistentDatasetError(
                f"Article IDs contain slips. Expected: {sorted(expected_ids)}, "
                f"Got: {sorted(raw_files.keys())}"
            )


    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path_to_raw_txt_data.iterdir():
            if not file_path.is_file():
                continue

            file_name = file_path.name
            if file_name.endswith('_raw.txt'):
                try:
                    article_id = int(file_name.split('_')[0])
                    self._storage[article_id] = Article(url=None, article_id=article_id)
                except ValueError:
                    continue

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

        for article_id, article in articles.items():
            raw_file_path = self._corpus.path_to_raw_txt_data / f"{article_id}_raw.txt"
            raw_text = from_raw(raw_file_path)
            
            cleaned_text = re.sub(r'[^\w\s-]', '', raw_text)
            cleaned_text = cleaned_text.lower()

            article.set_cleaned_text(cleaned_text)
            to_cleaned(article)

            if self._analyzer is not None:
                sentences = [s.strip() for s in re.split(r'[.!?]+', cleaned_text) if s.strip()]
                if sentences:
                    conllu_results = self._analyzer.analyze(sentences)
                    full_conllu = '\n'.join(conllu_results)
                    article.set_conllu_info(full_conllu)
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
        import ssl
        import certifi

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        import spacy_udpipe
        from spacy_conll import ConllFormatter

        spacy_udpipe.download("ru")
        nlp = spacy_udpipe.load("ru")

        nlp.add_pipe("conll_formatter", last=True, config={"conllu": True, "is_ud": True})

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
            if doc._.has_extension('conll'):
                results.append(doc._.conll)
            else:
                results.append("")
        return results


    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_info = article.get_conllu_info()
        if conllu_info:
            from core_utils.constants import ASSETS_PATH
            conllu_path = ASSETS_PATH / f"{article.get_article_id()}_udpipe.conllu"
            with open(conllu_path, 'w', encoding='utf-8') as f:
                f.write(conllu_info)

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        from spacy_conll import parse_conll

        file_path = article.get_file_path()
        conllu_path = file_path.parent / f"{article.get_article_id()}_udpipe.conllu"

        if not conllu_path.exists():
            raise FileNotFoundError(f"ConLLU file not found: {conllu_path}")

        if conllu_path.stat().st_size == 0:
            raise EmptyFileError(f"ConLLU file is empty: {conllu_path}")

        with open(conllu_path, 'r', encoding='utf-8') as f:
            conllu_content = f.read()

        doc = parse_conll(conllu_content)
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

        pos_freq = {}
        for token in doc:
            pos = token.pos_
            pos_freq[pos] = pos_freq.get(pos, 0) + 1

        return pos_freq

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        from core_utils.visualizer import visualize

        articles = self._corpus.get_articles()

        for article_id, article in articles.items():
            pos_frequencies = self._count_frequencies(article)

            article.set_pos_info(pos_frequencies)
            to_meta(article)

            image_path = article.get_file_path().parent / f"{article_id}_image.png"
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
        self._pos = pos

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
            graph = DiGraph()
            for token in sent:
                graph.add_node(token.i, token=token)
            for token in sent:
                if token.head != token:
                    graph.add_edge(token.head.i, token.i, dep=token.dep_)
            graphs.append(graph)
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
        for child_id in graph.successors(node_id):
            child_token = graph.nodes[child_id]['token']
            if child_id in subgraph_to_graph:
                child_node = TreeNode(child_token, parent=tree_node)
                tree_node.add_child(child_node)
                self._add_children(graph, subgraph_to_graph, child_id, child_node)

    def _find_pattern(self, doc_graphs: list) -> dict[int, list[TreeNode]]:
        """
        Search for the required pattern.

        Args:
            doc_graphs (list): A list of graphs for the document

        Returns:
            dict[int, list[TreeNode]]: A dictionary with pattern matches
        """
        matches = {}
        root_pos, _ = self._pos[0], self._pos[2]

        for sent_idx, graph in enumerate(doc_graphs):
            sent_matches = []
            for node_id in graph.nodes:
                token = graph.nodes[node_id]['token']
                if token.pos_ == root_pos:
                    root_node = TreeNode(token)
                    sent_matches.append(root_node)
            if sent_matches:
                matches[sent_idx] = sent_matches
        return matches

    def run(self) -> None:
        """
        Search for a pattern in documents and writes found information to JSON file.
        """
        articles = self._corpus.get_articles()

        for _, article in articles.items():
            doc = self._analyzer.from_conllu(article)
            graphs = self._make_graphs(doc)
            matches = self._find_pattern(graphs)

            article.set_pattern_info(matches)
            to_meta(article)


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    from core_utils.constants import ASSETS_PATH

    corpus_manager = CorpusManager(ASSETS_PATH)

    udpipe_analyzer = UDPipeAnalyzer()
    text_pipeline = TextProcessingPipeline(corpus_manager, analyzer = udpipe_analyzer)
    text_pipeline.run()

    pos_pipeline = POSFrequencyPipeline(corpus_manager, analyzer = udpipe_analyzer)
    pos_pipeline.run()

    print("Pipeline processing completed successfully")


if __name__ == "__main__":
    main()
