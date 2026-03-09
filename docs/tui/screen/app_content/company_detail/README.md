# Company Detail

View for managing a single company's details, contacts, meetings, and notes.

## Current Structure (Implementation)

Currently, the view uses a 2x2 grid (`detail-grid`) where all panels are of equal size.

```text
CompanyDetail {
    Container(classes="detail-grid") {
        DetailPanel(id="panel-info")      # Top-Left
        DetailPanel(id="panel-contacts")  # Top-Right
        DetailPanel(id="panel-meetings")  # Bottom-Left
        DetailPanel(id="panel-notes")     # Bottom-Right
    }
}
```

## Proposed Structure (Refactor)

The new layout will feature two primary vertical columns to give more space to company information.

```text
CompanyDetail {
    Horizontal {
        # Left Column: Detailed Info
        DetailPanel(id="panel-info") {
            InfoTable(id="info-table")
        }

        # Right Column: Engagement & Notes
        Vertical {
            DetailPanel(id="panel-contacts") {
                ContactsTable(id="contacts-table")
            }
            DetailPanel(id="panel-meetings") {
                MeetingsTable(id="meetings-table")
            }
            DetailPanel(id="panel-notes") {
                NotesTable(id="notes-table")
            }
        }
    }
}
```

## Strategy

- **Navigation:** Maintain VIM-like navigation (`h`, `j`, `k`, `l`) between panels.
- **Visuals:** Use a 40/60 or 50/50 split for the main columns. The right column panels will stack vertically.
- **Flexibility:** Ensure the `InfoTable` has enough width to display long names and URLs without excessive truncating.
