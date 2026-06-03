"""
Extract project team identifier from final_project lab settings.json.
"""

import argparse
from pathlib import Path

from quality_control.lab_settings import LabSettings


def get_project_team(lab_path: Path) -> int | None:
    """
    Get student's project_team value.

    Args:
        lab_path (Path): Path to lab.

    Returns:
        int: Student's final project team identifier.
    """
    settings = LabSettings(lab_path / "settings.json")
    return settings.parameters.ctlr.project_team


def main() -> None:
    """
    Module entrypoint.
    """
    parser = argparse.ArgumentParser(
        description="Extract project_team value from lab settings.json"
    )
    parser.add_argument(
        "--lab-path", type=str, required=True, help="Path to the lab containing settings.json"
    )
    args = parser.parse_args()
    lab_path = Path(args.lab_path)
    team_id = get_project_team(lab_path)
    print(team_id)


if __name__ == "__main__":
    main()
