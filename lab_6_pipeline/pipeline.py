"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode
from core_utils.visualizer import visualize

import spacy
from spacy.tokens import Doc

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    import spacy_conll
    import spacy_udpipe
    from spacy.language import Language
    from spacy.tokens import Doc
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    spacy_conll = None
    spacy_udpipe = None
    print("No libraries installed. Failed to import.")


class InconsistentDatasetError(Exception):
    """
    Raised when dataset has inconsistencies.
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
            raise NotADirectoryError(f"Path is not a directory: {self.path_to_raw_txt_data}")
        files = list(self.path_to_raw_txt_data.iterdir())
        if not files:
            raise EmptyDirectoryError(f"Directory is empty: {self.path_to_raw_txt_data}")
        raw_files = {}
        meta_files = {}
        for file_path in files:
            if not file_path.is_file():
                continue
            file_name = file_path.name
            raw_match = re.match(r'^(\d+)_raw\.txt$', file_name)
            if raw_match:
                article_id = int(raw_match.group(1))
                raw_files[article_id] = file_path
            meta_match = re.match(r'^(\d+)_meta\.json$', file_name)
            if meta_match:
                article_id = int(meta_match.group(1))
                meta_files[article_id] = file_path
        if not raw_files:
            raise InconsistentDatasetError("No raw files found in directory")
        raw_ids = sorted(raw_files.keys())
        if raw_ids[0] != 1:
            raise InconsistentDatasetError(f"First article ID must be 1, got {raw_ids[0]}")
        if len(raw_ids) != len(set(raw_ids)):
            raise InconsistentDatasetError("Duplicate article IDs found")
        missing_meta = [aid for aid in raw_ids if aid not in meta_files]
        if missing_meta:
            raise InconsistentDatasetError(f"Missing meta files for IDs: {missing_meta}")
        for article_id, raw_path in raw_files.items():
            if raw_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Raw file {article_id}_raw.txt is empty")
        for article_id, meta_path in meta_files.items():
            if meta_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"Meta file {article_id}_meta.json is empty")

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path_to_raw_txt_data.iterdir():
            if not file_path.is_file():
                continue
            match = re.match(r'^(\d+)_raw\.txt$', file_path.name)
            if match:
                article_id = int(match.group(1))
                article = Article(url=None, article_id=article_id)
                with open(file_path, 'r', encoding='utf-8') as f:
                    article.text = f.read()
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
            from_raw(article.get_raw_text_path(), article)
            raw_text = article.text
            cleaned_text = re.sub(r'[^\w\s]', '', raw_text)
            cleaned_text = cleaned_text.lower()
            article.text = cleaned_text
            to_cleaned(article)
            article.text = raw_text
            if self._analyzer is not None:
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
        super().__init__()
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        model_path = pathlib.Path(__file__).parent / "assets" / "model" / "russian-syntagrus-ud-2.0-170801.udpipe"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
        nlp = spacy_udpipe.load_from_path(lang="ru", path=str(model_path))
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
            conllu_lines = []
            for sent_id, sent in enumerate(doc.sents, 1):
                conllu_lines.append(f"# sent_id = {sent_id}")
                conllu_lines.append(f"# text = {sent.text}")
                for token in sent:
                    token_id = token.i - sent.start + 1
                    word = token.text
                    lemma = token.lemma_ if token.lemma_ else "_"
                    upos = token.pos_
                    xpos = "_"
                    if token.morph and str(token.morph) != "":
                        morph = str(token.morph).replace("|", "|").replace(" ", "|")
                    else:
                        morph = "_"
                    if token.head == token:
                        head = 0
                        deprel = "root"
                    else:
                        head = token.head.i - sent.start + 1
                        deprel = token.dep_ if token.dep_ else "_"
                    deps = "_"
                    conllu_lines.append(
                        f"{token_id}\t{word}\t{lemma}\t{upos}\t{xpos}\t"
                        f"{morph}\t{head}\t{deprel}\t{deps}\t"
                    )
                conllu_lines.append("")
            results.append("\n".join(conllu_lines) + "\n")
        return results

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        conllu_info = article.get_conllu_info()
        if conllu_info:
            article_id = article.article_id
            articles_dir = pathlib.Path(__file__).parent.parent / "test_tmp"
            articles_dir.mkdir(parents=True, exist_ok=True)
            file_path = articles_dir / f"{article_id}_udpipe.conllu"
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
            raise EmptyFileError(f"File does not exist: {file_path}")
        if file_path.stat().st_size == 0:
            raise EmptyFileError(f"File is empty: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        words = []
        pos_tags = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 5:
                word = parts[1]
                upos = parts[3]
                words.append(word)
                pos_tags.append(upos)
        nlp = spacy.blank("ru")
        doc = Doc(nlp.vocab, words=words)
        for i, token in enumerate(doc):
            if i < len(pos_tags):
                token.pos_ = pos_tags[i]
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
            if pos:
                pos_freq[pos] = pos_freq.get(pos, 0) + 1
        return pos_freq

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        articles = self._corpus.get_articles()
        for article in articles.values():
            pos_frequencies = self._count_frequencies(article)
            article.set_pos_info(pos_frequencies)
            to_meta(article)
            image_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU).parent / f"{article.article_id}_image.png"
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
    print("Pipeline execution completed successfully")

if __name__ == "__main__":
    main()
