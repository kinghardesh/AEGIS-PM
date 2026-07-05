# Sales Report CSV Export

## Overview

Users of our analytics dashboard frequently need to pull the sales report out of the product to work with it in spreadsheet tools. Today the only option is manual copy-paste, which is error-prone for large reports. We will add a first-class CSV export so users can download the current sales report as a well-formed CSV file.

The export must handle large reports efficiently by streaming rather than buffering the entire file in memory, and it must produce standards-compliant CSV that opens cleanly in common spreadsheet applications.

## Requirements

1. **Export button** — Add an "Export to CSV" button on the sales report page. Clicking it initiates a download of the currently displayed report.

2. **Streaming export endpoint** — Add a backend endpoint that generates the CSV for the requested report and streams the response to the client, so memory usage stays bounded regardless of report size.

3. **Column selection** — Let the user choose which columns to include in the export before downloading. The generated CSV includes only the selected columns, in the displayed order.

4. **RFC 4180 escaping** — Encode the CSV per RFC 4180: quote fields containing commas, double quotes, or newlines, and escape embedded double quotes by doubling them.

5. **Header row** — The first row of the CSV contains the human-readable column names for the selected columns.

## Out of Scope

- Export to XLSX, PDF, or any format other than CSV
- Scheduled or emailed exports
