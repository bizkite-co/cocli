# App Sub Nav Container

Context-specific sub-navigation list.

## Structure

```text
Vertical(id="app_sub_nav_container") {
    Label("Menu")
    # One of:
    CampaignSelection
    QueueSelection
    IndexSelection
    ListView(id="sidebar_operations")
}
```
