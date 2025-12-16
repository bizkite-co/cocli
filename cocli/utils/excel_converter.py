from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

def convert_xlsx_to_csv(xlsx_filepath: Path, output_dir: Path) -> Path:
    """
    Converts an XLSX file to a CSV file.

    Args:
        xlsx_filepath: The path to the input XLSX file.
        output_dir: The directory where the CSV file will be saved.

    Returns:
        The path to the newly created CSV file.
    """
    import pandas as pd # Lazy import
    
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_filename = xlsx_filepath.stem + ".csv"
    csv_filepath = output_dir / csv_filename

    df = pd.read_excel(xlsx_filepath)
    df.to_csv(csv_filepath, index=False)

    return csv_filepath

def convert_all_xlsx_in_directory(source_dir: Path, output_dir: Path) -> None:
    """
    Converts all XLSX files in a source directory to CSV, saving them in an output directory.
    Only converts if the corresponding CSV file does not already exist.

    Args:
        source_dir: The directory containing the XLSX files.
        output_dir: The directory where the CSV files will be saved.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Checking for XLSX files in: {source_dir}")
    for xlsx_file in source_dir.glob("*.xlsx"):
        csv_filename = xlsx_file.stem + ".csv"
        csv_filepath = output_dir / csv_filename

        if csv_filepath.exists():
            logger.info(f"Skipping '{xlsx_file.name}': '{csv_filename}' already exists.")
        else:
            logger.info(f"Converting '{xlsx_file.name}' to '{csv_filename}'...")
            try:
                convert_xlsx_to_csv(xlsx_file, output_dir)
                logger.info(f"Successfully converted '{xlsx_file.name}'.")
            except Exception as e:
                logger.error(f"Error converting '{xlsx_file.name}': {e}")

if __name__ == "__main__":
    # Example usage for converting real XLSX files
    source_folder = Path("./docs/issues/shopify-cidr-blocks/lists")
    target_output_folder = Path("./scraped_data/shopify_csv")
    
    convert_all_xlsx_in_directory(source_folder, target_output_folder)

    # Clean up dummy file if it exists from previous run
    dummy_csv_path = Path("./scraped_data/shopify_csv/dummy.csv")
    if dummy_csv_path.exists():
        os.remove(dummy_csv_path)
        logger.info(f"Cleaned up dummy CSV: {dummy_csv_path}")
    dummy_xlsx_path = Path("./test_data/dummy.xlsx")
    if dummy_xlsx_path.exists():
        os.remove(dummy_xlsx_path)
        logger.info(f"Cleaned up dummy XLSX: {dummy_xlsx_path}")