Feature: Company and Person Finding

  As a cocli user
  I want to easily find information about companies and people
  So that I can quickly access relevant details

  Scenario: User invokes find with no query
    Given a cocli data directory with no companies
    When the user runs "cocli find"
    Then the command should exit successfully
    And the output should display find help

  Scenario: User invokes find with no query but has companies
    Given a cocli data directory with companies "Acme Corp", "Beta Inc"
    When the user runs "cocli find" and interactively selects "Acme Corp" using arrow keys
    Then the command should exit successfully
    And the output should display a selectable list containing "Acme Corp", "Beta Inc"
    And the output should display details for "Acme Corp"

  Scenario: User invokes find with a query that has a single strong match
    Given a cocli data directory with a company named "Acme Corp"
    When the user runs "cocli find Acme"
    Then the command should exit successfully
    And the output should indicate "Found best match: Acme Corp"
    And the output should display details for "Acme Corp"

  Scenario: User invokes find with a query that has multiple strong matches and selects one
    Given a cocli data directory with companies "Acme Corp", "Acme Solutions"
    When the user runs "cocli find Acme" and interactively selects "Acme Corp" using arrow keys

    Then the output should display a selectable list containing "Acme Corp", "Acme Solutions"

  Scenario: User invokes find for a company with _index.md, tags.lst, and recent meetings
    Given a cocli data directory with a company named "Example Corp"
    And "Example Corp" has an _index.md file with YAML frontmatter and markdown content
    And "Example Corp" has a tags.lst file with tags "tech, software"
    And "Example Corp" has recent meetings within the last 6 months
    And the user selects "Example Corp" from the find selection list

    Then the output should display "--- Company Details ---"
    And the output should display "--- Tags ---"
    And the output should display tags "tech, software"
    And the output should display "--- Recent Meetings ---"
    And the output should display recent meeting dates and names
    And the output should display "To view all meetings: cocli view-meetings Example Corp"
    And the output should display "To add a new meeting: cocli add-meeting Example Corp"

  Scenario: User invokes find for a company with no _index.md
    Given a cocli data directory with a company named "NoIndex Corp"
    And "NoIndex Corp" has no _index.md file
    When the user runs "cocli find NoIndex Corp"
    Then the command should exit successfully
    And the output should indicate "No _index.md found for NoIndex Corp."


  Scenario: User invokes find with multiple matches and interactively selects one with arrow keys
    Given a cocli data directory with companies "Alpha Corp", "Beta Inc", "Gamma Ltd"
    When the user runs "cocli find A" and interactively selects "Alpha Corp" using arrow keys
    Then the command should exit successfully
    And the output should display a selectable list containing "Alpha Corp", "Beta Inc", "Gamma Ltd"
    And the output should display details for "Alpha Corp"

  Scenario: User invokes find with multiple matches and interactively selects one with VIM keys
    Given a cocli data directory with companies "Alpha Corp", "Beta Inc", "Gamma Ltd"
    When the user runs "cocli find B" and interactively selects "Beta Inc" using 'j' key
    Then the command should exit successfully
    And the output should display a selectable list containing "Alpha Corp", "Beta Inc", "Gamma Ltd"
    And the output should display details for "Beta Inc"

