# How the Automation Code Works

## Overview
The Enterprise Scorecard automation creates and configures scorecards in the e.fundamentals settings portal by automating browser interactions using Selenium. It processes Excel/CSV files to extract configuration data and applies it through a multi-phase workflow with comprehensive monitoring and error tracking.

**Tech Stack**: Python 3 + Flask + Selenium WebDriver + Pandas  
**Code Base**: 6,709 lines (app1a.py) + 1,161 lines (UI)  
**Architecture**: Multi-threaded Flask server with real-time status updates

---

## System Architecture

### **Core Components**

1. **Flask Web Server**
   - Serves UI at `http://localhost:5005` (configurable via PORT env variable)
   - RESTful API endpoints for automation control and status
   - Non-blocking automation using separate threads

2. **Monitoring System**
   - Real-time operation tracking with timestamps
   - Automatic error capture with full stack traces
   - Screenshot capture on failures (`error_screenshots/` directory)
   - Performance metrics calculation
   - Three types of reports: JSON (detailed), JSON (monitoring), TXT (summary)

3. **Step Tracking System**
   - Tracks all phases and steps with status (✅ success, ❌ failed, 🔄 in progress, ⏭️ skipped)
   - Real-time UI updates every 2 seconds
   - Comprehensive JSON reports saved to `tracking_reports/` directory

4. **Browser Automation**
   - Selenium WebDriver with Chrome
   - Automatic ChromeDriver management via webdriver_manager
   - 30-second manual login window
   - Intelligent wait strategies with explicit waits

---

## Complete Workflow

### **Initialization Phase**

1. **User fills web form** → Submits via UI (`templates/index.html`)
2. **Flask receives request** → `/start_automation` endpoint
3. **Validation** → Checks required fields:
   - Always: `customer_name`, `scorecard_name`, `scorecard_type`, `freshdesk_ticket_url`
   - New scorecard: `start_year`, `start_month`, `start_day`
4. **Initialize tracking** → Sets up `step_tracker` and `monitoring_log` dictionaries
5. **Thread creation** → Starts `run_automation()` in separate daemon thread
6. **Browser setup** → Launches Chrome with Selenium WebDriver

**Tracked Steps:**
- Browser Setup
- Read Excel File

---

## Phase 1: Client Selection & Scorecard Creation

### **Step 1: Login & Client Selection**
- Opens `https://settings.ef.uk.com/client_selection`
- **Manual login window**: Waits up to 30 seconds for login
- User clicks "Continue" button in UI to proceed
- Searches for client by `customer_name` in dropdown
- Selects the matching client

### **Step 2: Read Excel/CSV Configuration**
The `read_excel_data()` function handles three formats:

**Format 1: Enterprise** (most common)
- Has column: `Scorecard Measure Selection/Add Measure`
- Filters: Only processes rows where this column = `True`
- Reads columns: `Measure Group`, `Measure Name`, `Display Name`, `Definitions`
- Supports smart header detection (scans first 5 rows for headers)

**Format 2: Lego Brazil** (special case)
- Has column: `Grouping Name`
- Column mapping:
  - `Grouping Name` → `measure_group`
  - `Client Name of Metric` → `measure_display_name`
  - `Internal Measures Name` → `standard_kpis`
  - `Measure Order` → `order`
  - `Notes` → `definition`

**Format 3: Competitor** (simplified)
- Simple 4-column format
- No filtering, processes all rows
- Columns: `Measure Group`, `Standard KPIs`, `Measure Display Name`, `Definition`

### **Step 3: Create/Select Scorecard**
```python
if use_existing_scorecard:
    # Select existing scorecard from dropdown
else:
    # Create new scorecard
    - Navigate to scorecard creation page
    - Fill scorecard name
    - Select scorecard type
    - Set start date (year, month, day)
    - Click "Create" button
```

### **Step 4: Add Measures (Enterprise Only)**
- Only for scorecard_type == "Enterprise"
- For each measure from filtered Excel data:
  - Click "Add Measure" button
  - Search and select measure config by name
  - Click "Save"
- Logs each measure addition

**Tracked Steps:**
- Navigate to Login Page
- Manual Login
- Search for Client
- Create/Select Scorecard
- Add Measures (if Enterprise)

---

## Phase 1.5: Organization ID Update (Optional)

Only if `organization_id_phase1_5` is provided:
- Navigate to client settings page
- Search for client by name
- Click "Edit" button
- Update Organization ID field
- Click "Save"

**Tracked Steps:**
- Update Organization ID

---

## Phase 2: Weights & Targets 🎯

This is the most critical phase, handling bulk weight/target imports.

