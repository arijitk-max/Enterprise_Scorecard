# Step Tracking System Guide

## Overview
The step tracking system monitors all phases and steps of the automation process for any client (Lego Spain, Lego Brazil, Coca-Cola IT, etc.). It provides real-time visibility into automation execution and creates detailed reports for audit and troubleshooting.

## Features

### 1. Real-Time Tracking
- **UI Display**: The web interface shows a live step tracking panel that updates every 2 seconds
- **Status Icons**: 
  - ✅ Success - Step completed successfully
  - ❌ Failed - Step encountered an error
  - 🔄 In Progress - Step currently executing
  - ⏭️ Skipped - Step was intentionally skipped
- **Auto-Refresh**: UI polls `/status` endpoint every 2 seconds
- **No Manual Refresh Needed**: Updates appear automatically

### 2. Comprehensive Reports
Three types of reports automatically saved to `tracking_reports/` directory:

#### **a. Step Tracking Report** (JSON)
- **File Name**: `tracking_report_{CustomerName}_{Timestamp}.json`
- **Contains**: 
  - Start/end times for entire automation
  - Customer and scorecard names
  - All phases with status
  - All steps within each phase
  - Timestamps for each step
  - Error messages and error types
  - Total duration in seconds

#### **b. Monitoring Report** (JSON)
- **File Name**: `monitoring_report_{CustomerName}_{Timestamp}.json`
- **Contains**: 
  - Complete operation log
  - Full error details with stack traces
  - All warnings
  - Screenshot references
  - Browser state (URLs, page source snippets)
  - Performance metrics

#### **c. Summary Report** (Text)
- **File Name**: `summary_report_{CustomerName}_{Timestamp}.txt`
- **Contains**: 
  - Human-readable summary
  - Performance metrics
  - Error details with stack traces
  - Warning list
  - Phase summary with failed steps
  - Easy to read and share

### 3. API Endpoints
- **GET `/status`**: Returns current automation status + step tracking summary + monitoring data
- **GET `/step_tracking`**: Returns detailed step tracking report (full JSON)
- **GET `/monitoring`**: Returns comprehensive monitoring log (all operations, errors, screenshots)
- **GET `/monitoring/errors`**: Returns only the error list
- **GET `/monitoring/summary`**: Returns quick metrics summary

## What Gets Tracked

### Complete Phase List:

#### **Initialization Phase**
Steps tracked:
- Browser Setup - Chrome WebDriver initialization
- Read Excel File - Parse configuration file

#### **Phase 1: Client Selection & Scorecard Creation**
Steps tracked:
- Navigate to Login Page - Load settings portal
- Manual Login - Wait for user login (30 seconds)
- Search for Client - Find and select client
- Create/Select Scorecard - Create new or select existing
- Add Measures (Enterprise only) - Add each measure config

#### **Phase 1.5: Organization ID Update** (optional)
Steps tracked:
- Update Organization ID - Update client's org ID

#### **Phase 2: Weights & Targets**
Steps tracked:
- Export Template - Trigger bulk export job
- Download File - Wait for job completion and download
- Process File - Transform data with `process_weights_targets_file()`
- Import Processed CSV - Upload and import transformed data

#### **Phase 3: Measure Groups & Configs** (Enterprise only)
Steps tracked:
- Create Measure Groups - Add measure groups
- Configure Measure Configs - Set up measure configs in groups

#### **Phase 3a: Looker Config Update** (Enterprise only)
Steps tracked:
- Update Looker Config - Configure dashboards and models

#### **Phase 4: Search Term Weights** (optional)
Steps tracked:
- Read Search Term Weights File - Parse search terms CSV
- Import Search Term Weights - Bulk import search terms

#### **Phase 5: Category Brand Mapping** (optional)
Steps tracked:
- Read Category Brand Mapping File - Parse mapping Excel
- Import Category Brand Mapping - Bulk import mappings

#### **Phase 6: Rating Thresholds**
Steps tracked:
- Update Rating Thresholds - Set X/Y thresholds for measures

