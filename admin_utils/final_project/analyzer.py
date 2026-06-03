"""
Private module that describes student typical solution for the final project.
"""

# pylint: disable=protected-access
import sys
from pathlib import Path

from quality_control.console_logging import get_child_logger
from tqdm import tqdm

from lab_6_pipeline.pipeline import UDPipeAnalyzer

logger = get_child_logger(__file__)


def main() -> None:
    """
    Module entrypoint.
    """
    gold_root = Path(__file__).parent.parent.parent / "data" / "result"
    if not gold_root.exists():
        gold_root.mkdir(exist_ok=True)

    for author in tqdm(sorted(gold_root.iterdir()), total=len(list(gold_root.iterdir()))):
        if not author.is_dir():
            logger.info(f"Ignoring {author.name}...")
            continue
        txt_path = author / "total.txt"
        if not txt_path.exists():
            logger.info("Total file is not present. Generate first.")
            sys.exit(1)
        conllu_path = author / "total.conllu"

        with txt_path.open(encoding="utf-8") as file:
            content = file.read()

        analyzer = UDPipeAnalyzer()
        res = analyzer._analyzer(content)

        with conllu_path.open("w", encoding="utf-8") as f:
            f.write(res._.conll_str)
            f.write("\n")


if __name__ == "__main__":
    main()
