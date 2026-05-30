"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re

import spacy_udpipe
from spacy_conll.parser import ConllParser

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_meta, from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
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
        self._check_path_valid()
        raw_files, meta_files = self._collect_and_validate_files()
        self._validate_ids_continuity(raw_files)

    def _check_path_valid(self) -> None:
        """
        Check if path exists and is a directory.
        """
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError(
                f"Path does not exist: "
                f"{self.path_to_raw_txt_data}"
            )
        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError(
                f"Path does not lead to a directory: "
                f"{self.path_to_raw_txt_data}"
            )

    def _collect_and_validate_files(self) -> tuple[dict, dict]:
        """
        Collect raw and meta files and validate they exist and are not empty.
        """
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
            raise EmptyDirectoryError(
                f"No valid _raw.txt files found in "
                f"{self.path_to_raw_txt_data}"
            )

        if set(raw_files.keys()) != set(meta_files.keys()):
            raise InconsistentDatasetError(
                f"Raw and meta files mismatch. Raw IDs: {sorted(raw_files.keys())}, "
                f"Meta IDs: {sorted(meta_files.keys())}"
            )

        for file_path in list(raw_files.values()) + list(meta_files.values()):
            if file_path.stat().st_size == 0:
                raise InconsistentDatasetError(f"File {file_path.name} is empty")

        return raw_files, meta_files

    def _validate_ids_continuity(self, raw_files: dict) -> None:
        """
        Validate that article IDs are continuous from 1 to N.
        """
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
                    article = Article(url=None, article_id = article_id)

                    with open(file_path, 'r', encoding='utf-8') as f:
                        article.text = f.read().rstrip('\n')

                    self._storage[article_id] = article
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

        for article in articles.values():
            to_cleaned(article)

            if self._analyzer is not None:
                raw_text = article.text
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
        self._parser = ConllParser(self._analyzer)

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        model_path = str((PROJECT_ROOT / 'lab_6_pipeline' / 'assets' / 'model' /
                      'russian-syntagrus-ud-2.0-170801.udpipe'))
        model = spacy_udpipe.load_from_path(lang='ru', path=model_path)
        model.add_pipe(
            'conll_formatter',
            last=True,
            config={
                'conversion_maps': {'XPOS': {'': '_'}},
                'include_headers': True,
                'field_names': {
                    'ID': 'ID',
                    'FORM': 'FORM',
                    'LEMMA': 'LEMMA',
                    'UPOS': 'UPOS',
                    'XPOS': 'XPOS',
                    'FEATS': 'FEATS',
                    'HEAD': 'HEAD',
                    'DEPREL': 'DEPREL',
                    'DEPS': 'DEPS',
                    'MISC': 'MISC'
                }
            }
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
        return [self._analyzer(text)._.conll_str for text in texts]


    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(article.get_conllu_info())
            f.write('\n')


    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        if len(path.read_text(encoding='utf-8')) == 0:
            raise EmptyFileError('An article file is empty.')
        with open(path, 'r', encoding='utf-8') as f:
            document = f.read()
        parsed: Doc = self._parser.parse_conll_text_as_spacy(document.strip('\n'))
        return parsed


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
        articles = self._corpus.get_articles()

        for article_id, article in articles.items():
            pos_frequencies = self._count_frequencies(article)

            article.set_pos_info(pos_frequencies)
            to_meta(article)

            image_path = ASSETS_PATH / f"{article_id}_image.png"
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
    corpus_manager = CorpusManager(ASSETS_PATH)

    udpipe_analyzer = UDPipeAnalyzer()
    text_pipeline = TextProcessingPipeline(corpus_manager, analyzer = udpipe_analyzer)
    text_pipeline.run()

    pos_pipeline = POSFrequencyPipeline(corpus_manager, analyzer = udpipe_analyzer)
    pos_pipeline.run()

    print("Pipeline processing completed successfully")


if __name__ == "__main__":
    main()