#### **Phase 7: Diff Check & Final Verification**
Steps tracked:
- Perform Diff Check - Verify all changes in legacy editor
- Verify Changes - Final validation

#### **Finalization Phase**
Steps tracked:
- Automation Complete - Save reports and close browser

### Data Captured Per Step:
Each step records:
- `step_name`: Human-readable step name
- `status`: "success", "failed", "skipped", or "in_progress"
- `timestamp`: ISO format timestamp (e.g., "2026-02-04T15:30:45.123456")
- `message`: Descriptive message about what happened
- `details`: Optional dictionary with additional context
- `error`: Error message if step failed
- `error_type`: Exception class name (e.g., "TimeoutException", "ValueError")

## How to Use

### During Automation:
1. **Start automation** through web UI at `http://localhost:5005`
2. **Step tracking panel** automatically appears below the status message
3. **Watch real-time updates** as each step completes (refreshes every 2 seconds)
4. **Monitor panel** shows errors, warnings, and operation counts
5. **No refresh needed** - UI updates automatically

### After Automation:
1. Check the `tracking_reports/` directory for three types of reports:
   - `tracking_report_{Customer}_{Timestamp}.json` - Step-by-step tracking
   - `monitoring_report_{Customer}_{Timestamp}.json` - Complete operation log
   - `summary_report_{Customer}_{Timestamp}.txt` - Human-readable summary

2. Check `error_screenshots/` directory for any error screenshots:
   - Named: `error_{Phase}_{Step}_{Timestamp}.png`

### Viewing JSON Reports (Python):
```python
import json

# Load step tracking report
with open('tracking_reports/tracking_report_Lego_Spain_20260204_153045.json', 'r') as f:
    report = json.load(f)

# View automation summary
print(f"Customer: {report['customer_name']}")
print(f"Scorecard: {report['scorecard_name']}")
print(f"Duration: {report['total_duration_seconds']} seconds")

# View phases
for phase_name, phase_data in report['phases'].items():
    print(f"\n{phase_name}: {phase_data['status']}")
    print(f"  Started: {phase_data['start_time']}")
    print(f"  Ended: {phase_data['end_time']}")
    print(f"  Steps: {len(phase_data['steps'])}")
    
    # View steps
    for step in phase_data['steps']:
        status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️", "in_progress": "🔄"}.get(step['status'], "•")
        print(f"    {status_icon} {step['step_name']}: {step['status']}")
        if step.get('error'):
            print(f"       Error: {step['error']}")

# Load monitoring report
with open('tracking_reports/monitoring_report_Lego_Spain_20260204_153045.json', 'r') as f:
    monitoring = json.load(f)

# View performance metrics
metrics = monitoring['performance_metrics']
print(f"\nPerformance Metrics:")
print(f"  Total Operations: {metrics['total_operations']}")
print(f"  Total Errors: {metrics['total_errors']}")
print(f"  Total Warnings: {metrics['total_warnings']}")
print(f"  Success Rate: {metrics['success_rate']:.2f}%")
print(f"  Screenshots: {metrics['total_screenshots']}")

# View errors
if monitoring['errors']:
    print(f"\nErrors Detected:")
    for i, error in enumerate(monitoring['errors'], 1):
        print(f"  Error #{i}:")
        print(f"    Phase: {error['phase']}")
        print(f"    Step: {error['step']}")
        print(f"    Error: {error['error']}")
        print(f"    Type: {error['error_type']}")
        if error.get('screenshot_path'):
            print(f"    Screenshot: {error['screenshot_path']}")
```

### Viewing Text Summary (Command Line):
```bash
# View summary report
cat tracking_reports/summary_report_Lego_Spain_20260204_153045.txt

# Search for errors
grep -A 10 "ERRORS DETECTED" tracking_reports/summary_report_*.txt

# Check latest report
ls -t tracking_reports/summary_report_*.txt | head -1 | xargs cat
```

