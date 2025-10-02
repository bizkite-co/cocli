# cocli Help

`cocli` is a tool for managing your plain-text CRM.

## USAGE

`cocli <command>`

---

## COMMANDS

`add -c "Name;domain.com;Type" -p "FullName;email@domain.com;Phone"`
:   Adds a new company and/or person. All fields inside the quotes are required, separated by semicolons.
    - Creates the company if it doesn't exist.
    - Creates the person if they don't exist.
    - Associates the person with the company.

`find`
:   Fuzzy-search for any file (contact, meeting note, etc.) across all companies and open the selection in your default editor.

`import <format> <filepath>`
:   Imports companies from a specified file using the given format.
    Example: `cocli import google-maps ./leads.csv`

`help`
:   Displays this help message.