### **Step 1: Determine Setup Sheet Path**
```python
if setup_sheet_path provided in form:
    use setup_sheet_path
elif excel_file_path provided in form:
    use excel_file_path (same as Phase 1)
else:
    SKIP Phase 2 (no data to process)
```

### **Step 2: Export Template**
- Navigate to `https://settings.ef.uk.com/weights_targets`
- Select scorecard from dropdown
- Click "Bulk Operations" → "Export Template"
- Job submitted to background queue

### **Step 3: Wait & Download** (`wait_for_export_job_and_download()`)
**Advanced file search strategy:**
1. Navigate to `https://settings.ef.uk.com/tracked_jobs`
2. Poll job status every 10 seconds (max 5 minutes)
3. Wait for status = "COMPLETE"
4. Click download link
5. Search for downloaded file in multiple locations:
   - User-specified `export_file_path` directory
   - `~/Downloads`
   - Project `downloads/` folder
6. File matching criteria:
   - Modified in last 2 hours
   - Name contains: "export", "weight", "target", or "ExportWeightsTargetTemplateJob"
   - Most recent file wins
7. Returns full path to downloaded file

### **Step 4: Process File** (`process_weights_targets_file()`) ⭐

**This is the critical transformation function**

**Input Parameters:**
- `export_file_path`: Downloaded template CSV/Excel
- `setup_sheet_path`: Setup sheet with target weights
- `output_csv_path`: Where to save processed file
- `retailer_weights_targets_path`: Optional retailer-specific weights
- `scorecard_name`: Exact scorecard name for filtering

**Processing Steps:**

#### **4a. Read & Normalize Export File**
```python
# Read CSV or Excel
export_df = pd.read_csv(export_file_path) or pd.read_excel(export_file_path)

# Normalize column names (handles shortened names)
# 'targ' → 'target', 'weig' → 'weight', 'ret' → 'retailer', etc.
```

#### **4b. Read Setup Sheet with Smart Header Detection**
- Scans first 30 rows to find header row
- Uses scoring system to identify headers:
  - Keywords: "target", "weight", "metric name", "display name"
  - Weighted scoring (weight columns = 3 points, metric name = 2 points)
  - Minimum score threshold: 5 points
- Filters rows where `Scorecard Measure Selection/Add Measure == True`
- Handles both CSV and Excel formats

#### **4c. Apply Metric-Level Weights/Targets**
**Filters applied to export file:**
- `measure_config` is NOT blank
- `measure_group` IS blank
- `scorecard` exactly matches `scorecard_name`
- `retailer` IS blank

**For each filtered row:**
- Find matching row in setup sheet by "Metric Name"
- Copy `Target` → `target` column
- Copy `Metric Weight` → `weight` column
- Convert percentages: "15%" → 15
- Log successful updates

#### **4d. Apply Defaults**
For **ALL** empty cells in export file:
- `target` = 50 (if blank)
- `weight` = 1.0 (if blank)

#### **4e. Apply Retailer-Level Weights/Targets (Optional)**
If `retailer_weights_targets_path` provided:

**Filters applied to export file:**
- `measure_config` IS blank
- `measure_group` IS blank
- `brand` IS blank
- `scorecard` exactly matches `scorecard_name`
- `retailer` is NOT blank

**For each filtered row:**
- Find matching row in retailer sheet by "Retailer" name
- Copy `Retailer Target` → `target` column
- Copy `Retailer Weight` → `weight` column
- Overrides defaults from Step 4d

#### **4f. Save Processed CSV**
```python
output_path = f"processed/processed_weights_targets_{timestamp}.csv"
export_df.to_csv(output_path, index=False)
print(f"Phase 2: ✓ CSV file saved: {output_path}")
return True
```

### **Step 5: Import Processed CSV**
- Navigate to weights & targets page
- Select scorecard
- Click "Bulk Operations" → "Import"
- Upload processed CSV file
- Enter change reason (Freshdesk ticket URL from form)
- Submit import
- Wait for import job completion

**Tracked Steps:**
- Export Template
- Download File
- Process File
- Import Processed CSV

---

## Phase 3: Measure Groups & Configs (Enterprise Only)

Only for scorecard_type == "Enterprise":
- Create measure groups
- Add measure configs to groups
- Configure display names and definitions

**Tracked Steps:**
- Create Measure Groups
- Configure Measure Configs

---

## Phase 3a: Looker Config Update (Enterprise Only)

Only for scorecard_type == "Enterprise":
- Navigate to Looker config page
- Update dashboard and model configurations
- Save changes

**Tracked Steps:**
- Update Looker Config

---

