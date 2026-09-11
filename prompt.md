That is a lot of information, so I have to try to restate it back to you in a condensed format to make sure I understand what you are saying.

Are you saying that `stations` implies that there should be only one data type schema withing a station? That would imply that transforms should only happen between stations, right?

I was not aware that we had applied that constraint in `stations`. I am trying to think of all the eventualities that flow from that. Does that seem like a reasonable constraint? Is `gm-list` the only station that violates that?

So, `gm-list` would become some kind of split-station? One folder with two stations within it?

OK, maybe `gm-list` should always have been two stations. That is what we are saying by your split-decls solution, right?

I guess the split is the best option at this point. I think that is what I would have chosen if you had not recommended it. 

We should have a Frictionless `datapackage.json`, but I think we already have that for the USVs. 

We don't need a file-per item output in the `gm-list`. What if we put the output USV directly into `gm-details/pending/`? Oh, that is a different file type. So, you were saying that maybe the `gm-list/completed/results/*.usv` could be described as just a receipt. But, it's the result data that we need to work with.

The `gm-list` starts with a map-tile-search-phrase item and produces a USV of results. Should that go in a `gm-list-results/` stations/directory? I don't want to migrate that right now, but I thinking about how it _should_ be organized, acording to the `stations` strategy.

For now, I think you are right about the split. How should we proceed with that?
