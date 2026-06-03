"""
Private module for cut of original corpus to given number of tokens.
"""

# pylint: disable=protected-access
import sys
from itertools import chain
from pathlib import Path

from quality_control.console_logging import get_child_logger

from lab_6_pipeline.pipeline import UDPipeAnalyzer

logger = get_child_logger(__file__)


def num_tokens_in(xml_path: Path) -> int:
    """
    Calculates number of tokens in a CONLLU file.
    """
    with xml_path.open(encoding="utf-8") as file:
        content = file.read().strip()
    analyzer = UDPipeAnalyzer()
    res = analyzer._analyzer(content)

    all_filtered = (
        filter(lambda token_info: token_info.get("UPOS") != "PUNCT", sentence._.conll)
        for sentence in res.doc.sents
    )
    all_tokens = list(chain.from_iterable(all_filtered))
    return len(all_tokens)


def process_author(author_path: Path, gold_path: Path, target_tokens_count: int) -> None:
    """
    Creates txt files from original corpus until number of tokens is not met.
    """
    paths_to_join = []
    total_tokens = 0
    for xml_path in sorted(author_path.glob("*.xml")):
        paths_to_join.append(xml_path)
        total_tokens += num_tokens_in(xml_path)

        target_path = gold_path / f"{xml_path.stem}.txt"
        with xml_path.open(encoding="utf-8") as file:
            content = file.read().strip()
        with target_path.open("w", encoding="utf-8") as file:
            file.write(content)

        logger.info(f"\t{xml_path.name:<20} running total:{total_tokens:>10}")

        if total_tokens > target_tokens_count:
            break


def main() -> None:
    """
    Module entrypoint.
    """
    xml_root = Path(__file__).parent.parent.parent / "data" / "original"
    if not xml_root.exists():
        logger.error("Error. Data directory does not exist!")
        sys.exit(1)

    gold_root = Path(__file__).parent.parent.parent / "data" / "gold"
    if not gold_root.exists():
        gold_root.mkdir(exist_ok=True)

    target_tokens_count = 2500

    for idx, author in enumerate(sorted(xml_root.iterdir())):
        if not author.is_dir():
            logger.info(f"Ignoring {author.name}...")
            continue
        xml_paths = sorted(author.glob("*.xml"))
        logger.info(f"{idx} {author.name:<20} total poems: {len(list(xml_paths)):>10}")

        author_dir = gold_root / author.name
        author_dir.mkdir(exist_ok=True)
        process_author(
            author_path=author, gold_path=author_dir, target_tokens_count=target_tokens_count
        )


if __name__ == "__main__":
    main()
