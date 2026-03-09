# Company Search View

Searchable list of companies with template selection and preview.

## Structure

```text
CompanySearchView {
    Horizontal {
        TemplateList(id="search-templates-pane")
        CompanyList(id="search-companies-pane") {
            Input(id="company_search_input")
            ListView(id="company_list_view")
        }
        CompanyPreview(id="search-preview-pane")
    }
}
```

## Strategy

- **Initial Focus:** Starts in the **Template List** (top-left) to allow selecting a category before searching.
- **Visual Focus:** Focused panes are highlighted with a bright green header (`#00ff00`) and a slightly lighter background. Unfocused panes are "toned down" with dimmed header text (`#555555`) and pure black backgrounds.
- **Navigation:** Supports VIM-like navigation (`h`/`l`) between the three columns.
