# Competitor Scorecard Creation Timeline & Process

## Overview
This document outlines the complete automation process for creating a **Competitor** scorecard from start to finish.

---

## Prerequisites
Before starting, you need:
1. **Customer name** (e.g., `lego-es`)
2. **Scorecard name** (e.g., `Default-Standard`)
3. **Scorecard type**: Competitor
4. **Start date** (Year, Month, Day)
5. **Freshdesk ticket URL** (change reason)
6. **Rating Threshold (X)** - Optional (defaults to 4.20)
7. **Number of Ratings Threshold (Y)** - Optional (defaults to 50)
8. **Excel Configuration File** - Contains measure selection

---

## Complete Process Flow

### **Initialization** (~2-3 seconds)
**What happens:**
- Browser (Chrome) is launched
- Excel configuration file is read to get measure selections
- Tracking systems initialized

**Steps:**
1. Start Chrome browser
2. Read Excel file (e.g., `Lego Spain/Measure Selection.xlsx`)
3. Load measures data

---

### **Phase 1: Client Selection** (~30-60 seconds)
**What happens:**
- Navigate to settings portal
- Manual login required
- Search and select client

**Steps:**
1. Navigate to `https://settings.ef.uk.com/client_selection`
2. **MANUAL STEP**: User logs in (30 seconds wait or click Continue button)
3. Search for client by customer name
4. Select the client from search results
5. Navigate to client settings page

**Duration:** 30-60 seconds (includes manual login time)

---

### **Phase 1.5: Organization ID Update** (Optional, ~30-45 seconds)
**What happens:**
- Updates organization ID if provided in form

**Steps:**
1. Navigate to clients page
2. Search for client
3. Edit organization ID field
4. Save changes

**Duration:** 30-45 seconds
**When it runs:** Only if `organization_id` is provided in the form

---

### **Phase 2: Measure Selection** (~2-5 minutes)
**What happens:**
- Creates or selects existing scorecard
- Configures measures from Excel file
- Sets rating thresholds

**Steps:**
1. Navigate to Scorecards page
2. **If creating new scorecard:**
   - Click "Add Scorecard"
   - Fill in scorecard name
   - Select type: "Competitor"
   - Set start date (Year/Month/Day)
   - Enter change reason
   - Click "Create Scorecard"
3. **If using existing scorecard:**
   - Select scorecard from dropdown
4. Configure measures:
   - For each measure in Excel file:
     - Find measure in UI
     - Select it
     - Configure any specific settings
5. Set Rating Thresholds (if provided):
   - Rating Threshold (X) - e.g., 4.20
   - Number of Ratings Threshold (Y) - e.g., 50
6. Save scorecard configuration

**Duration:** 2-5 minutes (depending on number of measures)

---

### **Phase 2 Alternative: Weights & Targets Import** (Optional, ~3-5 minutes)
**What happens:**
- Exports template from portal
- Processes with setup sheet
- Imports back to portal

**Steps:**
1. Navigate to Weights & Targets page
2. Click "Bulk Operations" → "Export Template"
3. Wait for export job to complete (~30-60 seconds)
4. Download exported file
5. Process file with setup sheet:
   - Read exported template
   - Read setup sheet (e.g., `Metric Weights and Targets.xlsx`)
   - Apply metric-level weights and targets
   - Apply retailer-level weights and targets
   - Apply defaults where needed
   - Save processed CSV
6. Import processed CSV:
   - Navigate to Weights & Targets
   - Click "Bulk Operations" → "Import Weights & Targets CSV"
   - Upload processed file
   - Enter change reason
   - Click "Import"
   - Wait up to 200 seconds for import to complete

**Duration:** 3-5 minutes
**When it runs:** Only if weights/targets setup sheet path is provided

---

### **Phase 3a: Looker Config** (Skipped for Competitor)
**What happens:**
- For Competitor scorecards: **SKIPPED**
- This phase only runs for Enterprise scorecards

**Duration:** 0 seconds (skipped)

---

### **Phase 4: Search Term Weights Import** (Optional, ~30-45 seconds)
**What happens:**
- Processes search term weights file
- Imports to portal

**Steps:**
1. Read search term weights file (e.g., `Search_Terms_Branded.csv`)
2. Process file:
   - Find "Search Term" and "Weight" columns
   - Add scorecard name column
   - Clean and format data
   - Save processed CSV
3. Import to portal:
   - Navigate to Search Term Weights page
   - Select scorecard from dropdown
   - Click "Bulk Operations" → "Import Search Term Weights CSV"
   - Upload processed file
   - Enter change reason
   - Click "Import"
   - Wait for completion

**Duration:** 30-45 seconds
**When it runs:** Only if `search_term_weights_path` is provided

