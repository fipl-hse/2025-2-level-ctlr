"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib
import re

from core_utils.article.article import Article, ArtifactType
from core_utils.article.io import from_raw, to_cleaned
from core_utils.constants import PROJECT_ROOT
from core_utils.pipeline import LibraryWrapper, PipelineProtocol, TreeNode

try:
    from networkx import DiGraph
    from networkx.algorithms.isomorphism import DiGraphMatcher
except ImportError:
    DiGraph = None  # type: ignore
    print("No libraries installed. Failed to import.")

try:
    import spacy_udpipe
    from spacy.language import Language
    from spacy.tokens import Doc
    from spacy_conll import ConllParser 
except ImportError:
    Language = None  # type: ignore
    Doc = None  # type: ignore
    print("No libraries installed. Failed to import.")

class EmptyDirectoryError(Exception):
    "Exception raised when directory is empty"

class InconsistentDatasetError(Exception):
    "Exception raised when IDs contain slips, number of meta and raw files is not equal, files are empty"

class EmptyFileError(Exception):
    "Exception raised when article is empty"

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
        
        files = list(self.path_to_raw_txt_data.glob("*_raw.txt")) # проверка на то, пуста ли директория
        if not files:
            raise EmptyDirectoryError
        
        id_set = set()
        for file in files:
            try:
                article_id = int(file.stem.split("_")[0])
                id_set.add(article_id)
            except (ValueError, IndexError):
                continue
        
        required_ids = set(range(1, len(id_set) + 1))
        if id_set != required_ids:
            raise InconsistentDatasetError
        
        for article_id in id_set: # перебираем все id статей; формируем пути к файлам
            raw = self.path_to_raw_txt_data / f'{article_id}_raw.txt' 
            meta = self.path_to_raw_txt_data / f'{article_id}_meta.json'
        
            if not meta.exists():
                raise InconsistentDatasetError
            if raw.stat().st_size == 0 or meta.stat().st_size == 0: # проверка, не пустые ли
                raise InconsistentDatasetError
        
        
        
    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        files = self.path_to_raw_txt_data.glob("*_raw.txt")
        for file in files:
            article_id = int(file.stem.split("_")[0])
            article = from_raw(file) #создаём объект Article для каждого raw файла
            article.article_id = article_id
            self._storage[article_id] = article # добавление в словарь



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
            raw_text = article.text
            #чистим и сохраняем текст
            final_text = raw_text.lower()
            final_text = re.sub(r"[^\w\s\'-]", "", final_text)
            article.cleaned_text = final_text
            to_cleaned(article)
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
        self._analyzer = self._bootstrap()

    def _bootstrap(self) -> Language:
        """
        Load and set up the UDPipe model.

        Returns:
            Language: Analyzer instance
        """
        model_path = PROJECT_ROOT / "lab_6_pipeline" / "assets" / "model" / "russian-syntagrus-ud-2.0-170801.udpipe"

        nlp = spacy_udpipe.load_from_path(lang="ru", path=str(model_path))

        nlp.add_pipe(
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

        return nlp

    def analyze(self, texts: list[str]) -> list[str]:
        """
        Process texts into CoNLL-U formatted markup.

        Args:
            texts (list[str]): Collection of texts

        Returns:
            list[str]: List of documents
        """
        result_list = []

        for text in texts:
            analyzed_text = self._analyzer(text)
            conllu = analyzed_text._.conll_str
            result_list.append(conllu)
        
        return result_list


    def to_conllu(self, article: Article) -> None:
        """
        Save content to ConLLU format.

        Args:
            article (Article): Article containing information to save
        """
        file_path = article.get_file_path(kind=ArtifactType.UDPIPE_CONLLU)
        
        with open(file_path, "w", encoding = "utf-8") as file:
            file.write(article._conllu_info)
            file.write('\n')

    def from_conllu(self, article: Article) -> Doc:
        """
        Load ConLLU content from article stored on disk.

        Args:
            article (Article): Article to load

        Returns:
            Doc: Document ready for parsing
        """


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
    corpus_manager = CorpusManager(PROJECT_ROOT / "tmp" / "articles")
    udpipe_analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    pipeline.run()



if __name__ == "__main__":
    main()
