# Storage Model & Data Philosophy (Atomic USV)

The DFI uses the **Unicode Separated Values (USV)** protocol to ensure maximum robustness in a distributed environment.

## 1. Delimiter Protocol
To avoid the "delimiter collision" and "quoting overhead" of standard CSV, we use non-printable Unicode control characters as defined in RFC-adjacent modern standards:

| Separator | Character | Hex | Purpose |
| :--- | :--- | :--- | :--- |
| **Field** | Unit Separator (␟) | `\x1f` | Delimits columns (replaces comma/tab). |
| **Record** | Record Separator (␞) | `\x1e` | Delimits rows (replaces newline). |

### Advantages:
- **No Quoting**: Data containing commas, quotes, or semicolons can be stored raw.
- **Robust Parsers**: `awk`, `cut`, and `ripgrep` can use hex-defined delimiters for 100% reliable field extraction.
- **Zero-Byte Overhead**: No need for `"` characters around every field.

## 2. Reversible Dot-Based Naming
Files are named using `slugdotify` and the `.usv` extension:
- `indexes/domains/example.com.usv`

## 3. Directory Structure (Self-Documenting)
The index directory is a self-contained database:
```text
data/indexes/domains/
├── VERSION          # Schema version (e.g., "1")
├── _header.usv      # Column names delimited by \x1f
├── example.com.usv  # Single-row data delimited by \x1f
└── ...
```

## 4. Schema Evolution (Union-by-Name)
The system follows a **Schema-on-Read** unification strategy:
1. The reader identifies the number of `\x1f` separators.
2. If the count is lower than the current `_header.usv`, the reader projects `None` or default values for the missing trailing columns.
3. This allows Schema V1 and Schema V2 files to coexist in the same directory without breaking the pipeline.