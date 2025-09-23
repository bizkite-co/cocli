# Scrape Shopify Stores Using MyIp.ms

Use the [MyIp.ms](https://myip.ms/info/whois/23.227.38.74) to get lists of high traffic Shopify stores and enrich the company data.

```
23.227.38.32
23.227.38.36
23.227.38.65
23.227.38.74
```

## Next Steps

1.  **Compile Data:** Use the `process-shopify-scrapes` command to compile the raw scraped data into a deduplicated `index.csv` file.
2.  **Enrich Data:** Use the `enrich-shopify-data` command to process the `index.csv` file. This command will:
    *   Create a new company folder for each domain.
    *   Scrape the company's website for contact information, social media links, and other relevant data.
    *   Save the enriched data to `enrichments/website.md` within the company's folder.
    *   Update the company's `_index.md` with the new information.