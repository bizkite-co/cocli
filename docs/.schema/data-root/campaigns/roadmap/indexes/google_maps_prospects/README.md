# Google Maps Prospects Index

This should provide the fast-lookup index, as well as declared referential integrity between the indexed objects.

There is a one-to-one relationship between the Google Maps Place_ID and our company storage in a directory name slug.

## Write-Ahead Log (WAL)

The `{place_id}.usv` files in this directory are the write-ahead log items. They are last-write-wins and auto-de-duping.

A checkpointing compiler will have to periodically write them to a read-only index.

## Next Steps

* [ ] Decide if the read-only index will be sharded, and if so, how.
* [ ] Figure out the best way to lock the write log items while still allowing new writes.
