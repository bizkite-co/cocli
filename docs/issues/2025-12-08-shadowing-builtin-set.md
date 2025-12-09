# Incident Report: Shadowing Python's Builtin `set()`

**Date:** 2025-12-08
**Severity:** High (Crash + Config Corruption)
**Component:** CLI Commands (`cocli/commands/campaign.py`)

## Summary
A critical bug was introduced where a CLI command function was named `set`. This shadowed Python's built-in `set()` type constructor within the module's scope. When another function in the same module (`pipeline`) attempted to use `set()` to create a set of strings, it instead called the `set` command function.

## The Mechanism of Failure

1.  **Definition:**
    ```python
    @app.command()
    def set(campaign_name: str = ...): 
        # ... calls set_campaign(campaign_name) ...
    ```

2.  **Usage (Intent):**
    ```python
    # Intended to create a set from a list of keys
    existing_domains_set = set(list(existing_companies_map.keys())) 
    ```

3.  **Usage (Actual Execution):**
    *   The interpreter resolved `set` to the function defined in step 1.
    *   It passed the `list` of keys as the first argument (`campaign_name`).
    *   The `set` function executed `set_campaign(campaign_name)`, passing the *list* of thousands of domains as the campaign name.

4.  **Impact:**
    *   **Config Corruption:** The `set_campaign` function saved this list into `cocli_config.toml` under `[campaign] name = [...]`.
    *   **Runtime Crash:** `CampaignWorkflow` tried to construct a path using this "name" (`Path(...) / list`), resulting in `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'list'`.

## Resolution
The CLI command function was renamed to `set_default_campaign`, while preserving the CLI command name using the decorator:

```python
@app.command(name="set")
def set_default_campaign(...):
    ...
```

## Lessons Learned
*   **NEVER** name a function `set`, `list`, `dict`, `str`, `int`, `type`, `id`, or any other Python built-in name.
*   Use descriptive function names (e.g., `set_context`, `set_campaign_default`) and use the library's aliasing features (like `@app.command(name="set")`) to expose the desired CLI verb.
*   Type hinting does not prevent this runtime shadowing if the shadower is in the same scope.
