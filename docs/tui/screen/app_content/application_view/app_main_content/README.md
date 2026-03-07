# Application Main Content

The central area of the Application View that displays details for the selected category.

## Structure

```text
Container(id="app_main_content") {
    LoadingIndicator(id="app_loading")
    # One of:
    VerticalScroll(id="view_operations")
    QueueDetail(id="queue_detail")
    IndexDetail(id="index_detail")
    CampaignDetail(id="campaign-detail")
    StatusView(id="view_status")
    ClusterView(id="view_cluster")
}
```
