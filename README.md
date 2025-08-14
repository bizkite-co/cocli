# Company CLI (cocli)

`cocli` is a simple, shell-based command-line interface for managing a plain-text CRM system located in `~/companies`.

## Installation

1.  Clone this repository.
2.  Add `~/repos/company-cli/bin` to your shell's `PATH`.

    ```bash
    export PATH="$HOME/repos/company-cli/bin:$PATH"
    ```

## Usage

To see the full list of commands and what they do, run:

```bash
cocli help
```

## Configuration

By default, `cocli` looks for your company files in `~/companies`.

To use a different directory, set the `COCLI_COMPANIES_DIR` environment variable in your `.bashrc` or `.zshrc` file. For example:

```bash
export COCLI_COMPANIES_DIR="$HOME/work/my-clients"
```
