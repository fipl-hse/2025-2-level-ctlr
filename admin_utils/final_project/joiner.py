"""
Private module that describes how students join all text files in one.
"""

import sys
from pathlib import Path

from quality_control.console_logging import get_child_logger

logger = get_child_logger(__file__)


def main() -> None:
    """
    Module entrypoint.
    """
    res_root = Path(__file__).parent.parent.parent / "data" / "result"
    if not res_root.exists():
        res_root.mkdir(exist_ok=True)

    gold_root = Path(__file__).parent.parent.parent / "data" / "gold"
    if not gold_root.exists():
        logger.error("Gold path does not exist. Create first.")
        sys.exit(1)

    for idx, author in enumerate(sorted(gold_root.iterdir())):
        if not author.is_dir():
            logger.info(f"Ignoring {author.name}...")
            continue
        txt_paths = sorted(author.glob("*.txt"))

        contents = []
        for txt_path in txt_paths:
            with txt_path.open(encoding="utf-8") as file:
                contents.append(file.read())

        total_file_path = res_root / author.name / "total.txt"
        (res_root / author.name).mkdir(exist_ok=True)
        with total_file_path.open("w", encoding="utf-8") as file:
            file.write("\n\n".join(contents))

        logger.info(f"{idx+1} {author.name:<20} success")


if __name__ == "__main__":
    main()
