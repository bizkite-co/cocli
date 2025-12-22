Feature: CLI Help Output

  As a cocli user
  I want to see the help message when I run cocli with no arguments
  So that I can understand available commands and options

  Scenario: Display help when no arguments are provided
    When the user runs "cocli" with no arguments
    Then the command should exit with an error
    And the output should contain "Usage:"
    And the output should contain "Commands"
    And the output should contain "add"
    And the output should contain "add-email"
    And the output should contain "add-meeting"
    And the output should contain "context"
    And the output should contain "exclude"
    And the output should contain "fz"
    And the output should contain "import-customers"
    And the output should contain "import-data"
    And the output should contain "init"
    And the output should contain "next"
    And the output should contain "open-company-folder"
    And the output should contain "status"
    And the output should contain "sync"
    And the output should contain "view-company"
    And the output should contain "view-meetings"
    And the output should contain "enrich-customers"
    And the output should contain "enrich-shopify-data"
    And the output should contain "compile-enrichment"
    And the output should contain "flag-email-providers"
    And the output should contain "enrich"
    And the output should contain "query"
    And the output should contain "campaign"
    And the output should contain "deduplicate"
    And the output should contain "render"