### Using API Endpoints (During Automation):
```bash
# Get current status
curl http://localhost:5005/status

# Get detailed step tracking
curl http://localhost:5005/step_tracking

# Get all errors
curl http://localhost:5005/monitoring/errors

# Get monitoring summary
curl http://localhost:5005/monitoring/summary

# Get full monitoring log
curl http://localhost:5005/monitoring
```

## Example Report Structures

### Step Tracking Report (tracking_report_*.json)

```json
{
  "start_time": "2026-02-04T12:00:00.123456",
  "end_time": "2026-02-04T12:15:30.789012",
  "customer_name": "Lego Spain",
  "scorecard_name": "Lego Spain Scorecard 2026",
  "total_duration_seconds": 930.665556,
  "phases": {
    "Initialization": {
      "status": "success",
      "start_time": "2026-02-04T12:00:00.123456",
      "end_time": "2026-02-04T12:00:15.456789",
      "steps": [
        {
          "step_name": "Browser Setup",
          "status": "success",
          "timestamp": "2026-02-04T12:00:05.234567",
          "message": "Chrome WebDriver initialized",
          "details": {},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Read Excel File",
          "status": "success",
          "timestamp": "2026-02-04T12:00:15.456789",
          "message": "Loaded 25 measures from Excel",
          "details": {"file_path": "/path/to/file.xlsx", "measure_count": 25},
          "error": null,
          "error_type": null
        }
      ]
    },
    "Phase 1": {
      "status": "success",
      "start_time": "2026-02-04T12:00:15.456789",
      "end_time": "2026-02-04T12:02:30.123456",
      "steps": [
        {
          "step_name": "Navigate to Login Page",
          "status": "success",
          "timestamp": "2026-02-04T12:00:20.567890",
          "message": "Login page loaded",
          "details": {},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Manual Login",
          "status": "success",
          "timestamp": "2026-02-04T12:00:50.678901",
          "message": "User clicked Continue - proceeding",
          "details": {},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Search for Client",
          "status": "success",
          "timestamp": "2026-02-04T12:01:15.789012",
          "message": "Client 'Lego Spain' selected successfully",
          "details": {"client_name": "Lego Spain"},
          "error": null,
          "error_type": null
        }
      ]
    },
    "Phase 2": {
      "status": "success",
      "start_time": "2026-02-04T12:05:00.123456",
      "end_time": "2026-02-04T12:10:30.456789",
      "steps": [
        {
          "step_name": "Export Template",
          "status": "success",
          "timestamp": "2026-02-04T12:05:30.234567",
          "message": "Export job submitted",
          "details": {},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Download File",
          "status": "success",
          "timestamp": "2026-02-04T12:08:45.345678",
          "message": "File downloaded successfully",
          "details": {"file_path": "/Users/user/Downloads/export_20260204.csv"},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Process File",
          "status": "success",
          "timestamp": "2026-02-04T12:09:15.456789",
          "message": "File processed successfully",
          "details": {"rows_updated": 87},
          "error": null,
          "error_type": null
        },
        {
          "step_name": "Import Processed CSV",
          "status": "success",
          "timestamp": "2026-02-04T12:10:30.567890",
          "message": "Import completed",
          "details": {},
          "error": null,
          "error_type": null
        }
      ]
    },
    "Finalization": {
      "status": "success",
      "start_time": "2026-02-04T12:15:20.678901",
      "end_time": "2026-02-04T12:15:30.789012",
      "steps": [
        {
          "step_name": "Automation Complete",
          "status": "success",
          "timestamp": "2026-02-04T12:15:30.789012",
          "message": "All phases completed successfully",
          "details": {},
          "error": null,
          "error_type": null
        }
      ]
    }
  }
}
```

### Monitoring Report (monitoring_report_*.json)

