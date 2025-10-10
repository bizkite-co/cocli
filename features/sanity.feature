Feature: Sanity Check

  Scenario: Basic addition
    Given I have a number <a>
    And I have another number <b>
    When I add them together
    Then the result should be <c>

    Examples:
      | a | b | c |
      | 1 | 2 | 3 |
      | 5 | 7 | 12 |