## Phase 4: Search Term Weights (Optional)

Only if `search_term_weights_path` provided:

### **Processing Steps:**
1. Read search term weights CSV/Excel
2. Process and validate data
3. Navigate to search term weights page
4. Import file via bulk operations
5. Wait for import completion

**Tracked Steps:**
- Read Search Term Weights File
- Import Search Term Weights

---

## Phase 5: Category Brand Mapping (Optional)

Only if category brand mapping file provided:

### **Processing Steps:**
1. Read category brand mapping Excel
2. Process mapping data
3. Navigate to category brand mapping page
4. Import file via bulk operations
5. Wait for import completion

**Tracked Steps:**
- Read Category Brand Mapping File
- Import Category Brand Mapping

---

## Phase 6: Rating Thresholds

### **For Enterprise Scorecards:**
- For each measure config with custom thresholds:
  - Navigate to measure config page
  - Click edit icon
  - Update X and Y threshold values
  - Click "Save"

### **For Competitor Scorecards:**
- Find "Rating > x" measure config
- Update threshold values (default: X=4.20, Y=50)
- Click "Save"

**Tracked Steps:**
- Update Rating Thresholds

---

## Phase 7: Diff Check & Final Verification

### **Steps:**
1. Navigate to legacy editor
2. Perform diff check operation
3. Verify all changes applied correctly
4. Log verification results

**Tracked Steps:**
- Perform Diff Check
- Verify Changes

---

## Phase 8: Finalization

- Complete step tracker
- Save comprehensive reports
- Close browser (after 10-second verification window)
- Set `automation_status["running"] = False`

**Tracked Steps:**
- Automation Complete

---

## Key Functions Reference

### `init_step_tracker(customer_name, scorecard_name)`
Initializes tracking for new automation run:
- Resets `step_tracker` dictionary
- Resets `monitoring_log` dictionary
- Sets start time

### `track_step(phase_name, step_name, status, message, details, error, driver)`
Tracks individual steps:
- Logs to `step_tracker["phases"]`
- Logs to `monitoring_log["operations"]`
- Captures error details if failed
- Takes screenshot on failure
- Prints to console with status icons

### `log_operation(operation_type, phase_name, step_name, status, message, error, driver, details)`
Comprehensive operation logging:
- Records timestamp, status, message
- Captures full stack traces
- Records browser state (URL, page source snippet)
- Takes screenshot on errors
- Adds to errors/warnings lists

### `capture_error_screenshot(driver, phase_name, step_name)`
Automatic screenshot capture:
- Creates `error_screenshots/` directory
- Filename: `error_{Phase}_{Step}_{Timestamp}.png`
- Returns screenshot path

### `finalize_step_tracker()`
Saves three types of reports:
1. **Tracking Report** (`tracking_report_{Customer}_{Timestamp}.json`)
   - All phases and steps with status
   - Timestamps and durations
2. **Monitoring Report** (`monitoring_report_{Customer}_{Timestamp}.json`)
   - All operations with full details
   - All errors with stack traces
   - All screenshots
   - Performance metrics
3. **Summary Report** (`summary_report_{Customer}_{Timestamp}.txt`)
   - Human-readable summary
   - Error details with stack traces
   - Warning list
   - Phase summary
   - Performance metrics

### `read_excel_data(excel_path)`
Smart Excel/CSV reader:
- Detects format (Enterprise, Lego Brazil, Competitor)
- Finds header row (scans first 5 rows)
- Handles `#REF!` errors in headers
- Filters by `Scorecard Measure Selection/Add Measure == True`
- Returns list of measure dictionaries

### `process_weights_targets_file(...)`
Main Phase 2 processing function:
- Reads export and setup files
- Smart header detection (scans 30 rows)
- Applies metric-level weights/targets
- Applies defaults (target=50, weight=1.0)
- Applies retailer-level weights/targets
- Saves processed CSV to `processed/` directory
- Returns True/False for success/failure

### `wait_for_export_job_and_download(driver, username, export_file_path)`
Advanced file search:
- Polls job status on tracked jobs page
- Searches multiple directories
- Matches files by pattern and recency
- Returns path to downloaded file

---

## Error Handling Strategy

### **Try-Except Blocks**
Every phase wrapped in try-except:
```python
try:
    # Phase logic
    track_step(phase, step, "success", message)
except Exception as e:
    track_step(phase, step, "failed", str(e), error=e, driver=driver)
    # Continue to next phase
```

### **Screenshot Capture**
Automatic on any failed step:
- Saves to `error_screenshots/`
- Includes phase, step, timestamp in filename
- Links to error in monitoring log

