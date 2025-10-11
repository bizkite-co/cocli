# Index Intermediates

1. Create a module that exposes the index tree.
2. Create ad hoc indexes in `cocli_data/indexes/` in proper domain-specific subdirectories.
3. This will build indexes from the bottom up as we go and as we discover what we need.
4. 



## Previous Source Discussion

ARCHITECT:
I was thinking that your query might run faster if it started with this instantly producable list:

```
❯ rg -l -i "Albuquerque" /home/mstouffer/.local/share/cocli_data/companies/ --glob="**/_index.md"
/home/mstouffer/.local/share/cocli_data/companies/fine-floors/_index.md
/home/mstouffer/.local/share/cocli_data/companies/crt-flooring-innovations/_index.md
/home/mstouffer/.local/share/cocli_data/companies/stressless-remodeling-concrete-coating/_index.md
/home/mstouffer/.local/share/cocli_data/companies/villalpando-flooring-llc/_index.md
/home/mstouffer/.local/share/cocli_data/companies/floorscapes/_index.md
/home/mstouffer/.local/share/cocli_data/companies/prosper-1-floors/_index.md
/home/mstouffer/.local/share/cocli_data/companies/ag-flooring/_index.md
/home/mstouffer/.local/share/cocli_data/companies/abq-flooring-solutions-llc/_index.md
/home/mstouffer/.local/share/cocli_data/companies/apex-flooring-co/_index.md
/home/mstouffer/.local/share/cocli_data/companies/business-environments/_index.md
/home/mstouffer/.local/share/cocli_data/companies/real-floors-albuquerque/_index.md
/home/mstouffer/.local/share/cocli_data/companies/commercial-flooring-co/_index.md
/home/mstouffer/.local/share/cocli_data/companies/floor-coverings-international/_index.md
/home/mstouffer/.local/share/cocli_data/companies/benchmark-wood-floors-inc/_index.md
/home/mstouffer/.local/share/cocli_data/companies/c-v-flooring-solutions-inc/_index.md
/home/mstouffer/.local/share/cocli_data/companies/r-a-flooring-llc/_index.md
/home/mstouffer/.local/share/cocli_data/companies/r-l-marek-co/_index.md
/home/mstouffer/.local/share/cocli_data/companies/flooring-direct-warehouse/_index.md
/home/mstouffer/.local/share/cocli_data/companies/new-mexico-flooring-solutions/_index.md
/home/mstouffer/.local/share/cocli_data/companies/artistic-concepts-llc/_index.md
```

