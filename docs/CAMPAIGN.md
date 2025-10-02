# Campaign Primitive

A Campaign is a new primitive in `cocli` designed to manage marketing and data enrichment initiatives. It encapsulates a set of related activities aimed at a specific cohort of companies or people.

## Campaign Structure

A campaign is represented by a directory within the `campaigns` directory. The directory name is the slug of the campaign name. For example, a campaign named "Turboship Q3 2025" would be located at `campaigns/2025/turboship-q3-2025`.

Each campaign directory will contain:

*   `README.md`: A description of the campaign, its goals, and the initiatives it entails.
*   `data/`: A directory for storing raw and processed data related to the campaign. This could include scraped data, enriched data, and analysis results.
*   `config.toml`: A configuration file for the campaign, specifying details like the campaign name, the source of the data, and the enrichment steps to be applied.
*   `initiatives/`: A directory containing scripts or definitions for the various initiatives within the campaign.

## Campaign Lifecycle

1.  **Creation**: A new campaign is created with a `cocli campaign new` command. This will create the directory structure and a default `config.toml` and `README.md`.
2.  **Ingestion**: Data is ingested into the campaign from a specified source. This could be a CSV file, a database query, or another data source. The ingested data is stored in the `data/raw` directory.
3.  **Enrichment**: The ingested data is enriched with additional information. This can involve running various enrichment scripts, such as Google Maps searches, website scraping, and data cleaning. The enriched data is stored in the `data/processed` directory.
4.  **Analysis**: The enriched data is analyzed to generate insights and achieve the campaign's goals. This could involve generating reports, creating visualizations, or building models.
5.  **Action**: The insights from the analysis are used to take action, such as generating new leads, targeting specific customer segments, or identifying new market opportunities.

## Campaign Initiatives

An initiative is a specific action or set of actions taken as part of a campaign. Examples of initiatives include:

*   **Data Ingestion**: Importing data from a specific source.
*   **Enrichment**: Applying a specific enrichment process to the data.
*   **Analysis**: Generating a specific report or visualization.
*   **Lead Generation**: Creating new leads based on the campaign's findings.

Each initiative will be defined in a file within the `initiatives/` directory. This will allow for a modular and extensible approach to defining campaign workflows.
