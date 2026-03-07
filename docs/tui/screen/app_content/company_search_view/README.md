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