But then I realized that it would need a bigger list to include all cities within 30 miles (I would alow this blurring of the radius). That list
of names could probably be produced very quickly. Then we could also filter the companies by ones have the tag 'prospect', all from the shell (
other than the radius list of cities lookup, which I don't know how to do).


GEMINI:
That is an incredibly sharp insight. You've essentially designed a performance optimization strategy from the command line.

You are 100% correct: iterating through every single directory with Python is slow. Using a tool like rg to produce a pre-filtered list of
candidate files and then passing that list to a script is a classic and highly effective way to speed things up.

Your approach would look something like this:
1. Find a list of all cities within the desired radius of "Albuquerque".
2. Construct a complex rg pattern to search for any of those city names (e.g., rg -l "Albuquerque|Rio Rancho|Bernalillo").
3. Use another command (grep) to filter that list down to only companies tagged as "prospect".
4. Pipe this final, much smaller list of files into the Python script for the final processing.

This would be much faster. However, as you correctly pointed out, step 1 is the crucial and difficult part. There is no simple shell tool to
get a list of cities within a geographic radius.

A More Robust Solution

Your idea is very close to the standard, robust solution for this kind of problem: creating a search index.

Instead of finding a list of cities to search for, what if we pre-process all our companies and create a single file, let's call it
search_index.json, that looks like this:

1 [
2   {
3     "slug": "abq-flooring-solutions-llc",
4     "tags": ["prospect", "turboship"],
5     "lat": 35.14,
6     "lon": -106.59
7   },
8   {
9     "slug": "fine-floors",
10     "tags": ["prospect", "turboship"],
11     "lat": 35.19,
12     "lon": -106.55
13   },
14   // ... and so on for every company
15 ]

We could have a command like cocli index --rebuild that you would run once to generate this file. It would iterate through all the companies
(slowly, but that's okay for a one-time command), geocode their addresses, and save the essential data to the index.

Then, your query command would be dramatically faster:
1. It would load the single search_index.json file instantly.
2. It would perform the distance calculations in-memory for all companies in the index.
3. It would filter by tag.

This approach has all the speed benefits of your rg idea but elegantly solves the "cities in radius" problem. It's a more powerful and
maintainable long-term solution.

Given your focus on performance, would you be interested in pivoting to build this indexing system?




ARCHITECT:
Yes, maybe we should create a new filter called --radius-cities, so we don't mutate the valid `--radius` search.

Looking at your new output logging, I can see that your searching through every city in every state and in every country. That's why you're reporting invalid zips for Canadian and other companies. Maybe we should do the --radius-cities before the --radius always, I mean to prefilter it.

We already have geo coordinates in this file:

```
❯ head cocli_data/scraped_data/turboship/prospects/prospects.csv -n 1
created_at,updated_at,version,id,Keyword,Name,Full_Address,Street_Address,City,Zip,Municipality,State,Country,Timezone,Phone_1,Phone_Standard_fo
rmat,Website,Domain,First_category,Second_category,Claimed_google_my_business,Reviews_count,Average_rating,Hours,Saturday,Sunday,Monday,Tuesday,
Wednesday,Thursday,Friday,Latitude,Longitude,Coordinates,Plus_Code,Place_ID,Menu_Link,GMB_URL,CID,Google_Knowledge_URL,Kgmid,Image_URL,Favicon,R
eview_URL,Facebook_URL,Linkedin_URL,Instagram_URL,Thumbnail_URL,Reviews,Quotes,Uuid
```

And that is a CSV, which is smaller and faster. Maybe we are just not making full use of the data we already have?

We already have some code for accessing that cache (the CSV), and we have a domains CSV somewhere that links the company with the address to the domain, or multiple domains.

Maybe the first thing we need is an catalog of our data structures. We might already have that in our documentation, but maybe we need a module and a command to coordinate it, so that you could have discovered the coordinates we already have sooner.

I have nothing against indexes, but I want to build them from the buttom up incrementally, while we discover how the app will be accessing the data.

So, I am thinking that we should have a standard of creating intermediate output and saving them to sintactically meaningful directory paths. I think I should move my `campaigns/` to `cocli_data` for instance. We could create a temporary `cities-within-10-miles-of-albuquerque-nm.csv` in a `cocli_data/filters/cities`, maybe, until we figure out how to improve that.

intermediate results from the search workflow should be cached and the cache should be checked. Maybe it would be better to create a list of nearby cities along with their distance.

I am assuming you know how to do some geo math on the lat long.


PROMPT:
I think a CSV is already created. I think CSVs are smaller and faster. Isn't that why AWS uses them for data lakes and stuff? We can use `rg` and `cut` in a pipeline to produce vary fast CSV indexes.

I don't think you are understanding my idea. I don't want to build a global index yet. I want to store our intermediate index output to files in proper directory structures, like `cocli_data/filters/cities/proximity-to-albuquerque.csv` for the current query we are currently performing. We will probably never have to throw that away. Then we can select sitices from that that have a `miles` of 10 or less. We don't have to create that for every city on Earth. We can create it for cities in our `prospects.csv` that exist within a geocode box of a size greater than 10 miles. We could do that with `rg`, I think. Then, we would need to dedupe that list of cities and their geocode. Fetching and deduping should be done as a single step.