```json
{
  "start_time": "2026-02-04T12:00:00.123456",
  "end_time": "2026-02-04T12:15:30.789012",
  "customer_name": "Lego Spain",
  "scorecard_name": "Lego Spain Scorecard 2026",
  "total_duration_seconds": 930.665556,
  "errors": [
    {
      "type": "step",
      "phase": "Phase 2",
      "step": "Process File",
      "status": "failed",
      "timestamp": "2026-02-04T15:30:45.123456",
      "message": "File processing returned False",
      "error": "ValueError: Could not find required column 'Target' in setup sheet",
      "error_type": "ValueError",
      "stack_trace": "Traceback (most recent call last):\n  File \"app1a.py\", line 1285, in process_weights_targets_file\n    setup_df['Target']\nKeyError: 'Target'\n",
      "url": "https://settings.ef.uk.com/weights_targets",
      "page_source_snippet": "<!DOCTYPE html><html><head><title>Weights & Targets</title>...",
      "screenshot_path": "error_screenshots/error_Phase_2_Process_File_20260204_153045.png",
      "details": {}
    }
  ],
  "warnings": [
    {
      "type": "step",
      "phase": "Phase 2",
      "step": "Export Template",
      "status": "success",
      "timestamp": "2026-02-04T12:05:25.123456",
      "message": "Warning: No setup sheet path provided, using Phase 1 Excel file",
      "error": null,
      "stack_trace": null,
      "url": "https://settings.ef.uk.com/weights_targets",
      "page_source_snippet": null,
      "screenshot_path": null,
      "details": {}
    }
  ],
  "screenshots": [
    {
      "path": "error_screenshots/error_Phase_2_Process_File_20260204_153045.png",
      "phase": "Phase 2",
      "step": "Process File",
      "timestamp": "2026-02-04T15:30:45.234567"
    }
  ],
  "operations": [
    {
      "type": "step",
      "phase": "Initialization",
      "step": "Browser Setup",
      "status": "success",
      "timestamp": "2026-02-04T12:00:05.234567",
      "message": "Chrome WebDriver initialized",
      "error": null,
      "stack_trace": null,
      "url": null,
      "page_source_snippet": null,
      "screenshot_path": null,
      "details": {}
    }
    // ... more operations ...
  ],
  "performance_metrics": {
    "total_operations": 45,
    "total_errors": 1,
    "total_warnings": 1,
    "total_screenshots": 1,
    "success_rate": 97.78
  }
}
```

### Summary Report (summary_report_*.txt)

```text
================================================================================
AUTOMATION MONITORING SUMMARY REPORT
================================================================================

Customer: Lego Spain
Scorecard: Lego Spain Scorecard 2026
Start Time: 2026-02-04T12:00:00.123456
End Time: 2026-02-04T12:15:30.789012
Total Duration: 930.67 seconds (15.51 minutes)

================================================================================
PERFORMANCE METRICS
================================================================================
Total Operations: 45
Total Errors: 0
Total Warnings: 1
Success Rate: 100.00%
Screenshots Captured: 0

================================================================================
WARNINGS
================================================================================

Warning #1:
  Phase: Phase 2
  Step: Export Template
  Message: Warning: No setup sheet path provided, using Phase 1 Excel file

================================================================================
PHASE SUMMARY
================================================================================

Initialization:
  Status: success
  Steps: 2

Phase 1:
  Status: success
  Steps: 4

Phase 2:
  Status: success
  Steps: 4

Phase 6:
  Status: success
  Steps: 1

Phase 7:
  Status: success
  Steps: 2

Finalization:
  Status: success
  Steps: 1
```
```

## Benefits

1. **Complete Visibility**: Know exactly which step is running at any time with real-time UI updates
2. **Fast Debugging**: Quickly identify where failures occur with error screenshots and stack traces
3. **Automatic Documentation**: Comprehensive records of every execution for audit purposes
4. **Verification**: Confirm all steps completed successfully with status icons
5. **Audit Trail**: Timestamped record of all actions with full details
6. **Performance Tracking**: Monitor success rates and operation counts across runs
7. **Error Analysis**: Full stack traces and browser state for deep debugging
8. **Visual Debugging**: Screenshots show exact state when errors occurred
9. **Multiple Report Formats**: JSON for parsing, TXT for reading, choose what works best
10. **Non-Intrusive**: Tracking happens automatically, no extra work needed

## Integration with Monitoring System

Step tracking works hand-in-hand with the monitoring system:

```
┌─────────────────────────────────────────────────────────┐
│                     track_step()                        │
│  Called for every step in automation                    │
└─────────────┬───────────────────────────────────────────┘
              │
              ├──────────────────┬──────────────────────┐
              ▼                  ▼                      ▼
    ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
    │  step_tracker   │  │  monitoring_log  │  │  Console Output  │
    │                 │  │                  │  │                  │
    │  - phases       │  │  - operations    │  │  ✅ Step Name    │
    │  - steps        │  │  - errors        │  │  ❌ Error msg    │
    │  - status       │  │  - warnings      │  │  📸 Screenshot   │
    │  - timestamps   │  │  - screenshots   │  │                  │
    └────────┬────────┘  └────────┬─────────┘  └──────────────────┘
             │                    │
             ▼                    ▼
    ┌─────────────────┐  ┌──────────────────┐
    │ tracking_report │  │ monitoring_report│
    │     (JSON)      │  │     (JSON)       │
    └─────────────────┘  └──────────────────┘
                          ┌──────────────────┐
                          │ summary_report   │
                          │     (TXT)        │
                          └──────────────────┘
