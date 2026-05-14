"""
Tests for PatternSearchPipeline.
"""

import json
import shutil
import unittest

import pytest

from admin_utils.test_params import PIPE_TEST_FILES_FOLDER, TEST_PATH
from core_utils.article import article
from lab_6_pipeline import pipeline
from lab_6_pipeline.pipeline import CorpusManager, PatternSearchPipeline, UDPipeAnalyzer
from lab_6_pipeline.tests.utils import pipeline_test_files_setup


def depth_counter(pattern_dict: dict) -> int:
    """
    Function to check the depth of the pattern matches structure.

    Args:
        pattern_dict (dict): A dictionary with one sentence pattern

    Returns:
        int: A depth of the dictionary
    """
    if isinstance(pattern_dict, dict):
        child_depths = [depth_counter(child) for child in pattern_dict["children"]]
        if not child_depths:
            return 1
        max_depth = max(child_depths)
        return 1 + max_depth
    return 0


class PatternSearchPipelineTests(unittest.TestCase):
    """
    Tests for PatternSearchPipeline realization.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Define start instructions for PatternSearchPipelineTests class.
        """
        pipeline_test_files_setup(number_of_files=2)
        shutil.copyfile(
            PIPE_TEST_FILES_FOLDER / "reference_udpipe_test.conllu",
            TEST_PATH / "1_udpipe.conllu",
        )
        shutil.copyfile(
            PIPE_TEST_FILES_FOLDER / "2_udpipe.conllu",
            TEST_PATH / "2_udpipe.conllu",
        )

        article.ASSETS_PATH = TEST_PATH
        pipeline.ASSETS_PATH = TEST_PATH

        cls.corpus_manager = CorpusManager(path_to_raw_txt_data=TEST_PATH)
        cls.patterns = []
        for one_article in cls.corpus_manager.get_articles().values():
            path = one_article.get_meta_file_path()
            with open(path, "r", encoding="utf-8") as meta_file:
                meta = json.load(meta_file)
            print(f"File: {one_article.article_id}")
            print("Meta data:", meta)
            cls.patterns.append(meta.pop("pattern_matches"))
            print("Patterns:", cls.patterns)
            with open(path, "w", encoding="utf-8") as meta_file:
                json.dump(
                    meta,
                    meta_file,
                    sort_keys=False,
                    indent=4,
                    ensure_ascii=False,
                    separators=(",", ": "),
                )

        path_to_article = PIPE_TEST_FILES_FOLDER / "complex_pattern_matches.json"
        with open(path_to_article, "r", encoding="utf-8") as meta_file:
            cls.complex_patterns = json.load(meta_file)
        print(cls.complex_patterns)

        pattern_searcher = PatternSearchPipeline(
            cls.corpus_manager, UDPipeAnalyzer(), ("VERB", "NOUN", "ADP")
        )
        pattern_searcher.run()

    @pytest.mark.mark10
    @pytest.mark.stage_5_pattern_search_pipeline_checks
    @pytest.mark.lab_6_pipeline
    def test_patterns_are_dict(self) -> None:
        """
        Ensure patterns are matched correctly.
        """
        one_article = self.corpus_manager.get_articles()[1]
        path = one_article.get_meta_file_path()
        print(path)
        with open(path, "r", encoding="utf-8") as meta_file:
            patterns = json.load(meta_file)["pattern_matches"]
        print(self.patterns[0])
        print(patterns)
        self.assertIsInstance(patterns, dict)
        self.assertEqual(self.patterns[0], patterns, "Patterns were found incorrectly")

    @pytest.mark.mark10
    @pytest.mark.stage_5_pattern_search_pipeline_checks
    @pytest.mark.lab_6_pipeline
    def test_json_structure_depth(self) -> None:
        """
        Ensure the json structure has exact structure.
        """
        one_article = self.corpus_manager.get_articles()[2]
        path = one_article.get_meta_file_path()
        print(path)
        with open(path, "r", encoding="utf-8") as meta_file:
            patterns = json.load(meta_file)["pattern_matches"]
        for sentence_patterns in patterns.values():
            for pattern in sentence_patterns:
                self.assertEqual(depth_counter(pattern), 3)

    @pytest.mark.mark10
    @pytest.mark.stage_5_pattern_search_pipeline_checks
    @pytest.mark.lab_6_pipeline
    def test_complex_patterns_are_correct(self) -> None:
        """
        Ensure the output of complex structure follows one of the templates.
        """
        one_article = self.corpus_manager.get_articles()[2]
        path = one_article.get_meta_file_path()
        print(path)
        with open(path, "r", encoding="utf-8") as meta_file:
            patterns = json.load(meta_file)["pattern_matches"]

        matched = [
            patterns == match_pattern for match_pattern in self.complex_patterns["Match cases"]
        ]
        print(matched)
        self.assertTrue(max(matched))

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Define final instructions for PatternSearchPipelineTests class.
        """
        shutil.rmtree(TEST_PATH)
