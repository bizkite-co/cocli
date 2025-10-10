we are going to be migrating some of our workflow code to . We've already done some of it. Our code is using Pydantic and
    to establish a semantics of model transformations for our ETL and campaign workflows. So, we are trying to think of every step and the
  larger phases of the workflows as a transformation from one object type to another object type, such as a input CSV to an enriched directory
  structure. This will drive us to clearly define data structures and plan work as kinds of map-transform flows.

  Right now, we need to update our logging. We have a whole bunch of stuff like this:

  

  But we have also started to do this:

  

  I would like to move everything towards the second examples by using a modern and robust and professional and production-ready standardized
  logging on an application-wide range, but I thought it might also be a good time to consider a possible CQRS event sourcing for troubleshooting
   ETL history, etc. I'm wondering if there is a way to standardize the transform logging in such a way that we could trace the data back to it's
   source to better understand and troubleshoot data integrity problems.
