Analyze the local CSV file at C:\data\sales.csv — inspect its schema, column types, 
row count, value distributions, and detect any data quality issues (nulls, duplicates, 
outliers). Then build a complete multi-page Power BI report:

1. **Data Model**  
   Import the CSV into the semantic model with parameterized file path.  
   Declare explicit column types and create measures for every KPI 
   (never use default aggregation). Add a dedicated measures table.

2. **Landing Page — Executive Summary**  
   - KPI cards across the top row: one card per key numeric metric 
     (totals, counts, averages — infer from the data).  
   - A date-range slicer (Between mode) and a dropdown slicer for each 
     categorical column, synced across all pages.  
   - A clustered bar chart showing the primary metric broken down by 
     the most relevant category.

3. **Analysis Page — Trends & Breakdown** (hidden)  
   - A line or bar chart showing the primary metric over time.  
   - A second chart breaking down a secondary metric by another category.  
   - Same synced slicers as the landing page.  
   - A "Back" button returning to the landing page.

4. **Detail Page — Drillthrough** (hidden)  
   - A full table visual listing every row, sorted by date descending.  
   - Drillthrough filter bound to the main category field so users can 
     right-click any bar/card to drill into this page.  
   - A "Back" button to return to the source page.

5. **Navigation & Filtering**  
   - Add a page navigator on the landing page.  
   - Sync all slicers with matching syncGroup names across pages.  
   - Validate that drillthrough bindings, synced filters, and bookmarks 
     all work correctly.

6. **Theme & Styling**  
   - Professional look: rounded corners (radius 5–6), subtle border 
     (width 1), card-like containers with light shadow.  
   - Dark headers on tables, consistent font hierarchy.  
   - Pick a cohesive color palette from the data context 
     (e.g., blue/teal for finance, green for sustainability).

Adapt the number of pages, visuals, and measures to what the data actually 
contains — do not force visuals on columns that don't warrant them.
