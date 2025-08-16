Feature: Git Synchronization and Committing

  As a cocli user
  I want to easily synchronize my data with a Git remote
  So that my data is version-controlled and backed up

  Scenario: User invokes git-sync with no changes
    Given a cocli data directory that is a Git repository
    And there are no pending changes in the data directory
    When the user runs "cocli git-sync"
    Then the command should exit successfully
    And the output should indicate "Already up to date."

  Scenario: User invokes git-commit with a message
    Given a cocli data directory that is a Git repository
    And there are pending changes in the data directory
    When the user runs "cocli git-commit --message 'Initial commit'"
    Then the command should exit successfully
    And the output should indicate "[main] Committed changes"
    And the changes should be committed to the Git repository

  Scenario: User invokes git-sync when data directory is not a Git repository
    Given a cocli data directory that is NOT a Git repository
    When the user runs "cocli git-sync"
    Then the command should exit with an error
    And the output should indicate "Error: Data directory"