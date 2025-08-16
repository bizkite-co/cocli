Feature: Company and Person Finding

  As a cocli user
  I want to easily find information about companies and people
  So that I can quickly access relevant details

  Scenario: User invokes find with no companies
    Given a cocli data directory with no companies
    When the user runs "cocli find"
    Then the command should exit with an error
    And the output should indicate "No companies found."

  Scenario: User invokes find with a query that has a single strong match
    Given a cocli data directory with a company named "Acme Corp"
    When the user runs "cocli find Acme"
    Then the command should exit successfully
    And the output should indicate "Found best match: Acme Corp"
    And the output should display details for "Acme Corp"

  Scenario: User invokes find with a query that has multiple strong matches and selects one
    Given a cocli data directory with companies "Acme Corp" and "Acme Solutions"
    When the user runs "cocli find Acme" and selects "1"
    Then the command should exit successfully
    And the output should indicate "Multiple strong matches found for 'Acme':"
    And the output should display "1. Acme Corp"
    And the output should display "2. Acme Solutions"
    And the output should display details for "Acme Corp"

  Scenario: User invokes find with no query and selects a company by number
    Given a cocli data directory with companies "Acme Corp" and "Beta Inc"
    When the user runs "cocli find" and selects "2"
    Then the command should exit successfully
    And the output should indicate "Available companies:"
    And the output should display "1. Acme Corp"
    And the output should display "2. Beta Inc"
    And the output should display details for "Beta Inc"

  Scenario: User invokes find with no query and selects a company by name
    Given a cocli data directory with companies "Acme Corp" and "Beta Inc"
    When the user runs "cocli find" and selects "Beta Inc"
    Then the command should exit successfully
    And the output should indicate "Available companies:"
    And the output should display "1. Acme Corp"
    And the output should display "2. Beta Inc"
    And the output should display details for "Beta Inc"

  Scenario: User invokes find with an invalid selection during interactive mode
    Given a cocli data directory with companies "Acme Corp" and "Beta Inc"
    When the user runs "cocli find" and enters "invalid" then "1"
    Then the command should exit successfully
    And the output should indicate "Invalid selection. Please try again."
    And the output should display details for "Acme Corp"

  Scenario: User invokes find for a company with _index.md, tags.lst, and recent meetings
    Given a cocli data directory with a company named "Example Corp"
    And "Example Corp" has an _index.md file with YAML frontmatter and markdown content
    And "Example Corp" has a tags.lst file with tags "tech, software"
    And "Example Corp" has recent meetings within the last 6 months
    When the user runs "cocli find Example Corp"
    Then the command should exit successfully
    And the output should display "--- Company Details ---"
    And the output should display "--- Tags ---"
    And the output should display "tech, software"
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

  Scenario: User invokes find for a company with no tags.lst
    Given a cocli data directory with a company named "NoTags Corp"
    And "NoTags Corp" has no tags.lst file
    When the user runs "cocli find NoTags Corp"
    Then the command should exit successfully
    And the output should indicate "No tags found."

  Scenario: User invokes find for a company with no recent meetings
    Given a cocli data directory with a company named "NoMeetings Corp"
    And "NoMeetings Corp" has no recent meetings within the last 6 months
    When the user runs "cocli find NoMeetings Corp"
    Then the command should exit successfully
    And the output should indicate "No recent meetings found."