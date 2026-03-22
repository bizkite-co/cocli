from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from cocli.core.paths import paths


def validate_all():
    results_dir = paths.campaign("roadmap").queue("gm-list").completed / "results"
    invalid_path = results_dir.parent / "results.invalid.usv"

    total_metrics = {"total": 0, "valid": 0, "invalid": 0}

    # Open global invalid file once
    with open(invalid_path, "w", encoding="utf-8") as f_invalid:
        for usv_file in results_dir.rglob("*.usv"):
            if usv_file.name in [
                "corrupted-records.usv",
                "compiled.usv",
                "results.invalid.usv",
            ]:
                continue

            print(f"Validating {usv_file}...")
            # We can't easily pass the open file handle to validate_file
            # with current implementation, so we'll do it manually

            # Re-implementing a simple validation loop here for clarity
            metrics = GoogleMapsListItem.validate_file(usv_file)

            # Accumulate
            for k in total_metrics:
                total_metrics[k] += metrics.get(k, 0)

            # If invalid, we need to extract them (re-doing validation is fine)
            if metrics["invalid"] > 0:
                with open(usv_file, "r", encoding="utf-8") as f:
                    for line in f:
                        is_valid, _, error = GoogleMapsListItem.validate_record(line)
                        if not is_valid:
                            f_invalid.write(
                                f"{line.strip()} | Error: {error} | File: {usv_file}\n"
                            )

    print("Validation complete.")
    print(f"Metrics: {total_metrics}")
    print(f"Invalid records written to: {invalid_path}")


if __name__ == "__main__":
    validate_all()
