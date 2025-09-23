We have a @cocli/scrapers/myip_ms.py that scrapes a bunch of Shopify websites by their CIDR blocks because they are domains hosted on Shopfiy servers. It puts the domain names, IP addresses, popularity, and scraped date into a file like `/home/mstouffer/.local/share/cocli_data/scraped_data/shopify_csv/shopify-myip-ms-23-227-38-32-20250921184518.csv.


```
❯ head shopify-myip-ms-23-227-38-32-20250921184518.csv
id,Website,IP_Address,Popularity_Visitors_Per_Day,Country,Uuid,Scrape_Date
acb77ff0-e02c-4007-a227-07c0190c616f,/view/sites/16861/jbhifi.com.au,23.227.38.32,"73,000",Canada,422c41ec-e251-42
c4-b8af-aaa1b26f1159,2025-09-21T18:46:12.414658
5488ec13-c0b2-407a-8458-8f0d9f02ec32,/view/sites/9647328/pagefly.io,23.227.38.32,"36,100",Canada,78726734-9c95-4c4
5-9987-7a6b44354aad,2025-09-21T18:46:12.416619
d9d36e06-4408-4d62-821d-196b979dd6b4,/view/sites/20817850/snitch.co.in,23.227.38.32,"24,600",Canada,93119202-8090-
4fed-8b0b-6dfc1e89c7e4,2025-09-21T18:46:12.419304
```

That data needs to be compiled into a useful `index.csv` in the same directory. The domain name should be cleaned up, and we only need the domain, visits_per_day, and scraped date. The compiler should search through all files in the directory that aren't the `index.csv` and dedupe output that gets put into the `index.csv`.

At that point we will have a deduped list of Shopify sites. Then, we need to enrich the data and put it into the company data in `$HOME/.local/share/cocli_data/companies`

The company folders in that directory can look like this:

```
├── express-photo-studio
│   ├── _index.md
│   ├── contacts
│   ├── meetings
│   │   ├── 2025-08-23-cold-call.md
│   │   └── 2025-08-24T0335Z-cold-call-about-image-annex.md
│   └── tags.lst
```

We need to follow that same structure.

We will add an `enrichments` subfolder and create a `website.md` in that folder as we enrich each company folder.

We will loop through the `index.csv` and use the proper web browser tools to read the website and navigate to any "Contact Us" or "About Us" or similar pages on the website to find address location, email addresses, phone numbers, social media links, personnel name and contact info. etc.

We already have a @cocli/enrichment/website_scraper.py , but we haven't created a Pydantic type for the website yet. We should try to use Pydantic to make sure we are using the same names and types for data everywhere. We have a @cocli/models/company.py and a @cocli/commands/meetings.py models, but we should create more for consistency.  For instance I think we should probably implement the company folder structure as a Pydantic model so that we know the folder structure whenever we read or write to the company folders.

We well end up taking the website scraped data and enriching the `_index.md` and `contacts/` in the company folder. There is a `create_company_files()` and a `slugify()` to create the folder structure and make the company name slug consistent. Those are both in the @cocli/utils/ .

This is part of the @docs/issues/shopify-cidr-blocks/_index.md issue, so read that and the @docs/issues/shopify-cidr-blocks/plan.md and update them to reflect this new part of the issue.

Be thorough in the documentation so that we can return to this issue at a later date and time and have the full context.