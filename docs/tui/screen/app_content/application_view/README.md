# Application View

The core workflow view for managing campaigns, queues, and cluster status.

## Structure

```text
ApplicationView {
    Horizontal {
        # Left Column: Navigation
        Vertical(id="app_sidebar_column") {
            Vertical(id="app_nav_container")
            Vertical(id="app_sub_nav_container")
        }

        # Center: Main Content
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

        # Right Column: Performance/History
        Vertical(id="app_recent_runs")
    }
}
```