---

### **Phase 5: Category Brand Mapping** (Optional, ~1-2 minutes)
**What happens:**
- Imports category-brand relationships from Excel

**Steps:**
1. Read Category Brand mapping file:
   - For Competitor: `Category Brand mapping/Competition.xlsx`
   - Process data (forward-fill Brand column where missing)
2. Convert to CSV format
3. Navigate to Category Brand page
4. Click "Bulk Import Category Brand"
5. Upload CSV file
6. Enter change reason
7. Click "Save"
8. Wait for confirmation

**Duration:** 1-2 minutes
**When it runs:** Only if `category_brand_mapping_type` is "Competitor" or "Enterprise"

---

### **Phase 6: Legacy Config Update** (Optional, ~1-2 minutes)
**What happens:**
- Updates legacy configuration if provided

**Steps:**
1. Navigate to legacy_editor page
2. Find and update configuration fields
3. Save changes

**Duration:** 1-2 minutes
**When it runs:** Only if legacy config data is provided

---

### **Phase 7: Diff Check Operations** (~45-60 seconds)
**What happens:**
- Runs diff checks against TEST and PROD environments

**Steps:**
1. Navigate to `https://settings.ef.uk.com/legacy_editor`
2. Click "Diff Check TEST"
3. **Wait 15 seconds** for operation to complete
4. Click "Back"
5. Click "Diff Check PROD"
6. **Wait 15 seconds** for operation to complete
7. Click "Back"

**Duration:** ~45-60 seconds (includes 15-second waits)

---

### **Finalization** (~10-15 seconds)
**What happens:**
- Saves tracking reports
- Generates monitoring reports
- Keeps browser open for verification

**Steps:**
1. Generate tracking report (JSON)
2. Generate monitoring report (JSON)
3. Generate summary report (TXT)
4. Save all reports to `tracking_reports/` folder
5. Keep browser open for 10 seconds for verification
6. Automation complete

**Duration:** 10-15 seconds

---

## Total Timeline Estimate

### Minimum Configuration (Required phases only)
- Initialization: 2-3 seconds
- Phase 1: 30-60 seconds
- Phase 2: 2-5 minutes
- Phase 7: 45-60 seconds
- Finalization: 10-15 seconds

**Total: ~4-7 minutes**

---

### Full Configuration (All optional phases included)
- Initialization: 2-3 seconds
- Phase 1: 30-60 seconds
- Phase 1.5: 30-45 seconds (if Organization ID provided)
- Phase 2: 3-5 minutes (with weights/targets import)
- Phase 4: 30-45 seconds (if search term weights provided)
- Phase 5: 1-2 minutes (if category brand mapping provided)
- Phase 6: 1-2 minutes (if legacy config provided)
- Phase 7: 45-60 seconds
- Finalization: 10-15 seconds

**Total: ~8-15 minutes**

---

## Key Differences: Competitor vs Enterprise

| Feature | Competitor | Enterprise |
|---------|-----------|------------|
| Rating Thresholds | Optional (defaults: 4.20, 50) | Handled via measure configs |
| Looker Config (Phase 3a) | **Skipped** | **Runs** |
| Category Brand Mapping | Uses `Competition.xlsx` | Uses `Enterprise.xlsx` |
| Measure Configuration | Single threshold set | Multiple measure-specific configs |

---

## Monitoring & Tracking

Throughout the entire process, the system:
1. **Tracks every step** with timestamps and status
2. **Captures errors** with screenshots and stack traces
3. **Monitors performance** for each operation
4. **Generates reports** saved in `tracking_reports/` folder:
   - `tracking_report_[client]_[timestamp].json` - Detailed step tracking
   - `monitoring_report_[client]_[timestamp].json` - Error and performance data
   - `summary_report_[client]_[timestamp].txt` - Human-readable summary

---

## Success Indicators

The automation is successful when:
1. ✅ All required phases complete without errors
2. ✅ Scorecard is created/configured in the portal
3. ✅ All data imports complete successfully
4. ✅ Diff checks pass for TEST and PROD
5. ✅ Tracking report shows "success" status for all phases

---

## Common Failure Points

1. **Phase 2 - Export Template**: If Bulk Operations menu is not accessible
2. **Phase 2 - Import CSV**: If import takes longer than 200 seconds
3. **Phase 4 - Search Term Weights**: If file path is incorrect
4. **Phase 5 - Category Brand Mapping**: If file format is incorrect
5. **Phase 7 - Diff Checks**: If legacy_editor page is not accessible

---

## Manual Intervention Required

Only **one** manual step is required:
- **Phase 1**: Login to settings portal (30 seconds wait)

All other steps are fully automated.