```

## Troubleshooting with Step Tracking

### Problem: Automation stops unexpectedly
**Solution:**
1. Check last step in UI or tracking report
2. Look for ❌ failed status
3. Check error message and error_type
4. View screenshot if available
5. Read stack trace in monitoring report

### Problem: Phase shows "in_progress" but nothing happens
**Solution:**
1. Check console/terminal for output
2. Look at last operation timestamp
3. Check if browser window is responsive
4. Review monitoring_log for stuck operations

### Problem: Need to understand what happened in past run
**Solution:**
1. Open `tracking_reports/` directory
2. Find report for that run by timestamp
3. Read `summary_report_*.txt` for quick overview
4. Check `monitoring_report_*.json` for detailed analysis
5. View screenshots in `error_screenshots/` if errors occurred

### Problem: Comparing multiple runs
**Solution:**
```python
import json
import glob

# Load all tracking reports
reports = []
for file in sorted(glob.glob('tracking_reports/tracking_report_*.json')):
    with open(file) as f:
        reports.append(json.load(f))

# Compare durations
for report in reports:
    print(f"{report['customer_name']}: {report['total_duration_seconds']:.0f}s")

# Compare success rates
for report in reports[-5:]:  # Last 5 runs
    phases = report['phases']
    failed = sum(1 for p in phases.values() if p['status'] == 'failed')
    total = len(phases)
    print(f"{report['customer_name']}: {total-failed}/{total} phases succeeded")
```

## Best Practices

1. **Always check reports after automation**: Even if UI shows success, review reports for warnings
2. **Keep error screenshots**: They're invaluable for debugging UI issues
3. **Monitor success rate trends**: Declining success rates indicate automation brittleness
4. **Archive old reports**: Keep reports for audit trail and comparison
5. **Share summary reports**: Text summaries are easy to attach to tickets or emails
6. **Use API during development**: Hit `/monitoring/errors` to see errors immediately
7. **Filter by phase**: When debugging specific phase, search reports by phase name

## Notes

- Reports are saved automatically when automation completes (success or failure)
- The UI updates every 2 seconds while automation is running via polling
- Failed steps are clearly marked with ❌ and include full error details
- All timestamps are in ISO 8601 format for easy parsing and timezone handling
- Screenshots are PNG format, suitable for viewing or attaching to tickets
- JSON reports can be loaded in Python, JavaScript, or any JSON parser
- Text summaries are perfect for non-technical stakeholders
- Monitoring data persists until next automation run starts (then resets)


