We are going to be migrating some of our workflow code to `transitions`. We've already done some of it. Our code is using Pydantic and `mypy` to establish a semantics of model transformations for our ETL and campaign workflows. So, we are trying to think of every step and the larger phases of the workflows as a transformation from one object type to another object type, such as a input CSV to an enriched directory structure. This will drive us to clearly define data structures and plan work as kinds of map-transform flows.

Right now, we need to update our logging. We have a whole bunch of stuff like this:

```
cocli/commands/deduplicate.py
21:        print("Companies directory does not exist.")
36:                print(f"Error parsing YAML in {company_file}: {e}")
39:        print("No companies found to deduplicate.")
50:        print("No duplicates found.")
53:    print(f"Found {len(duplicates)} duplicate records.")
56:        print("Dry run enabled. The following duplicates were found:")
57:        print(duplicates.sort_values('hash_id'))
59:        print("Writing changes is not yet implemented.")

cocli/scrapers/google_maps_parsers/extract_name.py
15:        if debug: print(f"Debug: Extracted Name (aria-label): {name}")
22:        if debug: print(f"Debug: Extracted Name (innerText): {name}")
28:            if debug: print(f"Debug: Extracted Name (HTML fallback): {name}")
30:            if debug: print("Debug: Name element not found.")
```

But we have also started to do this:

```
1:import logging
52:    logging.basicConfig(filename='temp/view_company.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
53:    logging.debug(f"Starting _interactive_view_company for {company_name}")
55:    logging.info(f"companies_dir: {companies_dir}")
57:    logging.info(f"company_slug: {company_slug}")
59:    logging.info(f"selected_company_dir: {selected_company_dir}")
75:    logging.debug("Calling Company.from_directory")
```

I would like to move everything towards the second examples by using a modern and robust and professional and production-ready standardized logging on an application-wide range, but I thought it might also be a good time to consider a possible CQRS event sourcing for troubleshooting ETL history, etc. I'm wondering if there is a way to standardize the transform logging in such a way that we could trace the data back to it's source to better understand and troubleshoot data integrity problems.
