# Company Detail

View for managing a single company's details, contacts, meetings, and notes.

## Structure

The view features two primary vertical columns. The left column is dedicated to core company information, providing flexible space for long names and URLs. The right column contains stacked panels for engagement data.

```text
CompanyDetail {
    Horizontal(id="company-detail-container") {
        # Left Column: Detailed Info
        DetailPanel(id="panel-info") {
            InfoTable(id="info-table")
        }

        # Right Column: Engagement & Notes
        Vertical(id="engagement-column") {
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

- **Navigation:** Supports VIM-like navigation between panels.
    - `h`: Focus Info Panel.
    - `l`: Focus Engagement Column (Contacts).
    - `j`/`k`: Cycle vertically through engagement panels.
- **Visuals:** Uses a flexible split where company info takes the remaining space (`1fr`) and the engagement column has a fixed width (`40`).
