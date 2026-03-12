# Create dev environment refresh

Create a DEV environment from PROD

- Make a script to create a duplicate of the PROD data
- At first, we can create a complete duplicate. Over time, we should figure out ways to create a reduced environment for DEV, but it still has to be big enough to run realistic performance evals 
- We will need to be able to refresh the minimized DEV env from PROD, overwriting whatever was in DEV, at any time
- We should always be doing dev work in the DEV data. We will need some kind of DEV mode, that we should indicate in the CLI and TUI. There may one day be a UAT also, so we should create an environment enum, I think.

