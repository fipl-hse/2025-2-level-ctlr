"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code

import pathlib
import re
from typing import cast

import spacy_udpipe
from spacy_conll import ConllParser, init_parser

from core_utils.article.article import (
    Article,
    ArtifactType,
    get_article_id_from_filepath,
)
from core_utils.article.io import from_meta, from_raw, to_cleaned, to_meta
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
from core_utils.pipeline import (
    LibraryWrapper,
    PipelineProtocol,
    TreeNode,
)
from core_utils.visualizer import visualize

MODEL_PATH = PROJECT_ROOT / "lab_6_pipeline" / "assets" / "model"
MODEL_NAME = "russian-syntagrus-ud-2.0-170801.udpipe"

class EmptyDirectoryError(Exception):
    """
    Raised when directory is empty.
    """

class InconsistentDatasetError(Exception):
    """
    Raised when the dataset has structural issues (missing files, gaps, etc.).
    """

class EmptyFileError(Exception):
    """
    Raised when a file is empty.
    """

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
            raise FileNotFoundError(
                "Path does not exist."
            )
        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError(
                "Path does not lead to a directory."
            )

        # files = list(self.path_to_raw_txt_data.iterdir())
        # if not files:
        #     raise EmptyDirectoryError(
        #         "Directory is empty."
        #         )

        found_raw = []
        found_meta = []
        for raw_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            raw_name = raw_path.name
            if not raw_path.stat().st_size or not re.match(r"\d*_raw\.txt", raw_name):
                raise InconsistentDatasetError(
                    f"File is empty: {raw_name}"
                )
            found_raw.append(get_article_id_from_filepath(raw_path))
        for meta_path in self.path_to_raw_txt_data.glob("*_meta.json"):
            meta_name = meta_path.name
            if not meta_path.stat().st_size or not re.match(r"\d*_meta\.json", meta_name):
                raise InconsistentDatasetError(
                    f"File is empty: {meta_name}"
                )
            found_meta.append(get_article_id_from_filepath(meta_path))

        if not found_meta or not found_raw:
            raise EmptyDirectoryError(
                "Directory is empty"
            )
        if len(found_meta) != len(found_raw):
            raise InconsistentDatasetError(
                "Number of meta and raw files is unequal"
            )


        for id_raw, file_id in enumerate(sorted(found_raw), start=1):
            if id_raw != file_id:
                raise InconsistentDatasetError(
                    "Meta file IDs contain slips"
                )

        for id_meta, file_id in enumerate(sorted(found_meta), start=1):
            if id_meta != file_id:
                raise InconsistentDatasetError(
                    "Meta file IDs contain slips"
                )

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for raw_file_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            self._storage[from_raw(raw_file_path).article_id] = from_raw(raw_file_path)



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
            if not self._analyzer:
                return
            conllu_list = self._analyzer.analyze([article.text])
            if conllu_list and conllu_list[0]:
                article.set_conllu_info(conllu_list[0])
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
        model_path = (PROJECT_ROOT /"lab_6_pipeline" /
                      "assets" /"model" /
                      "russian-syntagrus-ud-2.0-170801.udpipe")

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")

        nlp = spacy_udpipe.load_from_path(lang="ru", path=str(model_path))
        config = {
            "field_names": {
                "ID": "ID",
                "FORM": "FORM",
                "UPOS": "UPOS",
                "XPOS": "XPOS",
                "FEATS": "FEATS",
                "HEAD": "HEAD",
                "DEPREL": "DEPREL",
                "DEPS": "DEPS",
                "MISC": "MISC",
            },
            "conversion_maps": {"XPOS": {"": "_"}},
            "include_headers": True,
            "disable_pandas": True,
        }
        if "conll_formatter" in nlp.pipe_names:
            nlp.remove_pipe("conll_formatter")
        nlp.add_pipe("conll_formatter", config=config, last=True)
        if not Doc.has_extension("conllu"):
            Doc.set_extension("conllu", getter=lambda doc: doc._.conll)
        return cast(Language, nlp)


    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        return [self._analyzer(text)._.conll_str + '\n' for text in texts]

    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        with open(article.get_file_path(ArtifactType.UDPIPE_CONLLU), "w", encoding="utf-8") as f:
            f.write(article.get_conllu_info())

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """
        article_path = article.get_file_path(ArtifactType.UDPIPE_CONLLU)
        if not article_path.exists():
            raise FileNotFoundError(f"File not found: {article_path}")
        if article_path.stat().st_size == 0:
            raise EmptyFileError(f"{article.article_id} conllu is empty")
        with open(article_path, "r", encoding="utf-8") as f:
            conllu_text = f.read()
        conllu_doc = self._parser.parse_conll_text_as_spacy(conllu_text.strip())
        if not isinstance(conllu_doc, Doc):
            raise TypeError
        return conllu_doc


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
        frequencies = {}
        doc = self._analyzer.from_conllu(article)
        for token in doc:
            frequencies[token.pos_] = frequencies.get(token.pos_, 0) + 1
        return frequencies

    def run(self) -> None:
        """
        Visualize the frequencies of each part of speech.
        """
        for article in self._corpus.get_articles().values():
            pos_frequencies = self._count_frequencies(article)
            article_meta = from_meta(article.get_meta_file_path())
            article_meta.set_pos_info(pos_frequencies)
            to_meta(article_meta)
            visualize(article_meta, ASSETS_PATH / f"{article.article_id}_image.png")


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
    visualizer = POSFrequencyPipeline(corpus_manager, analyzer)
    pipeline.run()
    visualizer.run()


if __name__ == "__main__":
    main()
