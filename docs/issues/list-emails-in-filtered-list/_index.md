In this project, we have upgraded our @cocli/commands/google_maps.py and similar functions to use a better workflow-based approach that's aware of our campaign context.

I have done this:

```
[08:43:55] company-cli   main [$⇡9] is 📦 v0.2.0 on ☁️  mark (us-east-1)
❯ cocli status
Current context is: missing:email
No campaign is set.

[08:46:35] company-cli   main [$⇡9] is 📦 v0.2.0 on ☁️  mark (us-east-1)
❯ cocli campaign set turboship
Campaign context set to: turboship
Current workflow state for 'turboship': idle

[08:47:01] company-cli   main [$⇡9] is 📦 v0.2.0 on ☁️  mark (us-east-1)
❯
```

You can see that I have the `context` set to `missing:email` and the `campaign` set to `turboship`.

What I want to do now is find out how many prospects we have in the Albequerqe, NM area that have emails. Should we create a `with:email`, or should we create a search function that allows filtering on city-state and email status? And by emails, I mean company email, or contact with email. And by Albequerque area, I mean within 50 miles of Albequerque.

The goal I am trying to get to is 100 emails near Albequerque. So, first I would need to be able to count how many emails we already have near Ablequerque, which I will have to run periodically in order to know when the goal is satisfied, and we need to back out our Google Maps search so that it can search in broader areas. I think Google Maps has about 17 levels of locality range in it's search function.

I have investigated the `missing:email` and discovered that it builds an ad hoc cache from the `get_companies_dir()` and maybe the `get_people_dir()` in the `cocli/core/config.py`, which is suitable because it's for a long-lasting context.

For now, we could do the same thing to produce a count of emails in an area.