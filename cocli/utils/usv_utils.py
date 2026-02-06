import csv
from typing import List, Iterable, Iterator, Any, Dict, Optional

# Unit Separator (US) - used for fields
UNIT_SEPARATOR = "\x1f"
# Record Separator - using standard newline for broad tool compatibility
RECORD_SEPARATOR = "\n"

class USVReader:
    """
    A reader for Unit Separated Values (USV).
    Uses \x1f for fields and \n for records.
    """
    def __init__(self, f: Iterable[str]):
        self.f = f
        self._iterator = iter(f)

    def __iter__(self) -> Iterator[List[str]]:
        for line in self._iterator:
            # Strip RS and Newline
            clean_line = line.strip("\x1e\n")
            if clean_line:
                yield clean_line.split(UNIT_SEPARATOR)

    def __next__(self) -> List[str]:
        return next(iter(self))

class USVDictReader:
    """
    A DictReader for USV.
    """
    def __init__(self, f: Iterable[str], fieldnames: Optional[List[str]] = None):
        self.reader = USVReader(f)
        self.fieldnames = fieldnames
        self._first_row_read = False
        self._gen = self._get_gen()

    def _get_gen(self) -> Iterator[Dict[str, str]]:
        for row in self.reader:
            if not self._first_row_read:
                if self.fieldnames is None:
                    self.fieldnames = row
                    self._first_row_read = True
                    continue
                self._first_row_read = True
            
            if self.fieldnames is not None:
                yield dict(zip(self.fieldnames, row))

    def __iter__(self) -> Iterator[Dict[str, str]]:
        return self

    def __next__(self) -> Dict[str, str]:
        return next(self._gen)

class USVWriter:
    """
    A writer for Unit Separated Values (USV).
    """
    def __init__(self, f: Any):
        self.f = f

    def writerow(self, row: Iterable[Any]) -> None:
        line = UNIT_SEPARATOR.join(str(item) if item is not None else "" for item in row)
        self.f.write(line + RECORD_SEPARATOR)

class USVDictWriter:
    """
    A DictWriter for USV.
    """
    def __init__(self, f: Any, fieldnames: List[str]):
        self.f = f
        self.fieldnames = fieldnames
        self.writer = USVWriter(f)

    def writeheader(self) -> None:
        self.writer.writerow(self.fieldnames)

    def writerow(self, rowdict: Dict[str, Any]) -> None:
        row = [rowdict.get(key, "") for key in self.fieldnames]
        self.writer.writerow(row)

def csv_to_usv(csv_path: str, usv_path: str) -> None:
    """Utility to convert a standard CSV to USV."""
    with open(csv_path, 'r', encoding='utf-8') as f_in:
        reader = csv.reader(f_in)
        with open(usv_path, 'w', encoding='utf-8') as f_out:
            writer = USVWriter(f_out)
            for row in reader:
                writer.writerow(row)

def usv_to_csv(usv_path: str, csv_path: str) -> None:
    """Utility to convert USV to standard CSV."""
    with open(usv_path, 'r', encoding='utf-8') as f_in:
        reader = USVReader(f_in)
        with open(csv_path, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.writer(f_out)
            for row in reader:
                writer.writerow(row)