### **Error Propagation**
- Errors logged but don't stop automation
- Each phase independent
- Final report shows all errors

### **Detailed Logging**
Every operation logged with:
- Timestamp (ISO format)
- Phase and step name
- Status (success/failed/skipped/in_progress)
- Error message and type
- Stack trace
- Browser URL and page source snippet
- Screenshot path

---

## File Flow Diagram

```
┌─────────────────────────────────────┐
│   Excel/CSV Configuration File      │
│  (Measure Selection & Definitions)  │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│      Phase 1: Read & Create         │
│   - Parse Excel (filter by True)    │
│   - Create scorecard                │
│   - Add measures                    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   Phase 2: Export Template          │
│   - Bulk export weights/targets     │
│   - Download CSV from portal        │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│     Downloaded Export File          │
│  (Portal-generated template CSV)    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  process_weights_targets_file()     │
│   1. Read export + setup sheet      │
│   2. Apply metric weights/targets   │
│   3. Apply defaults                 │
│   4. Apply retailer weights         │
│   5. Save to processed/ folder      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   Processed CSV                     │
│  processed/processed_weights_       │
│  targets_{timestamp}.csv            │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   Phase 2: Import to Portal         │
│   - Bulk import processed CSV       │
│   - Apply changes to scorecard      │
└─────────────────────────────────────┘
```

---

## API Endpoints

### **POST `/start_automation`**
Starts automation in background thread
- Validates required fields
- Creates daemon thread for `run_automation()`
- Returns `{"success": True, "message": "Automation started"}`

### **POST `/continue_automation`**
Continues after manual login
- Sets `continue_automation_flag` event
- Returns `{"success": True, "message": "Continuing automation"}`

### **GET `/status`**
Returns current automation status
```json
{
  "running": true,
  "message": "Phase 2: Processing file...",
  "step_tracking": {
    "start_time": "2026-02-04T10:30:00",
    "customer_name": "Lego Spain",
    "scorecard_name": "Lego Spain 2026",
    "phases": {
      "Phase 1": {"status": "success", "steps": [...]},
      "Phase 2": {"status": "in_progress", "steps": [...]}
    },
    "monitoring": {
      "total_errors": 0,
      "total_warnings": 1,
      "total_operations": 15,
      "screenshots_captured": 0,
      "recent_errors": [],
      "recent_warnings": [...]
    }
  }
}
```
Polled every 2 seconds by UI

### **GET `/step_tracking`**
Returns detailed step tracking report (full JSON)

### **GET `/monitoring`**
Returns comprehensive monitoring data:
- All operations
- All errors with stack traces
- All warnings
- All screenshots
- Performance metrics

### **GET `/monitoring/errors`**
Returns only error list with details

### **GET `/monitoring/summary`**
Returns quick metrics summary

### **GET `/get_measure_configs`**
Returns list of measure configs from Excel file
- Used by UI to populate threshold dropdown
- Query param: `excel_file_path`

---

## Status Updates Flow

```
Automation Thread              Flask Server              Web UI
     │                              │                       │
     │─────track_step()────────────▶│                       │
     │  (updates step_tracker)      │                       │
     │                              │                       │
     │───automation_status["msg"]──▶│                       │
     │                              │                       │
     │                              │◀────GET /status───────│
     │                              │   (every 2 seconds)   │
     │                              │                       │
     │                              │──status + tracking───▶│
     │                              │                       │
     │                              │                       │──Updates UI
     │                              │                       │  (progress bar,
     │                              │                       │   step tracker,
     │                              │                       │   monitoring panel)
```

---

## Monitoring Dashboard Data

The UI displays real-time monitoring:
- **Operations**: Total operations performed
- **Errors**: Count with red indicator if > 0
- **Warnings**: Count with yellow indicator if > 0
- **Screenshots**: Count of error screenshots
- **Recent Errors**: Last 5 errors with full details
- **Recent Warnings**: Last 5 warnings
- **Success Rate**: Calculated as (operations - errors) / operations × 100%

---

## Why This Design Works

1. **Non-Blocking**: Automation runs in separate thread, Flask remains responsive
2. **Real-Time Feedback**: 2-second polling provides immediate visibility
3. **Comprehensive Tracking**: Every operation logged with full context
4. **Error Resilience**: Each phase independent, failures don't cascade
5. **Visual Debugging**: Screenshots show exact error state
6. **Audit Trail**: Three report types for different needs
7. **Flexible Input**: Handles multiple Excel formats automatically
8. **Smart File Detection**: Multiple strategies for finding downloaded files
9. **Idempotent**: Can be re-run safely, skips completed phases


