"""
Tests for final project implementation.
"""

import shutil
from pathlib import Path
from typing import Generator

import pytest

import final_project.main as main_module
from admin_utils.final_project.checker import check_via_official_validator


@pytest.fixture(scope="function")
def final_project_setup(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Set up test environment for final project and clean up after test.

    Args:
        tmp_path (Path): Pytest temporary path fixture.

    Yields:
        Path: Path to generated auto_annotated.conllu.
    """
    assets_path = tmp_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)

    dist_path = tmp_path / "dist"
    dist_path.mkdir(parents=True, exist_ok=True)

    test_files_dir = Path(__file__).parent / "test_files"
    txt_files = list(test_files_dir.glob("*.txt"))

    if not txt_files:
        pytest.skip("No test txt files found in test_files directory")

    for txt_file in txt_files:
        shutil.copy(txt_file, assets_path / txt_file.name)

    main_module.main(corpus_path=assets_path, dist_path=dist_path)

    conllu_path = dist_path / "auto_annotated.conllu"

    yield conllu_path

    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.mark4
@pytest.mark.mark6
@pytest.mark.mark8
@pytest.mark.mark10
@pytest.mark.final_project
def test_main_generates_valid_conllu(final_project_setup: Path) -> None:
    """
    Ensure main() generates valid CoNLL-U file.

    Args:
        final_project_setup (Path): Fixture providing path to generated conllu file.
    """
    conllu_path = final_project_setup

    assert conllu_path.exists(), f"auto_annotated.conllu was not created at {conllu_path}"

    assert conllu_path.stat().st_size > 0, "Generated conllu file is empty"

    _, _, return_code = check_via_official_validator(conllu_path)

    assert return_code == 0, "Generated conllu file failed validation"


@pytest.mark.mark4
@pytest.mark.mark6
@pytest.mark.mark8
@pytest.mark.mark10
@pytest.mark.final_project
def test_main_creates_file_in_correct_location(final_project_setup: Path) -> None:
    """
    Ensure main() creates auto_annotated.conllu in dist folder.

    Args:
        final_project_setup (Path): Fixture providing path to generated conllu file.
    """
    conllu_path = final_project_setup

    assert conllu_path.exists(), f"auto_annotated.conllu was not created at {conllu_path}"

    assert (
        conllu_path.name == "auto_annotated.conllu"
    ), f"Expected filename auto_annotated.conllu, but got {conllu_path.name}"
