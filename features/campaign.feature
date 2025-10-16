Feature: Campaign Management

  As a cocli user
  I want to be able to create and manage campaigns

  Scenario: User creates a new campaign
    Given a cocli data directory
    When the user runs "cocli campaign add 'My Test Campaign' 'My Test Company'"
    Then the command should exit successfully
    And a directory for the campaign "my-test-campaign" should exist in the campaigns folder
    And a "config.toml" file should exist in the campaign directory "my-test-campaign"
    And the "config.toml" file in the campaign directory "my-test-campaign" should contain 'name = "My Test Campaign"'
    And the "config.toml" file in the campaign directory "my-test-campaign" should contain 'company-slug = "my-test-company"'
