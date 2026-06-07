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
        self.path = path_to_raw_txt_data
        self._storage = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path.exists():
            raise FileNotFoundError('File does not exist.')
        if not self.path.is_dir():
            raise NotADirectoryError('The path does not lead to a directory.')
        all_files = list(self.path.iterdir())
        if not all_files:
            raise EmptyDirectoryError('The directory is empty.')
        raw_files = [
            raw for raw in self.path.iterdir() if raw.name.endswith('_raw.txt')
        ]
        meta_files = [
            meta for meta in self.path.iterdir() if meta.name.endswith('_meta.json')
        ]
        if len(raw_files) != len(meta_files):
            raise InconsistentDatasetError('Numbers of raw and meta files are not equal.')
        raw_ids = [int(f.stem.split('_')[0]) for f in raw_files]
        if len(set(raw_ids)) != len(raw_ids):
            raise InconsistentDatasetError('Raw IDs are not unique.')
        if min(raw_ids) <= 0:
            raise InconsistentDatasetError('Raw IDs must be positive.')
        meta_ids = [int(f.stem.split('_')[0]) for f in meta_files]
        if len(set(meta_ids)) != len(meta_ids):
            raise InconsistentDatasetError('Meta IDs are not unique.')
        if min(meta_ids) <= 0:
            raise InconsistentDatasetError('Meta IDs must be positive.')
        for filepath in raw_files + meta_files:
            if filepath.stat().st_size == 0:
                raise InconsistentDatasetError('The file is empty.')

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for meta_path in self.path.glob('*_meta.json'):
            article_id = int(meta_path.stem.split('_')[0])
            self._storage[article_id] = from_meta(meta_path)
        for raw_path in self.path.glob('*_raw.txt'):
            article_id = int(raw_path.stem.split('_')[0])
            self._storage[article_id].text = raw_path.read_text(encoding='utf-8')

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
        articles = list(self._corpus.get_articles().values())
        for article in articles:
            to_cleaned(article)
        if not self._analyzer:
            return
        raw_texts = [article.text for article in articles]
        conllu_results = self._analyzer.analyze(raw_texts)
        if conllu_results is None:
            return
        for article, conllu_text in zip(articles, conllu_results):
            if conllu_text:
                article.set_conllu_info(conllu_text)
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
        model_path = (PROJECT_ROOT / 'lab_6_pipeline' / 'assets' / 'model' /
                      'russian-syntagrus-ud-2.0-170801.udpipe')
        model = spacy_udpipe.load_from_path(lang='ru', path=str(model_path))
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
        path.write_text(article.get_conllu_info() + '\n', encoding='utf-8')

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        document = path.read_text(encoding='utf-8')
        if len(document) == 0:
            raise EmptyFileError('An article file is empty.')
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
        self._corpus_manager = corpus_manager
        self._analyzer = analyzer

    def _count_frequencies(self, article: Article) -> dict[str, int]:
        """
        Count POS frequency in Article.

        Args:
            article (Article): Article instance

        Returns:
            dict[str, int]: POS frequencies
        """
        freq = {}
        article_conllu = self._analyzer.from_conllu(article)
        for token in article_conllu:
            freq[token.pos_] = freq.get(token.pos_, 0) + 1
        return freq

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        for article in self._corpus_manager.get_articles().values():
            freq_pos = self._count_frequencies(article)
            article.set_pos_info(freq_pos)
            to_meta(article)
            visualize(article=article, path_to_save=ASSETS_PATH / f'{article.article_id}_image.png')

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
    analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, analyzer)
    pipeline.run()
    pos_freq_pipeline = POSFrequencyPipeline(corpus_manager, analyzer)
    pos_freq_pipeline.run()


if __name__ == "__main__":
    main()
