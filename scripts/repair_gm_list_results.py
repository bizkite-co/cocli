from cocli.core.paths import paths
from cocli.core.constants import UNIT_SEP


def repair_and_validate():
    results_dir = paths.campaign("roadmap").queue("gm-list").completed / "results"

    for usv_file in results_dir.rglob("*.usv"):
        if usv_file.name in ["compiled.usv", "results.invalid.usv"]:
            continue

        repaired_lines = []
        with open(usv_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(UNIT_SEP)
                # If only 9 parts, assume category is missing (index 3)
                if len(parts) == 9:
                    parts.insert(3, "")
                repaired_lines.append(UNIT_SEP.join(parts) + "\n")

        with open(usv_file, "w", encoding="utf-8") as f:
            f.writelines(repaired_lines)

    print("Repaired all results files.")


if __name__ == "__main__":
    repair_and_validate()
