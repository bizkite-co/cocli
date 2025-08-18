Feature: CLI Help Output

  As a cocli user
  I want to see the help message when I run cocli with no arguments
  So that I can understand available commands and options

  Scenario: Display help when no arguments are provided
    When the user runs "cocli" with no arguments
    Then the command should exit with an error
    And the output should contain "╭─ Error ─+╮"
    And the output should contain "Usage: cocli"
    And the output should contain "╭─ Commands ─+╮"
    And the output should contain "importer"
    And the output should contain "scrape"
    And the output should contain "add"
    And the output should contain "add-meeting"
    And the output should contain "find"
    And the output should contain "view-company"
    And the output should contain "view-meetings"
    And the output should contain "open-company-folder"
    And the output should contain "data-path"
    And the output should contain "git-sync"
    And the output should contain "git-commit"
    And the output should contain "Try 'cocli --help' for help."
