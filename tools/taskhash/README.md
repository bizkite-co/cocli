# TaskHash

A portable, zero-dependency tool for code signature hashing and task bypass. It helps prevent redundant execution of long-running tasks (like linting or testing) by only running them when relevant source files have changed.

## Features

- **Portable**: Compiled Go binary works on Linux, macOS, and Windows.
- **Configurable**: Define what to include or exclude in a simple `taskhash.json` file.
- **Task-aware**: Tracks separate signatures for different tasks (e.g., `lint`, `test`, `build`).
- **PowerShell Friendly**: Easy to integrate into Windows CI/CD pipelines.

## Configuration (`taskhash.json`)

```json
{
  "includes": ["src", "Makefile"],
  "excludes": [".git", "dist", "docs", ".code_signatures.json"],
  "store": ".code_signatures.json"
}
```

## Usage

### Check if task should run
```bash
taskhash --task lint --check
if [ $? -ne 0 ]; then
  # Run lint command
  taskhash --task lint --update
fi
```

### PowerShell Example
```powershell
./taskhash.exe --task lint --check
if ($LASTEXITCODE -ne 0) {
    # Run lint command
    ./taskhash.exe --task lint --update
}
```

## Compilation

```bash
go build -o taskhash taskhash.go
```
