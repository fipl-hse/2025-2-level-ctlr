"""
Pipeline for CONLL-U formatting.
"""

# pylint: disable=too-few-public-methods, unused-import, undefined-variable, too-many-nested-blocks, duplicate-code
import pathlib

import re
import matplotlib.pyplot as plt
import networkx as nx
import spacy_udpipe

from networkx import DiGraph
from networkx.algorithms.isomorphism import DiGraphMatcher
from spacy.language import Language
from spacy.tokens import Doc, Token
from spacy_conll.parser import ConllParser

from core_utils.article.article import (
    Article,
    ArtifactType,
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
            raw.name for raw in self.path.iterdir() if raw.name.endswith('_raw.txt')
        ]
        meta_files = [
            meta.name for meta in self.path.iterdir() if meta.name.endswith('_meta.json')
        ]
        if len(raw_files) != len(meta_files):
            raise InconsistentDatasetError('Numbers of raw and meta files are not equal.')
        for file_id in range(1, len(raw_files) + 1):
            if not any(f'{file_id}_raw.txt' == raw for raw in raw_files):
                raise InconsistentDatasetError('Raw IDs contain slips.')
        for meta_id in range(1, len(meta_files) + 1):
            if not any(f'{meta_id}_meta.json' == meta for meta in meta_files):
                raise InconsistentDatasetError('Meta IDs contain slips.')
        if any(
            True for filepath in self.path.iterdir()
            if filepath.stat().st_size == 0
            and (filepath.name.endswith('_raw.txt') or filepath.name.endswith('_meta.json'))
        ):
            raise InconsistentDatasetError('The file is empty.')

    def _scan_dataset(self) -> None:
        """
        Register each dataset entry.
        """
        for file_path in self.path.glob('*_raw.txt'):
            self._storage[int(file_path.name[:-8])] = from_raw(file_path)

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
        for article in self._corpus.get_articles().values():
            to_cleaned(article)
            if self._analyzer is not None:
                conllu_list = self._analyzer.analyze([article.text])
                conllu_str = conllu_list[0] if conllu_list else ''
                article.set_conllu_info(conllu_str)
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
        self._corpus = corpus_manager
        self._analyzer = analyzer
        self._node_labels = pos

    def _make_graph_from_root(self, graph: DiGraph, root: Token) -> None:
        """
        Make graph from root token

        Args:
            graph (DiGraph): Empty graph
            root (Token): Root token from sentence
        """
        graph.add_node(root.i, text=root.text, label=root.pos_)

        for child in root.children:
            graph.add_edge(root.i, child.i, label=child.dep_)
            self._make_graph_from_root(graph, child)


    def _make_graphs(self, doc: Doc) -> list[DiGraph]:
        """
        Make graphs for a document.

        Args:
            doc (Doc): Document for patterns searching

        Returns:
            list[DiGraph]: Graphs for the sentences in the document
        """
        graph_lst = []
        for sentence in doc.sents:
            graph = DiGraph()
            self._make_graph_from_root(graph, sentence.root)
            graph_lst.append(graph)
        return graph_lst

    def _make_target_graph(self) -> nx.DiGraph:
        """
        Used in _find_pattern function to create nx.DiGraph instance,
        using self._node_labels values.

        Returns:
            nx.DiGraph: Instance with self._node_labels as nodes.
        """
        target_graph = nx.DiGraph()
        for i, label in enumerate(self._node_labels):
            target_graph.add_node(i, label=label)
            if i > 0:
                target_graph.add_edge(i - 1, i)

        return target_graph

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
        next_subgraph_id = subgraph_to_graph[node_id] + 1
        next_child_id = None
        for graph_id, subgraph_id in subgraph_to_graph.items():
            if subgraph_id == next_subgraph_id:
                next_child_id = graph_id
                break
        if next_child_id is not None:
            child_node = TreeNode(
                graph.nodes[next_child_id]["label"],
                graph.nodes[next_child_id]["text"],
                []
            )
            tree_node.children.append(child_node)
            self._add_children(graph, subgraph_to_graph, next_child_id, child_node)

    def _find_pattern(self, doc_graphs: list) -> dict[int, list[TreeNode]]:
        """
        Search for the required pattern.

        Args:
            doc_graphs (list): A list of graphs for the document

        Returns:
            dict[int, list[TreeNode]]: A dictionary with pattern matches
        """
        target_graph = self._make_target_graph()
        graph_mathces = {}
        for graph_id, graph in enumerate(doc_graphs):
            matcher = DiGraphMatcher(
                graph,
                target_graph,
                node_match=lambda node_1, node_2: node_1["label"] == node_2["label"],
            )
            matched_trees = []
            for match_dict in matcher.subgraph_isomorphisms_iter():
                head_id = int(next(iter(match_dict)))
                head_node = TreeNode(
                        graph.nodes[head_id]["label"],
                        graph.nodes[head_id]["text"],
                        []
                    )
                matched_trees.append(head_node)
                self._add_children(graph, match_dict, head_id, head_node)

            if matched_trees:
                graph_mathces[graph_id] = matched_trees

        return graph_mathces

    def _unpack_tree(self, tree_node: TreeNode) -> dict:
        """
        Unpacks TreeNode instance to dict

        Args:
            tree_node (TreeNode): Filled instance of TreeNode.

        Returns:
            dict: A dictionary whose keys are attributes of input TreeNode instance.
        """
        return {
            "upos": tree_node.upos,
            "text": tree_node.text,
            "children": [self._unpack_tree(child) for child in tree_node.children]
        }

    def run(self) -> None:
        """
        Search for a pattern in documents and writes found information to JSON file.
        """
        for article in self._corpus.get_articles().values():
            article_doc = self._make_graphs(self._analyzer.from_conllu(article))
            patterns = self._find_pattern(article_doc)
            patterns_info_dict = {}
            for graph_id, matched_trees in patterns.items():
                patterns_info_dict[graph_id] = [self._unpack_tree(tree) for tree in matched_trees]
            article.set_patterns_info(patterns_info_dict)
            to_meta(article)


def main() -> None:
    """
    Entrypoint for pipeline module.
    """
    corpus_manager = CorpusManager(ASSETS_PATH)
    udpipe_analyzer = UDPipeAnalyzer()
    pipeline = TextProcessingPipeline(corpus_manager, udpipe_analyzer)
    pipeline.run()
    pos_pipeline = POSFrequencyPipeline(corpus_manager, udpipe_analyzer)
    pos_pipeline.run()
    pattern_searcher = PatternSearchPipeline(
        corpus_manager,
        udpipe_analyzer,
        ("VERB", "NOUN", "ADP")
    )
    pattern_searcher.run()


if __name__ == "__main__":
    main()