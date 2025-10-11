I think a CSV is already created. I think CSVs are smaller and faster. Isn't that why AWS uses them for data lakes and stuff? We can use `rg` and `cut` in a pipeline to produce vary fast CSV indexes.

I don't think you are understanding my idea. I don't want to build a global index yet. I want to store our intermediate index output to files in proper directory structures, like `cocli_data/filters/cities/proximity-to-albuquerque.csv` for the current query we are currently performing. We will probably never have to throw that away. Then we can select sitices from that that have a `miles` of 10 or less. We don't have to create that for every city on Earth. We can create it for cities in our `prospects.csv` that exist within a geocode box of a size greater than 10 miles. We could do that with `rg`, I think. Then, we would need to dedupe that list of cities and their geocode. Fetching and deduping should be done as a single step.

Ok, I found some other cached indexes in here:

```sh
[16:25:44] company-cli   main [$!?⇡10] is 📦 v0.2.0 on ☁️  mark (us-east-1)
❯ ls cocli_data/cache/
google_maps_cache.csv  website_data_cache.csv
```

I gues that would necessitate that we rebuild the index every time we add a new company that's in the geocode box near Albuquerque, but I think that might be OK for now. I think the script or command that creates these operations will be reusable, exspeciall if we create a module that exposes the index tree properly.


