"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks
import json
import pathlib
import re

import spacy_udpipe
from networkx import DiGraph
from spacy_conll import init_parser
from spacy_conll.parser import ConllParser
from spacy.language import Language
from spacy.tokens import Doc

from core_utils.article.article import (
    Article,
    ArtifactType,
    get_article_id_from_filepath,
    split_by_sentence,
)
from core_utils.article.io import from_meta, from_raw, to_cleaned
from core_utils.constants import ASSETS_PATH, PROJECT_ROOT
from core_utils.pipeline import (
    AbstractCoNLLUAnalyzer,
    CoNLLUDocument,
    LibraryWrapper,
    PipelineProtocol,
    TreeNode,
    UnifiedCoNLLUDocument,
)

<<<<<<< HEAD
# logger = get_child_logger(__file__)
MODEL_PATH = PROJECT_ROOT / "lab_6_pipeline" / "assets" / "model"
MODEL_NAME = "russian-syntagrus-ud-2.0-170801.udpipe"

class InconsistentDatasetError(Exception):
    """
    Raised when IDs contain slips,
    number of meta and raw files is not equal,
    files are empty.
    """
class EmptyDirectoryError(Exception):
    """
    Raised when directory is empty.
    """
class EmptyFileError(Exception):
    pass
=======
>>>>>>> upstream

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
        self._storage: dict[int, Article] = {}
        self._validate_dataset()
        self._scan_dataset()

    def _validate_dataset(self) -> None:
        """
        Validate folder with assets.
        """
        if not self.path_to_raw_txt_data.exists():
            raise FileNotFoundError(
                "File does not exist"
            )

        if not self.path_to_raw_txt_data.is_dir():
            raise NotADirectoryError(
                "Path does not lead to directory"
            )

        found_files: dict[str, list] = {}
        for file_path in self.path_to_raw_txt_data.iterdir():
            file_name = file_path.name

            if re.match(r"\d*_raw\.txt|\d*_meta\.json", file_name):
                if not file_path.stat().st_size:
                    raise InconsistentDatasetError(
                        f"File is empty: {file_name}"
                    )
                id, file_type = file_name.split("_")
                found_files.setdefault(file_type, []).append(int(id))

        if not found_files:
            raise EmptyDirectoryError(
                "Directory is empty"
            )

        raw_ids = found_files.get("raw.txt")
        meta_ids = found_files.get("meta.json")
        if not raw_ids:
            raise InconsistentDatasetError(
                "Dataset contains no raw files"
            )
        if not meta_ids:
            raise InconsistentDatasetError(
                "Dataset contains no meta files"
            )
        if len(meta_ids) != len(raw_ids):
            raise InconsistentDatasetError(
                "Number of meta and raw files is not equal"
            )
        if len(raw_ids) != sorted(raw_ids)[-1]:
            raise InconsistentDatasetError(
                "Raw file IDs contain slips"
            )
        if len(meta_ids) != sorted(meta_ids)[-1]:
            raise InconsistentDatasetError(
                "Meta file IDs contain slips"
            )


    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for meta_file_path in self.path_to_raw_txt_data.glob("*_meta.json"):
            article_id = get_article_id_from_filepath(meta_file_path)
            self._storage[article_id] = from_meta(meta_file_path, Article(None, article_id))
        for raw_file_path in self.path_to_raw_txt_data.glob("*_raw.txt"):
            article_id = get_article_id_from_filepath(raw_file_path)
            self._storage[article_id] = from_raw(raw_file_path, self._storage[article_id])


    def get_articles(self) -> dict[int, Article]:
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
        self.corpus_manager = corpus_manager
        self._analyzer = analyzer

    def run(self) -> None:
        """
        Perform basic preprocessing and write processed text to files.
        """
        for article in self.corpus_manager.get_articles().values():
            to_cleaned(article)

            if self._analyzer:
                conlu_sentences = self._analyzer.analyze(split_by_sentence(article.get_raw_text()))
                if conlu_sentences:
                    article.set_conllu_info("".join([str(sentence) for sentence in conlu_sentences]))
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
        self._analyzer.add_pipe(
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
        },)
        self._parser = ConllParser(self._analyzer)

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        return spacy_udpipe.load_from_path(
            lang="ru",
            path=str(MODEL_PATH / MODEL_NAME)
        )
    

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        conllu_markup_list = []
        for sent_id, text in enumerate(texts, start=1):
            conllu_markup = [
                f"# sent_id = {sent_id}",
                f"# text = {text}"
            ]
            doc = self._analyzer(text)
            for token_id, token in enumerate(doc, start=1):
                conllu_markup.append("\t".join([
                    str(token_id), #ID
                    token.text, #FORM
                    token.lemma_, #LEMMA
                    token.pos_ or "_", #UPOS
                    token.tag_ or "_", #XPOS
                    "|".join(morph for morph in token.morph) or "_", #FEATS
                    "0" if token.dep_=="ROOT" else str(token.head.i + 1), #HEAD
                    token.dep_ or "_", #DEPREL
                    "_", #DEPS
                    "_" if token.whitespace_ else "SpaceAfter=No" #MISK
                ]))

            conllu_markup.append("\n")
            conllu_markup_list.append("\n".join(conllu_markup))

        return conllu_markup_list

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
        return self._parser.parse_conll_file_as_spacy(article)
        # with open(article.get_file_path(ArtifactType.UDPIPE_CONLLU), "r", encoding="utf-8") as f:
        #     return self._parser.parse_conll_text_as_spacy(f.read())


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
        self.corpus_manager = corpus_manager
        self._analyzer = analyzer
        self._corpus = {}

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
    test_texts = [
        "Красивая - мама красиво, училась в ПДД и ЖКУ по адресу Львовская 10 лет с почтой test . ",
        "Я сегодня шла за картошкой в огород.",
        "Ой, упала, вот это поворот!",
        "Замарала пяточку, все лицо в навозе.",
        "Ещё не успела носиком по травке поелозить."
    ]

    corpus_manager = CorpusManager(ASSETS_PATH)
    udpipe_analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    # l = udpipe_analyzer.analyze(test_texts)
    # pipeline.run()

    # from pprint import pprint
    # for sent in l:
    #     pprint(sent)
    #     print()


    path = r"C:\Users\artem\hse\2025-2-level-ctlr\tmp\articles\1_udpipe.conllu"
    path = r"C:\Users\artem\hse\2025-2-level-ctlr\lab_6_pipeline\tests\test_files\reference_udpipe_test.conllu"
    article = Article(None, 2)
    doc = udpipe_analyzer.from_conllu(path)

    # print("ok")



if __name__ == "__main__":
    main()
