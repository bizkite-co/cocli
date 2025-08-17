Feature: Google Maps Business Scraper

  As a user of cocli
  I want to scrape business information from Google Maps
  So that I can import it into my company database

  Scenario: Successfully scrape business data and generate Lead Sniper CSV
    Given a Google Maps search URL for "photography studio"
    And a temporary output directory for the CSV
    When I run the Google Maps scraper with the URL and keyword "photography studio"
    Then a CSV file named "lead-sniper-photography-studio-*.csv" should be created in the temporary directory
    And the CSV file should contain at least one business entry
    And the CSV file should have the Lead Sniper header
      | id | Keyword | Name | Full_Address | Street_Address | City | Zip | Municipality | State | Country | Timezone | Phone_1 | Phone_Standard_format | Phone_From_WEBSITE | Email_From_WEBSITE | Website | Domain | First_category | Second_category | Claimed_google_my_business | Reviews_count | Average_rating | Business_Status | Hours | Saturday | Sunday | Monday | Tuesday | Wednesday | Thursday | Friday | Latitude | Longitude | Coordinates | Plus_Code | Place_ID | Menu_Link | GMB_URL | CID | Google_Knowledge_URL | Kgmid | Image_URL | Favicon | Review_URL | Facebook_URL | Linkedin_URL | Instagram_URL | Meta_Description | Meta_Keywords | Uuid | Accessibility | Service_options | Amenities | From_the_business | Crowd | Planning |
    And the first business entry should have a "Name" and "Website"