Feature: Unified Data Ordinance
  As a Cocli Architect
  I want every data element to have a deterministic ordinant
  So that I can automate data propagation and role-based security

  Scenario: Resolving a Company Info Ordinant
    Given a company with slug "actus-advisors"
    When I access the field "phone_number"
    Then the system should map it to the file "companies/actus-advisors/_index.md"
    And the YAML key should be "phone_number"

  Scenario: Resolving a Note Ordinant
    Given a company with slug "actus-advisors"
    And a new note with title "Follow up"
    When I save the note
    Then it must be stored in "companies/actus-advisors/notes/"
    And the filename must contain the slugified title "follow-up"

  Scenario: Role-Based Enforcement
    Given a user with role "collector"
    When they attempt to update a note in "companies/actus-advisors/notes/"
    Then the system must deny the write operation
    And log a security violation
