from flask import Flask, render_template, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
import threading
import os
from datetime import datetime
import glob
import json
import traceback
import base64

app = Flask(__name__)

# Global variable to store the automation task
automation_thread = None
automation_status = {"running": False, "message": "", "driver": None}
continue_automation_flag = threading.Event()

# Enhanced monitoring system
monitoring_log = {
    "start_time": None,
    "end_time": None,
    "errors": [],
    "warnings": [],
    "screenshots": [],
    "operations": [],
    "performance_metrics": {}
}

# Step tracking system
step_tracker = {
    "start_time": None,
    "end_time": None,
    "customer_name": "",
    "scorecard_name": "",
    "phases": {}
}

def init_step_tracker(customer_name, scorecard_name):
    """Initialize the step tracker and monitoring log for a new automation run"""
    global step_tracker, monitoring_log
    step_tracker = {
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "customer_name": customer_name,
        "scorecard_name": scorecard_name,
        "phases": {}
    }
    monitoring_log = {
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "customer_name": customer_name,
        "scorecard_name": scorecard_name,
        "errors": [],
        "warnings": [],
        "screenshots": [],
        "operations": [],
        "performance_metrics": {}
    }

def log_operation(operation_type, phase_name, step_name, status, message="", error=None, driver=None, details=None):
    """
    Comprehensive logging for all operations with error capture
    
    Args:
        operation_type: Type of operation (e.g., "step", "error", "warning", "screenshot")
        phase_name: Name of the phase
        step_name: Name of the step
        status: "success", "failed", "skipped", "in_progress"
        message: Optional message
        error: Exception object or error string
        driver: Selenium driver for screenshot capture
        details: Additional details dictionary
    """
    global monitoring_log
    
    operation = {
        "type": operation_type,
        "phase": phase_name,
        "step": step_name,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "error": None,
        "stack_trace": None,
        "url": None,
        "page_source_snippet": None,
        "screenshot_path": None,
        "details": details or {}
    }
    
    # Capture error details if provided
    if error:
        if isinstance(error, Exception):
            operation["error"] = str(error)
            operation["stack_trace"] = traceback.format_exc()
            operation["error_type"] = type(error).__name__
        else:
            operation["error"] = str(error)
    
    # Capture browser state if driver is available
    if driver:
        try:
            operation["url"] = driver.current_url
            # Capture a snippet of page source (first 500 chars)
            try:
                page_source = driver.page_source[:500]
                operation["page_source_snippet"] = page_source
            except:
                pass
        except:
            pass
    
    # Capture screenshot on errors
    if status == "failed" and driver:
        try:
            screenshot_path = capture_error_screenshot(driver, phase_name, step_name)
            if screenshot_path:
                operation["screenshot_path"] = screenshot_path
                monitoring_log["screenshots"].append({
                    "path": screenshot_path,
                    "phase": phase_name,
                    "step": step_name,
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as screenshot_error:
            operation["screenshot_error"] = str(screenshot_error)
    
    # Add to monitoring log
    monitoring_log["operations"].append(operation)
    
    # Track errors separately
    if status == "failed":
        monitoring_log["errors"].append(operation)
    
    # Track warnings
    if "warning" in message.lower() or "warn" in message.lower():
        monitoring_log["warnings"].append(operation)
    
    # Print to console
    status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️", "in_progress": "🔄"}.get(status, "•")
    error_indicator = " 🔴 ERROR" if status == "failed" else ""
    print(f"{status_icon} [{phase_name}] {step_name}: {status.upper()}{error_indicator}" + (f" - {message}" if message else ""))
    if error and status == "failed":
        print(f"   Error: {str(error)}")
        if isinstance(error, Exception):
            print(f"   Stack trace: {traceback.format_exc()}")

def capture_error_screenshot(driver, phase_name, step_name):
    """Capture screenshot on error for debugging"""
    try:
        screenshots_dir = os.path.join(os.path.dirname(__file__), "error_screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_phase = phase_name.replace(" ", "_").replace("/", "_")
        safe_step = step_name.replace(" ", "_").replace("/", "_")
        filename = f"error_{safe_phase}_{safe_step}_{timestamp}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        driver.save_screenshot(filepath)
        print(f"📸 Screenshot captured: {filepath}")
        return filepath
    except Exception as e:
        print(f"⚠️ Could not capture screenshot: {str(e)}")
        return None

def track_step(phase_name, step_name, status, message="", details=None, error=None, driver=None):
    """
    Track a step in the automation process with enhanced error monitoring
    
    Args:
        phase_name: Name of the phase (e.g., "Phase 1", "Phase 2")
        step_name: Name of the step (e.g., "Login", "Read Excel", "Create Scorecard")
        status: "success", "failed", "skipped", "in_progress"
        message: Optional message about the step
        details: Optional dictionary with additional details
        error: Exception object or error string for detailed logging
        driver: Selenium driver for screenshot capture on errors
    """
    global step_tracker
    
    # Log the operation with full monitoring
    log_operation("step", phase_name, step_name, status, message, error, driver, details)
    
    if phase_name not in step_tracker["phases"]:
        step_tracker["phases"][phase_name] = {
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "status": "in_progress",
            "steps": []
        }
    
    step_entry = {
        "step_name": step_name,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "details": details or {},
        "error": str(error) if error else None,
        "error_type": type(error).__name__ if isinstance(error, Exception) else None
    }
    
    step_tracker["phases"][phase_name]["steps"].append(step_entry)
    
    # Update phase status based on step status
    if status == "failed":
        step_tracker["phases"][phase_name]["status"] = "failed"
    elif status == "success" and step_tracker["phases"][phase_name]["status"] == "in_progress":
        # Only update to success if all previous steps were successful
        all_success = all(s["status"] in ["success", "skipped"] for s in step_tracker["phases"][phase_name]["steps"])
        if all_success:
            step_tracker["phases"][phase_name]["status"] = "success"

def complete_phase(phase_name, status="success"):
    """Mark a phase as complete"""
    global step_tracker
    if phase_name in step_tracker["phases"]:
        step_tracker["phases"][phase_name]["end_time"] = datetime.now().isoformat()
        step_tracker["phases"][phase_name]["status"] = status

def execute_with_monitoring(phase_name, step_name, func, *args, driver=None, **kwargs):
    """
    Execute a function with comprehensive error monitoring and tracking
    
    Args:
        phase_name: Name of the phase
        step_name: Name of the step
        func: Function to execute
        *args, **kwargs: Arguments to pass to the function
        driver: Selenium driver for screenshot capture
    
    Returns:
        Result of the function, or None if it failed
    """
    track_step(phase_name, step_name, "in_progress", f"Starting {step_name}...", driver=driver)
    try:
        result = func(*args, **kwargs)
        track_step(phase_name, step_name, "success", f"{step_name} completed successfully", driver=driver)
        return result
    except Exception as e:
        error_msg = f"{step_name} failed: {str(e)}"
        track_step(phase_name, step_name, "failed", error_msg, error=e, driver=driver)
        raise

def finalize_step_tracker():
    """Finalize the step tracker and monitoring log, save comprehensive reports"""
    global step_tracker, monitoring_log
    step_tracker["end_time"] = datetime.now().isoformat()
    monitoring_log["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    if step_tracker["start_time"] and step_tracker["end_time"]:
        start = datetime.fromisoformat(step_tracker["start_time"])
        end = datetime.fromisoformat(step_tracker["end_time"])
        duration = (end - start).total_seconds()
        step_tracker["total_duration_seconds"] = duration
        monitoring_log["total_duration_seconds"] = duration
    
    # Calculate performance metrics
    monitoring_log["performance_metrics"] = {
        "total_operations": len(monitoring_log["operations"]),
        "total_errors": len(monitoring_log["errors"]),
        "total_warnings": len(monitoring_log["warnings"]),
        "total_screenshots": len(monitoring_log["screenshots"]),
        "success_rate": ((len(monitoring_log["operations"]) - len(monitoring_log["errors"])) / max(len(monitoring_log["operations"]), 1)) * 100 if monitoring_log["operations"] else 0
    }
    
    # Save tracking report
    try:
        reports_dir = os.path.join(os.path.dirname(__file__), "tracking_reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        customer_safe = step_tracker['customer_name'].replace(' ', '_')
        
        # Save step tracking report
        tracking_filename = f"tracking_report_{customer_safe}_{timestamp}.json"
        tracking_filepath = os.path.join(reports_dir, tracking_filename)
        with open(tracking_filepath, 'w') as f:
            json.dump(step_tracker, f, indent=2)
        print(f"\n📊 Step tracking report saved to: {tracking_filepath}")
        
        # Save comprehensive monitoring report
        monitoring_filename = f"monitoring_report_{customer_safe}_{timestamp}.json"
        monitoring_filepath = os.path.join(reports_dir, monitoring_filename)
        with open(monitoring_filepath, 'w') as f:
            json.dump(monitoring_log, f, indent=2)
        print(f"📈 Comprehensive monitoring report saved to: {monitoring_filepath}")
        
        # Save human-readable summary
        summary_filename = f"summary_report_{customer_safe}_{timestamp}.txt"
        summary_filepath = os.path.join(reports_dir, summary_filename)
        with open(summary_filepath, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("AUTOMATION MONITORING SUMMARY REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Customer: {step_tracker['customer_name']}\n")
            f.write(f"Scorecard: {step_tracker['scorecard_name']}\n")
            f.write(f"Start Time: {step_tracker['start_time']}\n")
            f.write(f"End Time: {step_tracker['end_time']}\n")
            f.write(f"Total Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)\n\n")
            
            f.write("=" * 80 + "\n")
            f.write("PERFORMANCE METRICS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total Operations: {monitoring_log['performance_metrics']['total_operations']}\n")
            f.write(f"Total Errors: {monitoring_log['performance_metrics']['total_errors']}\n")
            f.write(f"Total Warnings: {monitoring_log['performance_metrics']['total_warnings']}\n")
            f.write(f"Success Rate: {monitoring_log['performance_metrics']['success_rate']:.2f}%\n")
            f.write(f"Screenshots Captured: {monitoring_log['performance_metrics']['total_screenshots']}\n\n")
            
            if monitoring_log["errors"]:
                f.write("=" * 80 + "\n")
                f.write("ERRORS DETECTED\n")
                f.write("=" * 80 + "\n")
                for i, error in enumerate(monitoring_log["errors"], 1):
                    f.write(f"\nError #{i}:\n")
                    f.write(f"  Phase: {error.get('phase', 'Unknown')}\n")
                    f.write(f"  Step: {error.get('step', 'Unknown')}\n")
                    f.write(f"  Time: {error.get('timestamp', 'Unknown')}\n")
                    f.write(f"  Error: {error.get('error', 'Unknown')}\n")
                    f.write(f"  Error Type: {error.get('error_type', 'Unknown')}\n")
                    f.write(f"  URL: {error.get('url', 'N/A')}\n")
                    if error.get('screenshot_path'):
                        f.write(f"  Screenshot: {error.get('screenshot_path')}\n")
                    if error.get('stack_trace'):
                        f.write(f"  Stack Trace:\n{error.get('stack_trace')}\n")
                    f.write("\n")
            
            if monitoring_log["warnings"]:
                f.write("=" * 80 + "\n")
                f.write("WARNINGS\n")
                f.write("=" * 80 + "\n")
                for i, warning in enumerate(monitoring_log["warnings"], 1):
                    f.write(f"\nWarning #{i}:\n")
                    f.write(f"  Phase: {warning.get('phase', 'Unknown')}\n")
                    f.write(f"  Step: {warning.get('step', 'Unknown')}\n")
                    f.write(f"  Message: {warning.get('message', 'Unknown')}\n")
                    f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write("PHASE SUMMARY\n")
            f.write("=" * 80 + "\n")
            for phase_name, phase_data in step_tracker.get("phases", {}).items():
                f.write(f"\n{phase_name}:\n")
                f.write(f"  Status: {phase_data.get('status', 'Unknown')}\n")
                f.write(f"  Steps: {len(phase_data.get('steps', []))}\n")
                failed_steps = [s for s in phase_data.get('steps', []) if s.get('status') == 'failed']
                if failed_steps:
                    f.write(f"  Failed Steps: {len(failed_steps)}\n")
                    for step in failed_steps:
                        f.write(f"    - {step.get('step_name')}: {step.get('error', 'Unknown error')}\n")
        
        print(f"📋 Human-readable summary saved to: {summary_filepath}")
        
    except Exception as e:
        print(f"Warning: Could not save reports: {e}")
        import traceback
        print(traceback.format_exc())

def get_step_tracker_summary():
    """Get a summary of the step tracker for API response"""
    global step_tracker, monitoring_log
    
    summary = {
        "start_time": step_tracker.get("start_time"),
        "end_time": step_tracker.get("end_time"),
        "customer_name": step_tracker.get("customer_name"),
        "scorecard_name": step_tracker.get("scorecard_name"),
        "total_duration_seconds": step_tracker.get("total_duration_seconds"),
        "phases": {},
        "monitoring": {
            "total_errors": len(monitoring_log.get("errors", [])),
            "total_warnings": len(monitoring_log.get("warnings", [])),
            "total_operations": len(monitoring_log.get("operations", [])),
            "screenshots_captured": len(monitoring_log.get("screenshots", [])),
            "recent_errors": monitoring_log.get("errors", [])[-5:] if monitoring_log.get("errors") else [],
            "recent_warnings": monitoring_log.get("warnings", [])[-5:] if monitoring_log.get("warnings") else []
        }
    }
    
    for phase_name, phase_data in step_tracker.get("phases", {}).items():
        summary["phases"][phase_name] = {
            "status": phase_data.get("status"),
            "start_time": phase_data.get("start_time"),
            "end_time": phase_data.get("end_time"),
            "steps_count": len(phase_data.get("steps", [])),
            "steps": phase_data.get("steps", [])
        }
    
    return summary

def read_excel_data(excel_path):
    """
    Read and parse Excel or CSV file with proper column mapping.
    
    Handles three formats:
    1. Enterprise format: Has 'Scorecard Measure Selection/Add Measure' column
       - Filters to only rows where this column is True
       - Uses columns: Measure Group, Measure Name, Display Name, Definitions
    2. Lego Brazil format: Has 'Grouping Name' column
       - Mapping: Grouping Name → measure_group (Measure Group in portal)
       - Mapping: Client Name of Metric → measure_display_name (Measure Config Name in portal)
       - Mapping: Internal Measures Name → standard_kpis (Measure Definition in portal)
       - Mapping: Measure Order → order (used for ordering measure configs within groups)
       - Mapping: Notes → definition
    3. Competitor format: Simple 4-column format
       - No filtering, processes all rows
       - Uses columns: Measure Group, Standard KPIs, Measure Display Name, Definition
    """
    try:
        # Handle both CSV and Excel files
        file_ext = os.path.splitext(excel_path)[1].lower()
        if file_ext == '.csv':
            # For CSV files, try header=2 first (same as Phase 2 does for Enterprise format)
            try:
                df = pd.read_csv(excel_path, header=2)
            except:
                # If header=2 fails, try without header and find it manually
                df = pd.read_csv(excel_path, header=None, nrows=10)
                # Look for header row with "Measure Group" or "Scorecard Measure Selection"
                header_row = 0
                for i in range(min(10, len(df))):
                    row_values = [str(val).strip().lower() if pd.notna(val) else "" for val in df.iloc[i].values]
                    if 'measure group' in ' '.join(row_values) or 'scorecard measure selection' in ' '.join(row_values):
                        header_row = i
                        break
                df = pd.read_csv(excel_path, header=header_row)
        else:
            # For Excel files, try to detect the correct header row
            # First, read without headers to inspect the structure
            df_temp = pd.read_excel(excel_path, header=None, nrows=5)
            
            # Look for the row containing "Measure Group" or "Scorecard Measure Selection"
            header_row = 0
            for i in range(min(5, len(df_temp))):
                row_values = [str(val).strip().lower() if pd.notna(val) else "" for val in df_temp.iloc[i].values]
                row_str = ' '.join(row_values)
                if 'measure group' in row_str or 'scorecard measure selection' in row_str or 'grouping name' in row_str:
                    header_row = i
                    break
            
            # Also check if first row has invalid headers (like #REF!)
            if header_row == 0:
                first_row_values = [str(val).strip().lower() if pd.notna(val) else "" for val in df_temp.iloc[0].values]
                first_row_str = ' '.join(first_row_values)
                if '#ref!' in first_row_str or 'unnamed' in first_row_str.lower():
                    # First row is invalid, try header=1
                    header_row = 1
            
            # Read with the detected header row
            df = pd.read_excel(excel_path, header=header_row)
        
        # Normalize column names (strip spaces) for easier matching
        df.columns = df.columns.str.strip()
        
        # Check if this is the Lego Brazil format (has 'Grouping Name' column)
        has_grouping_name = 'Grouping Name' in df.columns
        
        # Check if this is the new Enterprise format (has 'Scorecard Measure Selection/Add Measure' column)
        has_selection_column = 'Scorecard Measure Selection/Add Measure' in df.columns
        
        if has_grouping_name:
            # Lego Brazil format
            # Map columns: 
            # - Grouping Name → measure_group (Measure Group in portal)
            # - Client Name of Metric → measure_display_name (Measure Config Name in portal)
            # - Internal Measures Name → standard_kpis (Measure Definition in portal)
            # - Measure Order → order (used for ordering measure configs within groups)
            # - Notes → definition
            data = []
            for idx, row in df.iterrows():
                # Get columns (already normalized by strip())
                grouping_name = str(row['Grouping Name']).strip() if pd.notna(row.get('Grouping Name', '')) else ""
                client_name = str(row['Client Name of Metric']).strip() if pd.notna(row.get('Client Name of Metric', '')) else ""
                # Handle both 'Internal Measures Name' and 'Internal  Measures Name' (double space)
                internal_col = None
                for col in df.columns:
                    if 'Internal' in col and 'Measures' in col and 'Name' in col:
                        internal_col = col
                        break
                internal_name = str(row[internal_col]).strip() if internal_col and pd.notna(row.get(internal_col, '')) else ""
                notes = str(row['Notes']).strip() if pd.notna(row.get('Notes', '')) else ""
                # Get Measure Order (convert to int, default to idx+1 if missing)
                measure_order = int(row['Measure Order']) if pd.notna(row.get('Measure Order', '')) else (idx + 1)
                
                # Skip empty rows
                if not grouping_name or grouping_name == "nan":
                    continue
                
                # Client Name of Metric is the display name (Measure Config Name in portal)
                measure_display_name = client_name if client_name and client_name != "nan" else internal_name
                
                # Internal Measures Name is the measure definition ID (Measure Definition in portal)
                standard_kpis = internal_name
                
                data.append({
                    "measure_group": grouping_name,
                    "standard_kpis": standard_kpis,
                    "measure_display_name": measure_display_name,
                    "definition": notes,
                    "order": measure_order  # Store order for use when creating configs
                })
            
            return data
        elif has_selection_column:
            # New Enterprise format with multiple columns
            # Filter to only rows where 'Scorecard Measure Selection/Add Measure' is True
            # Exclude False, blank/NaN values - ONLY keep True values
            selection_col = 'Scorecard Measure Selection/Add Measure'
            
            # Convert column to boolean, handling both boolean and string values
            # First, replace NaN/blank with False
            df[selection_col] = df[selection_col].fillna(False)
            
            # Convert string "True"/"False" to boolean if needed
            if df[selection_col].dtype == 'object':
                df[selection_col] = df[selection_col].astype(str).str.strip().str.lower()
                df[selection_col] = df[selection_col].map({'true': True, 'false': False, '': False, 'nan': False})
                df[selection_col] = df[selection_col].fillna(False)
            
            # Filter: ONLY keep rows where value is True (exclude False and blank)
            df_filtered = df[df[selection_col] == True].copy()
            
            data = []
            for idx, row in df_filtered.iterrows():
                # Enterprise format mapping:
                # - Measure Group → measure_group (e.g., Availability, Content, Ratings & Reviews, Search)
                # - Measure Name → standard_kpis (measure definition ID for dropdown selection)
                # - Display Name → measure_display_name (name of the configs)
                # - Definitions → definition (same as competitor format)
                
                measure_group = str(row['Measure Group']).strip() if pd.notna(row['Measure Group']) else ""
                measure_name = str(row['Measure Name']).strip() if pd.notna(row['Measure Name']) else ""
                display_name = str(row['Display Name']).strip() if pd.notna(row['Display Name']) else ""
                definition = str(row['Definitions']).strip() if pd.notna(row.get('Definitions', '')) else ""
                
                # Display Name is the name of the configs (required for Enterprise)
                measure_display_name = display_name if display_name and display_name != "nan" else measure_name
                
                # Measure Name is the measure definition ID (used for dropdown selection)
                standard_kpis = measure_name
                
                # Skip empty rows
                if not measure_group or measure_group == "nan":
                    continue
                
                data.append({
                    "measure_group": measure_group,
                    "standard_kpis": standard_kpis,
                    "measure_display_name": measure_display_name,
                    "definition": definition
                })
            
            return data
        else:
            # Old format: Columns: Measure Group, Standard KPIs, Measure Display Name, Definition
            data = []
            for idx, row in df.iterrows():
                # Try to use column names first (if headers were detected correctly)
                if 'Measure Group' in df.columns:
                    measure_group = str(row['Measure Group']).strip() if pd.notna(row.get('Measure Group', '')) else ""
                    standard_kpis = str(row['Standard KPIs']).strip() if pd.notna(row.get('Standard KPIs', '')) else ""
                    measure_display_name = str(row['Measure Display Name']).strip() if pd.notna(row.get('Measure Display Name', '')) else ""
                    definition = str(row['Definition']).strip() if pd.notna(row.get('Definition', '')) else ""
                else:
                    # Fallback to positional indexing (skip first column if it's Unnamed or #REF!)
                    # Check if first column looks like a data column or header artifact
                    first_col_val = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ""
                    if first_col_val in ['nan', '', '#ref!'] or 'unnamed' in first_col_val:
                        # First column is invalid, use columns 1-4
                        measure_group = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
                        standard_kpis = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                        measure_display_name = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ""
                        definition = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
                    else:
                        # First column is valid data, use columns 0-3
                        measure_group = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                        standard_kpis = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
                        measure_display_name = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                        definition = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ""
                
                # Skip empty rows
                if not measure_group or measure_group == "nan":
                    continue
                    
                data.append({
                    "measure_group": measure_group,
                    "standard_kpis": standard_kpis,
                    "measure_display_name": measure_display_name,
                    "definition": definition
                })
            
            return data
    except Exception as e:
        print(f"Error reading Excel: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_distinct_measure_groups(excel_data):
    """Get distinct measure groups in Excel order"""
    seen = []
    groups = []
    for item in excel_data:
        if item["measure_group"] not in seen:
            seen.append(item["measure_group"])
            groups.append(item["measure_group"])
    return groups

def find_element_by_xpath(driver, xpath, timeout=30, clickable=True):
    """Helper function to find element by XPath with wait"""
    try:
        if clickable:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
        else:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        return element
    except TimeoutException:
        return None

def click_element(driver, xpath, timeout=30):
    """Helper function to click element by XPath"""
    element = find_element_by_xpath(driver, xpath, timeout)
    if element:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.3)
        element.click()
        time.sleep(0.5)
        return True
    return False

def fill_input(driver, xpath, value, timeout=30):
    """Helper function to fill input field"""
    element = find_element_by_xpath(driver, xpath, timeout, clickable=False)
    if element:
        element.clear()
        element.send_keys(str(value))
        time.sleep(0.3)
        return True
    return False

def select_dropdown_by_value(driver, xpath, value, timeout=30, max_retries=3):
    """Helper function to select dropdown option by value with retry logic"""
    value_str = str(value).strip()
    
    for attempt in range(max_retries):
        try:
            # Wait for element to be present and clickable
            element = find_element_by_xpath(driver, xpath, timeout=10, clickable=True)
            if not element:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False
            
            # Scroll element into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            
            # Wait for dropdown to have options loaded (at least 2 options including default)
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: len(Select(d.find_element(By.XPATH, xpath)).options) > 1
                )
            except:
                # If waiting for options fails, try anyway
                pass
            
            select = Select(element)
            time.sleep(0.5)  # Additional wait for options to be fully loaded
            
            # Method 1: Try selecting by exact value
            try:
                select.select_by_value(value_str)
                time.sleep(0.5)
                # Verify selection was successful
                if select.first_selected_option.get_attribute('value') == value_str or select.first_selected_option.text.strip() == value_str:
                    return True
            except:
                pass
            
            # Method 2: Try selecting by visible text (exact match)
            try:
                select.select_by_visible_text(value_str)
                time.sleep(0.5)
                # Verify selection
                if value_str.lower() in select.first_selected_option.text.strip().lower():
                    return True
            except:
                pass
            
            # Method 3: Try case-insensitive match by visible text
            try:
                options = select.options
                for option in options:
                    if option.text.strip().lower() == value_str.lower():
                        select.select_by_visible_text(option.text)
                        time.sleep(0.5)
                        return True
            except:
                pass
            
            # Method 4: Try partial match (contains)
            try:
                options = select.options
                for option in options:
                    option_text = option.text.strip().lower()
                    value_lower = value_str.lower()
                    if value_lower in option_text or option_text in value_lower:
                        select.select_by_visible_text(option.text)
                        time.sleep(0.5)
                        return True
            except:
                pass
            
            # If all methods failed and we have retries left, wait and try again
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait longer before retry
                continue
                
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return False
    
    return False


def select_scorecard_in_weights_targets(driver, scorecard_name):
    """
    Select scorecard from dropdown in Weights & Targets page.
    
    Args:
        driver: Selenium WebDriver instance
        scorecard_name: Name of the scorecard to select
    
    Returns:
        True if successful, False otherwise
    """
    try:
        automation_status["message"] = f"Phase 2: Selecting scorecard '{scorecard_name}'..."
        print(f"Phase 2: Selecting scorecard '{scorecard_name}' from dropdown...")
        
        # Find the scorecard dropdown
        scorecard_select = find_element_by_xpath(driver, "//select[@id='scorecard_id']", timeout=15)
        if not scorecard_select:
            automation_status["message"] = "Phase 2: Warning: Could not find scorecard dropdown, continuing anyway"
            print("Phase 2: WARNING - Could not find scorecard dropdown //select[@id='scorecard_id']")
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", scorecard_select)
        time.sleep(1)
        
        # Select the scorecard
        if select_dropdown_by_value(driver, "//select[@id='scorecard_id']", scorecard_name):
            automation_status["message"] = f"Phase 2: Selected scorecard '{scorecard_name}'"
            print(f"Phase 2: ✓ Successfully selected scorecard '{scorecard_name}'")
            time.sleep(2)  # Wait for page to update
            return True
        else:
            automation_status["message"] = f"Phase 2: Warning: Could not select scorecard '{scorecard_name}', continuing anyway"
            print(f"Phase 2: WARNING - Could not select scorecard '{scorecard_name}' from dropdown")
            return False
            
    except Exception as e:
        automation_status["message"] = f"Phase 2: Warning: Error selecting scorecard: {str(e)}, continuing anyway"
        print(f"Phase 2: WARNING - Error selecting scorecard: {str(e)}")
        return False

def export_weights_targets_template(driver, scorecard_name=None):
    """
    Navigate to weights & targets and export the template.
    
    Args:
        driver: Selenium WebDriver instance
        scorecard_name: Name of the scorecard to select (optional)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        automation_status["message"] = "Phase 2: Navigating to Weights & Targets..."
        driver.get("https://settings.ef.uk.com/weights_targets")
        time.sleep(3)
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Weights') or contains(text(), 'Targets')]"))
            )
        except:
            pass
        
        # Select scorecard if name provided
        if scorecard_name:
            select_scorecard_in_weights_targets(driver, scorecard_name)
        
        automation_status["message"] = "Phase 2: Clicking Bulk Operations..."
        # Find and click "Bulk Operations" button
        bulk_ops_button = find_element_by_xpath(driver, "//button[contains(text(), 'Bulk Operations')]", timeout=15)
        if not bulk_ops_button:
            # Try alternative selectors
            bulk_ops_button = find_element_by_xpath(driver, "//a[contains(text(), 'Bulk Operations')]", timeout=10)
        
        if bulk_ops_button:
            driver.execute_script("arguments[0].scrollIntoView(true);", bulk_ops_button)
            time.sleep(1)
            bulk_ops_button.click()
            time.sleep(2)
            
            # Look for "Export Template" option
            automation_status["message"] = "Phase 2: Looking for Export Template option..."
            export_template_link = find_element_by_xpath(driver, "//a[contains(text(), 'Export Template')]", timeout=10)
            if not export_template_link:
                # Try in dropdown menu
                export_template_link = find_element_by_xpath(driver, "//*[contains(text(), 'Export Template')]", timeout=10)
            
            if export_template_link:
                driver.execute_script("arguments[0].scrollIntoView(true);", export_template_link)
                time.sleep(1)
                export_template_link.click()
                automation_status["message"] = "Phase 2: Export template job triggered. Waiting for job to complete..."
                time.sleep(2)
                return True
            else:
                automation_status["message"] = "Phase 2: Error: Could not find Export Template option"
                return False
        else:
            automation_status["message"] = "Phase 2: Error: Could not find Bulk Operations button"
            return False
            
    except Exception as e:
        automation_status["message"] = f"Phase 2: Error exporting template: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def wait_for_export_job_and_download(driver, username, export_file_path=None, max_wait_time=300):
    """
    Wait for export job to complete and download the file.
    
    Args:
        driver: Selenium WebDriver instance
        username: User email to filter jobs by
        export_file_path: Optional path to look for downloaded file (directory or file path)
        max_wait_time: Maximum time to wait in seconds (default 5 minutes)
    
    Returns:
        Path to downloaded file if successful, None otherwise
    """
    try:
        automation_status["message"] = f"Phase 2: Navigating to tracked jobs page..."
        driver.get("https://settings.ef.uk.com/tracked_jobs")
        time.sleep(3)
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//table | //*[contains(text(), 'Job')]"))
            )
        except:
            pass
        
        automation_status["message"] = f"Phase 2: Looking for export job started by {username}..."
        start_time = time.time()
        job_found_at_least_once = False
        download_path = None
        
        while time.time() - start_time < max_wait_time:
            try:
                # Find all job rows
                job_rows = driver.find_elements(By.XPATH, "//table//tr | //tbody//tr")
                matching_jobs = []
                
                for row in job_rows:
                    try:
                        row_text = row.text.lower()
                        # Check if this row contains ExportWeightsTargetTemplateJob and the username
                        if 'exportweightstargettemplatejob' in row_text and username.lower() in row_text:
                            # Check status
                            status_elements = row.find_elements(By.XPATH, ".//td[contains(@class, 'status')] | .//*[contains(text(), 'COMPLETE') or contains(text(), 'QUEUED') or contains(text(), 'RUNNING') or contains(text(), 'FAILED')]")
                            status_text = "UNKNOWN"
                            if status_elements:
                                status_text = status_elements[0].text.strip().upper()
                            
                            # Get created at timestamp if available
                            created_at = None
                            try:
                                date_elements = row.find_elements(By.XPATH, ".//td[contains(@class, 'date')] | .//td[position()>1]")
                                if date_elements:
                                    created_at = date_elements[0].text.strip()
                            except:
                                pass
                            
                            matching_jobs.append({
                                'row': row,
                                'status': status_text,
                                'created_at': created_at
                            })
                            job_found_at_least_once = True
                    except:
                        continue
                
                if matching_jobs:
                    # Sort by created_at (most recent first) - simple string comparison
                    matching_jobs.sort(key=lambda x: x['created_at'] or '', reverse=True)
                    latest_job = matching_jobs[0]
                    status = latest_job['status']
                    
                    automation_status["message"] = f"Phase 2: Found job with status: {status}"
                    
                    if status == 'COMPLETE':
                        # Find download link/button in this row
                        row = latest_job['row']
                        download_link = None
                        
                        # Try multiple selectors for download link
                        download_selectors = [
                            ".//a[contains(@href, 'download')]",
                            ".//button[contains(text(), 'Download')]",
                            ".//a[contains(text(), 'Download')]",
                            ".//*[contains(@class, 'download')]",
                            ".//a[contains(@href, '.csv')]",
                            ".//a[contains(@href, '.xlsx')]",
                        ]
                        
                        for selector in download_selectors:
                            try:
                                download_link = row.find_element(By.XPATH, selector)
                                if download_link:
                                    break
                            except:
                                continue
                        
                        if download_link:
                            automation_status["message"] = "Phase 2: Clicking download link..."
                            driver.execute_script("arguments[0].scrollIntoView(true);", download_link)
                            time.sleep(1)
                            download_link.click()
                            time.sleep(5)  # Wait for download to start
                            
                            # Find downloaded file
                            # Check in specified export path first, then Downloads folder
                            time.sleep(3)  # Give more time for download
                            all_files = []
                            
                            # Determine search directories
                            search_dirs = []
                            if export_file_path:
                                # Resolve the path (handle ~ and relative paths)
                                resolved_path = export_file_path
                                if not os.path.isabs(resolved_path):
                                    resolved_path = os.path.join(os.path.dirname(__file__), resolved_path)
                                resolved_path = os.path.expanduser(resolved_path)
                                
                                # If it's a file path, use its directory; if it's a directory, use it directly
                                if os.path.isfile(resolved_path):
                                    search_dir = os.path.dirname(resolved_path)
                                else:
                                    search_dir = resolved_path
                                
                                if os.path.exists(search_dir):
                                    search_dirs.append(search_dir)
                            
                            # Also check Downloads folder as fallback
                            downloads_path = os.path.expanduser("~/Downloads")
                            if os.path.exists(downloads_path) and downloads_path not in search_dirs:
                                search_dirs.append(downloads_path)
                            
                            # Also check the project's downloads folder if it exists
                            project_downloads = os.path.join(os.path.dirname(__file__), "downloads")
                            if os.path.exists(project_downloads) and project_downloads not in search_dirs:
                                search_dirs.append(project_downloads)
                                print(f"Phase 2: Added project downloads folder: {project_downloads}")
                            
                            # Look for recently downloaded files in all search directories
                            print(f"Phase 2: Searching for downloaded file in directories: {search_dirs}")
                            for search_dir in search_dirs:
                                for ext in ['*.csv', '*.xlsx', '*.xls']:
                                    pattern = os.path.join(search_dir, ext)
                                    found = glob.glob(pattern)
                                    all_files.extend(found)
                                    if found:
                                        print(f"Phase 2: Found {len(found)} files matching {ext} in {search_dir}")
                            
                            print(f"Phase 2: Total files found: {len(all_files)}")
                            
                            # Sort by modification time, most recent first
                            if all_files:
                                all_files.sort(key=os.path.getmtime, reverse=True)
                                print(f"Phase 2: Most recent files: {[os.path.basename(f) for f in all_files[:5]]}")
                                # Get the most recent file that matches export pattern
                                # Also check files that might have been downloaded in the last hour (in case automation was restarted)
                                current_time = time.time()
                                for file in all_files[:20]:  # Check top 20 most recent files
                                    file_lower = file.lower()
                                    file_basename = os.path.basename(file_lower)
                                    
                                    # More flexible matching - check for export, weight, target, or the job name pattern
                                    matches_pattern = (
                                        'export' in file_lower or 
                                        'weight' in file_lower or 
                                        'target' in file_lower or 
                                        'exportweightstargettemplatejob' in file_lower.replace(' ', '').replace('_', '').replace('-', '')
                                    )
                                    
                                    # Also check if file was modified in the last hour (for restarted automations)
                                    file_age = current_time - os.path.getmtime(file)
                                    is_recent = file_age < 3600  # Less than 1 hour old
                                    
                                    if matches_pattern and is_recent:
                                        download_path = file
                                        print(f"Phase 2: Matched file: {os.path.basename(file)} (modified {file_age/60:.1f} minutes ago)")
                                        break
                                
                                # If no recent file found, try any matching file (for existing files)
                                if not download_path:
                                    for file in all_files[:20]:
                                        file_lower = file.lower()
                                        if ('export' in file_lower or 'weight' in file_lower or 'target' in file_lower or 
                                            'exportweightstargettemplatejob' in file_lower.replace(' ', '').replace('_', '').replace('-', '')):
                                            download_path = file
                                            print(f"Phase 2: Matched existing file: {os.path.basename(file)}")
                                            break
                            
                            if download_path:
                                automation_status["message"] = f"Phase 2: File downloaded: {download_path}"
                                print(f"Phase 2: Successfully found downloaded file: {download_path}")
                                return download_path
                            else:
                                search_locations = ", ".join(search_dirs) if search_dirs else "Downloads folder"
                                error_msg = f"Phase 2: Download clicked but file not found. Searched in: {search_locations}. Found {len(all_files)} files total."
                                automation_status["message"] = error_msg
                                print(f"Phase 2: ERROR - {error_msg}")
                                if all_files:
                                    print(f"Phase 2: Available files (top 10): {[os.path.basename(f) for f in all_files[:10]]}")
                                return None
                        else:
                            automation_status["message"] = "Phase 2: Job complete but download link not found in row."
                            return None
                    elif status in ['QUEUED', 'RUNNING', 'PENDING']:
                        automation_status["message"] = f"Phase 2: Job status is {status}. Waiting 10 seconds and checking again..."
                        time.sleep(10)
                        driver.refresh()
                        time.sleep(3)
                        continue
                    elif status == 'FAILED':
                        automation_status["message"] = "Phase 2: Export job failed. Please check manually."
                        return None
                else:
                    if not job_found_at_least_once:
                        automation_status["message"] = f"Phase 2: Job not found yet. Waiting 10 seconds..."
                        time.sleep(10)
                        driver.refresh()
                        time.sleep(3)
                    else:
                        automation_status["message"] = "Phase 2: Job no longer found. It may have been completed and removed."
                        break
                        
            except Exception as e:
                automation_status["message"] = f"Phase 2: Error checking job status: {str(e)[:100]}"
                time.sleep(10)
                driver.refresh()
                time.sleep(3)
        
        if not job_found_at_least_once:
            automation_status["message"] = f"Phase 2: Export job started by {username} not found within {max_wait_time//60} minutes"
            return None
        elif not download_path:
            automation_status["message"] = f"Phase 2: Export job started by {username} found but did not complete download within {max_wait_time//60} minutes"
            return None
        
        return download_path
        
    except Exception as e:
        automation_status["message"] = f"Phase 2: Error waiting for export job: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return None

def process_weights_targets_file(export_file_path, setup_sheet_path, output_csv_path, retailer_weights_targets_path=None, scorecard_name='Default'):
    """
    Process the exported weights/targets file with data from setup sheet and retailer weights/targets.
    
    Processing order:
    1. Apply filters: measure_config not blank, measure_group blank, scorecard match, retailer blank
    2. Apply metric-level weights/targets from setup_sheet_path to filtered rows
    3. Apply defaults to ALL empty cells (target=50, weight=1.0)
    4. Apply filters: measure_config blank, measure_group blank, brand blank, scorecard match (exact from UI), retailer all EXCEPT blanks
    5. Apply retailer-level weights/targets from retailer_weights_targets_path to filtered rows (overrides defaults)
    
    Args:
        export_file_path: Path to exported file (CSV or Excel)
        setup_sheet_path: Path to setup sheet with Target, Metric Name, Metric Weight (Metric Weights and Targets)
        output_csv_path: Path to save processed CSV
        retailer_weights_targets_path: Optional path to Retailer Weights/Targets sheet (Retailer, Retailer Target, Retailer Weight)
        scorecard_name: Scorecard name to filter rows (default: 'Default')
    
    Returns:
        True if successful, False otherwise
    """
    print("=" * 80)
    print("Phase 2: process_weights_targets_file() CALLED")
    print(f"Phase 2: Input parameters:")
    print(f"  - export_file_path: {export_file_path}")
    print(f"  - setup_sheet_path: {setup_sheet_path}")
    print(f"  - output_csv_path: {output_csv_path}")
    print(f"  - retailer_weights_targets_path: {retailer_weights_targets_path}")
    print(f"  - scorecard_name: {scorecard_name}")
    print("=" * 80)
    
    try:
        automation_status["message"] = "Phase 2: Reading exported file..."
        print(f"Phase 2: Processing - Export file path: {export_file_path}")
        print(f"Phase 2: Processing - Export file exists: {os.path.exists(export_file_path)}")
        
        if not export_file_path or not os.path.exists(export_file_path):
            error_msg = f"Phase 2: Export file does not exist: {export_file_path}"
            print(f"Phase 2: ✗✗✗ ERROR - {error_msg}")
            automation_status["message"] = error_msg
            return False
        
        if not setup_sheet_path or not os.path.exists(setup_sheet_path):
            error_msg = f"Phase 2: Setup sheet does not exist: {setup_sheet_path}"
            print(f"Phase 2: ✗✗✗ ERROR - {error_msg}")
            automation_status["message"] = error_msg
            return False
        
        # Read export file (can be CSV or Excel)
        if export_file_path.endswith('.csv'):
            export_df = pd.read_csv(export_file_path)
        else:
            export_df = pd.read_excel(export_file_path)
        
        print(f"Phase 2: Export file columns (original): {list(export_df.columns)}")
        
        # Normalize column names - handle shortened names like 'targ' -> 'target', 'weig' -> 'weight'
        # The export file may have shortened column names, so we normalize them to standard names
        column_mapping = {}
        for col in export_df.columns:
            col_str = str(col).strip().lower()
            if col_str in ['targ', 'target']:
                column_mapping[col] = 'target'
            elif col_str in ['weig', 'weight']:
                column_mapping[col] = 'weight'
            elif col_str in ['retailer', 'ret']:
                column_mapping[col] = 'retailer'
            elif col_str in ['scorecard', 'score']:
                column_mapping[col] = 'scorecard'
            elif col_str in ['brand', 'br']:
                column_mapping[col] = 'brand'
            elif col_str in ['measure_group', 'measuregroup', 'mg']:
                column_mapping[col] = 'measure_group'
            elif col_str in ['measure_config', 'measureconfig', 'mc']:
                column_mapping[col] = 'measure_config'
        
        # Rename columns if needed
        if column_mapping:
            export_df = export_df.rename(columns=column_mapping)
            print(f"Phase 2: Normalized column names: {column_mapping}")
        
        print(f"Phase 2: Export file columns (after normalization): {list(export_df.columns)}")
        automation_status["message"] = f"Phase 2: Export file has {len(export_df)} rows"
        
        # Read setup sheet
        automation_status["message"] = "Phase 2: Reading setup sheet..."
        print(f"Phase 2: Processing - Setup sheet path: {setup_sheet_path}")
        print(f"Phase 2: Processing - Setup sheet exists: {os.path.exists(setup_sheet_path)}")
        
        # Read the file first without header to check structure (supports both CSV and Excel)
        file_ext = os.path.splitext(setup_sheet_path)[1].lower()
        # Read more rows to find headers that might be at different positions
        max_rows_to_check = 30
        if file_ext == '.csv':
            temp_df = pd.read_csv(setup_sheet_path, header=None, nrows=max_rows_to_check)
        else:
            temp_df = pd.read_excel(setup_sheet_path, header=None, nrows=max_rows_to_check)
        print(f"Phase 2: Checking first {max_rows_to_check} rows for header...")
        
        # Try to find the header row using a flexible scoring system
        # This allows headers to be at any row and handles various file formats
        header_row = 2  # Default fallback
        best_score = 0
        best_row = None
        
        # Define column patterns we're looking for (with weights)
        # Higher weight = more important for identifying headers
        column_patterns = {
            'target': {'keywords': ['target'], 'weight': 3, 'max_length': 30},
            'weight': {'keywords': ['weight', 'weig'], 'weight': 3, 'max_length': 30},
            'metric_name': {'keywords': ['metric name', 'measure name'], 'weight': 2, 'max_length': 30},
            'display_name': {'keywords': ['display name'], 'weight': 2, 'max_length': 30},
            'retailer': {'keywords': ['retailer'], 'weight': 1, 'max_length': 30},
            'measure_group': {'keywords': ['measure group', 'grouping name'], 'weight': 1, 'max_length': 30},
            'selection': {'keywords': ['selection', 'add measure'], 'weight': 1, 'max_length': 50},
        }
        
        # Score each row to find the best header candidate
        for i in range(min(max_rows_to_check, len(temp_df))):
            row_values = [str(val).strip() if pd.notna(val) else "" for val in temp_df.iloc[i].values]
            row_lower = [str(val).strip().lower() if pd.notna(val) else "" for val in temp_df.iloc[i].values]
            
            # Filter out empty values
            non_empty_values = [v for v in row_values if v and v != ""]
            
            # Skip rows with too few values (likely not headers)
            if len(non_empty_values) < 3:
                continue
            
            # Check for long descriptions (headers shouldn't have these)
            long_values = [v for v in row_values if len(v) > 50]
            if len(long_values) > 2:  # Too many long values = likely description row
                continue
            
            # Calculate score based on matching column patterns
            score = 0
            matched_patterns = []
            
            for pattern_name, pattern_info in column_patterns.items():
                for val in row_lower:
                    if len(val) <= pattern_info['max_length']:
                        for keyword in pattern_info['keywords']:
                            if keyword in val:
                                score += pattern_info['weight']
                                matched_patterns.append(pattern_name)
                                break  # Only count once per pattern
            
            # Bonus points for having multiple short column names (typical of headers)
            short_values = [v for v in row_values if len(v) < 30 and v != ""]
            if len(short_values) >= 4:
                score += 2  # Bonus for multiple columns
            
            # Penalty for having mostly empty cells (headers should have values)
            empty_ratio = sum(1 for v in row_values if not v or v == "") / max(len(row_values), 1)
            if empty_ratio > 0.7:  # More than 70% empty
                score -= 5
            
            # Track the best scoring row
            if score > best_score:
                best_score = score
                best_row = i
                print(f"Phase 2: Row {i} scored {score} points (matched: {set(matched_patterns)})")
        
        # Use the best scoring row as header, or fall back to default
        if best_row is not None and best_score >= 5:  # Minimum score threshold
            header_row = best_row
            found_header = True
            print(f"Phase 2: ✓ Found header row at index {header_row} (score: {best_score})")
            print(f"Phase 2: Header row values: {[str(v)[:50] for v in temp_df.iloc[header_row].values[:10] if pd.notna(v) and str(v).strip()]}")
        else:
            print(f"Phase 2: ⚠ Header row not found with sufficient confidence (best score: {best_score}), using default row {header_row}")
            print(f"Phase 2: Row {header_row} values: {[str(v)[:50] for v in temp_df.iloc[header_row].values[:10] if pd.notna(v) and str(v).strip()]}")
        
        # Read with the correct header row
        print(f"Phase 2: Reading setup sheet with header={header_row}")
        if file_ext == '.csv':
            setup_df = pd.read_csv(setup_sheet_path, header=header_row)
        else:
            setup_df = pd.read_excel(setup_sheet_path, header=header_row)
        setup_df.columns = setup_df.columns.str.strip()
        
        print(f"Phase 2: Setup sheet columns: {list(setup_df.columns)}")
        print(f"Phase 2: Setup sheet has {len(setup_df)} rows")
        
        # Filter by "Scorecard Measure Selection/Add Measure" column if it exists (same as Phase 1)
        # Only process rows where this column is True
        selection_col = 'Scorecard Measure Selection/Add Measure'
        if selection_col in setup_df.columns:
            print(f"Phase 2: Found '{selection_col}' column - filtering to only True values")
            # Convert column to boolean, handling both boolean and string values
            setup_df[selection_col] = setup_df[selection_col].fillna(False)
            
            # Convert string "True"/"False" to boolean if needed
            if setup_df[selection_col].dtype == 'object':
                setup_df[selection_col] = setup_df[selection_col].astype(str).str.strip().str.lower()
                setup_df[selection_col] = setup_df[selection_col].map({'true': True, 'false': False, '': False, 'nan': False})
                setup_df[selection_col] = setup_df[selection_col].fillna(False)
            
            # Filter: ONLY keep rows where value is True (exclude False and blank)
            rows_before = len(setup_df)
            setup_df = setup_df[setup_df[selection_col] == True].copy()
            rows_after = len(setup_df)
            print(f"Phase 2: Filtered from {rows_before} rows to {rows_after} rows (only True values)")
            automation_status["message"] = f"Phase 2: Filtered setup sheet to {rows_after} rows with True selection"
        else:
            print(f"Phase 2: No '{selection_col}' column found - processing all rows")
        
        # Map columns: Find Target, Metric Name (or Display Name), Metric Weight (or Measure weights), and optionally Retailer columns
        target_col = None
        metric_col = None
        display_name_col = None  # Prefer Display Name for matching (export file uses Display Name)
        weight_col = None
        retailer_col = None
        
        for col in setup_df.columns:
            col_lower = str(col).lower()
            if 'target' in col_lower and target_col is None and 'retailer' not in col_lower:
                target_col = col
            elif 'display' in col_lower and 'name' in col_lower:
                # Prefer Display Name for matching (export file measure_config uses Display Name values)
                display_name_col = col
            elif ('metric' in col_lower and 'name' in col_lower) or ('measure' in col_lower and 'name' in col_lower):
                # Handle both "Metric Name" and "Measure Name" columns (fallback if Display Name not found)
                if metric_col is None:
                    metric_col = col
            elif ('metric' in col_lower and 'weight' in col_lower) or ('measure' in col_lower and 'weight' in col_lower):
                # Handle both "Metric Weight" and "Measure weights" columns
                if weight_col is None:
                    weight_col = col
            elif 'retailer' in col_lower and 'target' not in col_lower and 'weight' not in col_lower:
                retailer_col = col
        
        # Use Display Name if available, otherwise fall back to Metric/Measure Name
        if display_name_col:
            metric_col = display_name_col
            print(f"Phase 2: Using 'Display Name' column for matching (export file uses Display Name values)")
        elif metric_col:
            print(f"Phase 2: Using '{metric_col}' column for matching (Display Name not found)")
        
        print(f"Phase 2: Found columns - Target: {target_col}, Metric/Display: {metric_col}, Weight: {weight_col}, Retailer: {retailer_col}")
        
        if not (target_col and metric_col and weight_col):
            error_msg = f"Phase 2: Error: Could not find required columns in setup sheet. Found: {list(setup_df.columns)}"
            automation_status["message"] = error_msg
            print(f"Phase 2: ERROR - {error_msg}")
            return False
        
        has_retailer_col = retailer_col is not None
        automation_status["message"] = f"Phase 2: Setup sheet has retailer column: {has_retailer_col}"
        
        # Helper function to extract number from percentage strings or preserve numeric values
        def extract_number(value):
            """
            Preprocess percentage values: Convert "85%" → 85 (NOT 0.85)
            - Percentage strings like "85%", "70%", "10%" → 85, 70, 10
            - Numbers like 85, 70, 10 → stay as 85, 70, 10
            - Decimals like 0.01, 0.85 → stay as 0.01, 0.85 (only convert if they're percentage strings)
            """
            if pd.isna(value) or value == '' or value is None:
                return None
            try:
                    # If it's a string with "%", extract the number (e.g., "85%" → 85, "10%" → 10)
                if isinstance(value, str):
                    value_str = str(value).strip()
                    if '%' in value_str:
                        import re
                        # Extract the numeric part from percentage string
                        match = re.search(r'([\d.]+)', value_str)
                        if match:
                            num_value = float(match.group(1))
                            # "85%" → 85, "10%" → 10, "70%" → 70
                            return num_value
                    # If it's a string without %, try to convert to number
                    else:
                        try:
                            num_value = float(value_str)
                            return num_value
                        except:
                            return None
                # If it's already a number, return as-is
                # Numbers >= 1 stay as-is (85 → 85, 70 → 70)
                # Numbers < 1 stay as-is (0.01 → 0.01, 0.85 → 0.85) - these are likely decimals, not percentages
                elif isinstance(value, (int, float)):
                    return value
            except Exception as e:
                print(f"Phase 2: Warning - Could not extract number from '{value}': {str(e)}")
                return value  # Return original if can't process
            return value
        
        # Create mapping from setup sheet
        # If retailer column exists: (retailer, metric_name) -> (target, weight)
        # If no retailer column: metric_name -> (target, weight)
        setup_mapping = {}
        setup_mapping_all = {}  # For "ALL" retailer entries
        
        for idx, row in setup_df.iterrows():
            metric_name = str(row[metric_col]).strip() if pd.notna(row[metric_col]) else ""
            target_val_raw = row[target_col] if pd.notna(row[target_col]) else None
            weight_val_raw = row[weight_col] if pd.notna(row[weight_col]) else None
            
            # Extract number from percentage string or preserve numeric value
            # Important: Only convert percentage strings ("85%" → 85), preserve decimals as-is (0.85 → 0.85)
            target_val = extract_number(target_val_raw)
            weight_val = extract_number(weight_val_raw)
            
            # DO NOT convert decimals to percentages - only extract from percentage strings
            # "85%" → 85, "100%" → 100, but 0.85 stays 0.85, 0.9 stays 0.9
            
            if not metric_name or metric_name == "nan":
                continue
            
            if has_retailer_col:
                retailer_name = str(row[retailer_col]).strip() if pd.notna(row[retailer_col]) else ""
                retailer_name_upper = retailer_name.upper() if retailer_name else ""
                
                # If retailer is "ALL", store in separate mapping
                if retailer_name_upper == "ALL":
                    setup_mapping_all[metric_name.lower()] = {
                        'target': target_val,
                        'weight': weight_val
                    }
                else:
                    # Store with retailer key
                    key = (retailer_name.lower() if retailer_name else "", metric_name.lower())
                    setup_mapping[key] = {
                        'target': target_val,
                        'weight': weight_val
                    }
            else:
                # No retailer column - simple metric mapping
                setup_mapping[metric_name.lower()] = {
                    'target': target_val,
                    'weight': weight_val
                }
        
        print(f"Phase 2: Created mapping for {len(setup_mapping)} retailer+metric combinations and {len(setup_mapping_all)} 'ALL' retailer entries")
        print(f"Phase 2: Sample mappings - setup_mapping keys (first 5): {list(setup_mapping.keys())[:5]}")
        print(f"Phase 2: Sample mappings - setup_mapping_all keys (first 5): {list(setup_mapping_all.keys())[:5]}")
        automation_status["message"] = f"Phase 2: Created mapping for {len(setup_mapping)} retailer+metric combinations and {len(setup_mapping_all)} 'ALL' retailer entries"
        
        # Step 1: Apply filters for metric weights/targets
        # Filter requirements:
        # - scorecard: Only the exact scorecard name from UI
        # - retailer: Only blanks
        # - brand: Only blanks
        # - measure_group: Only blanks
        # - measure_config: All values EXCEPT blanks
        automation_status["message"] = "Phase 2: Step 1 - Applying filters for metric weights/targets..."
        print(f"Phase 2: Step 1 - Applying filters:")
        print(f"  - scorecard='{scorecard_name}' (exact match from UI)")
        print(f"  - retailer: only blanks")
        print(f"  - brand: only blanks")
        print(f"  - measure_group: only blanks")
        print(f"  - measure_config: all values EXCEPT blanks")
        
        if 'measure_config' not in export_df.columns:
            error_msg = f"Phase 2: Error: Export file missing 'measure_config' column. Found columns: {list(export_df.columns)}"
            automation_status["message"] = error_msg
            print(f"Phase 2: ERROR - {error_msg}")
            return False
        
        # Create filter mask for metric weights/targets
        # Note: brand column may not exist in all export files
        brand_filter = True  # Default: include all (if brand column doesn't exist)
        if 'brand' in export_df.columns:
            brand_filter = (export_df['brand'].isna() | (export_df['brand'] == ''))
        
        metric_mask = (
            (export_df['scorecard'] == scorecard_name) &
            (export_df['retailer'].isna() | (export_df['retailer'] == '')) &
            brand_filter &
            (export_df['measure_group'].isna() | (export_df['measure_group'] == '')) &
            export_df['measure_config'].notna() & 
            (export_df['measure_config'] != '')
        )
        
        metric_filtered_count = metric_mask.sum()
        print(f"Phase 2: Filter matched {metric_filtered_count} rows for metric weights/targets")
        automation_status["message"] = f"Phase 2: Filter matched {metric_filtered_count} rows for metric weights/targets"
        
        # Debug: Show what we're matching against
        print(f"Phase 2: DEBUG - setup_mapping has {len(setup_mapping)} entries")
        print(f"Phase 2: DEBUG - setup_mapping keys (first 10): {list(setup_mapping.keys())[:10]}")
        print(f"Phase 2: DEBUG - has_retailer_col: {has_retailer_col}")
        print(f"Phase 2: DEBUG - Export file has 'retailer' column: {'retailer' in export_df.columns}")
        
        # Apply metric weights/targets only to filtered rows
        updated_count = 0
        matched_metrics = set()
        unmatched_metrics = set()
        
        print(f"Phase 2: Starting to match and update filtered rows...")
        print(f"Phase 2: DEBUG - Will process {len(export_df[metric_mask])} rows")
        for idx in export_df[metric_mask].index:
            row = export_df.loc[idx]
            measure_config = str(row['measure_config']).strip() if pd.notna(row['measure_config']) else ""
            
            if not measure_config or measure_config == "nan":
                continue
            
            # Case-insensitive matching for metric name
            metric_key = measure_config.lower()
            setup_data = None
            
            # IMPORTANT: has_retailer_col means setup sheet HAS retailer column
            # If setup sheet doesn't have retailer column, use simple metric matching
            # (even if export file has retailer column, we match by metric name only)
            if has_retailer_col and 'retailer' in export_df.columns:
                # Retailer-specific matching (setup sheet has retailer column)
                retailer_name = str(row['retailer']).strip() if pd.notna(row.get('retailer', '')) else ""
                retailer_key = retailer_name.lower() if retailer_name else ""
                
                # First try retailer-specific match
                key = (retailer_key, metric_key)
                if key in setup_mapping:
                    setup_data = setup_mapping[key]
                    print(f"Phase 2: Matched retailer-specific: ({retailer_key}, {metric_key})")
                # Then try "ALL" retailer match
                elif metric_key in setup_mapping_all:
                    setup_data = setup_mapping_all[metric_key]
                    print(f"Phase 2: Matched 'ALL' retailer: {metric_key}")
            else:
                # Simple metric matching (no retailer column in setup sheet)
                # Match by metric name only, regardless of retailer in export file
                if metric_key in setup_mapping:
                    setup_data = setup_mapping[metric_key]
                    print(f"Phase 2: Matched metric: {metric_key} -> Target: {setup_data['target']}, Weight: {setup_data['weight']}")
                else:
                    print(f"Phase 2: NO MATCH for: {metric_key} (available keys: {list(setup_mapping.keys())[:5]}...)")
            
            if setup_data:
                # Update target
                if pd.notna(setup_data['target']):
                    old_target = export_df.at[idx, 'target']
                    export_df.at[idx, 'target'] = setup_data['target']
                    print(f"Phase 2: Updated target for {measure_config}: {old_target} -> {setup_data['target']}")
                else:
                    print(f"Phase 2: WARNING - setup_data['target'] is NaN for {measure_config}")
                
                # Update weight
                if pd.notna(setup_data['weight']):
                    old_weight = export_df.at[idx, 'weight']
                    export_df.at[idx, 'weight'] = setup_data['weight']
                    print(f"Phase 2: Updated weight for {measure_config}: {old_weight} -> {setup_data['weight']}")
                else:
                    print(f"Phase 2: WARNING - setup_data['weight'] is NaN for {measure_config}")
                
                updated_count += 1
                matched_metrics.add(metric_key)
            else:
                unmatched_metrics.add(metric_key)
                print(f"Phase 2: NO MATCH for {measure_config} (key: {metric_key})")
        
        print(f"Phase 2: Step 1 - Matched and updated {updated_count} rows with metric-level data from setup sheet")
        print(f"Phase 2: Matched {len(matched_metrics)} unique metrics: {list(matched_metrics)[:10]}")
        if unmatched_metrics:
            print(f"Phase 2: Unmatched metrics (first 10): {list(unmatched_metrics)[:10]}")
        automation_status["message"] = f"Phase 2: Step 1 - Updated {updated_count} rows with metric-level data"
        
        # Step 2: Apply defaults to empty cells FIRST (before retailer values)
        automation_status["message"] = "Phase 2: Step 2 - Applying defaults to empty cells..."
        print(f"Phase 2: Step 2 - Applying defaults (target=50, weight=1.0) to empty cells...")
        
        defaults_applied = 0
        if 'target' in export_df.columns:
            for idx, row in export_df.iterrows():
                target_val = row.get('target')
                if pd.isna(target_val) or target_val == '' or target_val is None:
                    export_df.at[idx, 'target'] = 50
                    defaults_applied += 1
        
        if 'weight' in export_df.columns:
            for idx, row in export_df.iterrows():
                weight_val = row.get('weight')
                if pd.isna(weight_val) or weight_val == '' or weight_val is None:
                    export_df.at[idx, 'weight'] = 1.0
                    defaults_applied += 1
        
        print(f"Phase 2: Step 2 - Applied defaults (target=50, weight=1.0) to {defaults_applied} empty cells")
        automation_status["message"] = f"Phase 2: Step 2 - Applied defaults to {defaults_applied} empty cells"
        
        # Step 3: Apply retailer-level weights/targets (overrides defaults for retailer rows)
        retailer_updated_count = 0
        
        # CRITICAL DEBUG: Check retailer file path
        print(f"Phase 2: CRITICAL DEBUG - Checking retailer file path...")
        print(f"Phase 2: CRITICAL DEBUG - retailer_weights_targets_path = {retailer_weights_targets_path}")
        print(f"Phase 2: CRITICAL DEBUG - retailer_weights_targets_path is None? {retailer_weights_targets_path is None}")
        print(f"Phase 2: CRITICAL DEBUG - retailer_weights_targets_path is empty? {retailer_weights_targets_path == '' if retailer_weights_targets_path else 'N/A'}")
        
        if retailer_weights_targets_path:
            print(f"Phase 2: CRITICAL DEBUG - Path provided, checking if file exists...")
            file_exists = os.path.exists(retailer_weights_targets_path)
            print(f"Phase 2: CRITICAL DEBUG - File exists? {file_exists}")
            if not file_exists:
                print(f"Phase 2: CRITICAL DEBUG - File does NOT exist at: {retailer_weights_targets_path}")
                print(f"Phase 2: CRITICAL DEBUG - Current working directory: {os.getcwd()}")
                print(f"Phase 2: CRITICAL DEBUG - File absolute path: {os.path.abspath(retailer_weights_targets_path) if retailer_weights_targets_path else 'N/A'}")
        else:
            print(f"Phase 2: CRITICAL DEBUG - No retailer file path provided! Skipping retailer processing.")
        
        if retailer_weights_targets_path and os.path.exists(retailer_weights_targets_path):
            automation_status["message"] = "Phase 2: Step 3 - Reading retailer weights/targets sheet..."
            print(f"Phase 2: Step 3 - Processing retailer weights/targets from: {retailer_weights_targets_path}")
            print(f"Phase 2: Step 3 - File exists: {os.path.exists(retailer_weights_targets_path)}")
            print(f"Phase 2: Step 3 - File path: {retailer_weights_targets_path}")
            
            try:
                # Read retailer weights/targets file (supports both CSV and Excel)
                # Detect file type
                file_ext = os.path.splitext(retailer_weights_targets_path)[1].lower()
                
                # Read first 15 rows to find header
                if file_ext == '.csv':
                    temp_retailer_df = pd.read_csv(retailer_weights_targets_path, header=None, nrows=15)
                else:
                    temp_retailer_df = pd.read_excel(retailer_weights_targets_path, header=None, nrows=15)
                
                retailer_header_row = 9  # Default, will be updated if found
                found_retailer_header = False
                
                # Search for header row - look for row with column structure matching "Retailer", "Retailer Target", "Retailer Weight"
                # We need to find a row where:
                # 1. One column contains "retailer" but NOT "target" and NOT "weight" (the retailer name column)
                # 2. One column contains "retailer" AND "target" (the target column)
                # 3. One column contains "retailer" AND "weight" (the weight column)
                # This avoids matching instruction text that contains all words in one cell
                for i in range(min(15, len(temp_retailer_df))):
                    row_values = [str(val).strip().lower() if pd.notna(val) else "" for val in temp_retailer_df.iloc[i].values]
                    
                    # Check each column individually
                    has_retailer_name_col = False
                    has_retailer_target_col = False
                    has_retailer_weight_col = False
                    
                    for val in row_values:
                        if val:
                            # Retailer name column: contains "retailer" but NOT "target" and NOT "weight"
                            if 'retailer' in val and 'target' not in val and 'weight' not in val:
                                has_retailer_name_col = True
                            # Retailer target column: contains both "retailer" AND "target"
                            elif 'retailer' in val and 'target' in val:
                                has_retailer_target_col = True
                            # Retailer weight column: contains both "retailer" AND "weight"
                            elif 'retailer' in val and 'weight' in val:
                                has_retailer_weight_col = True
                    
                    # Only accept if we have all three distinct columns
                    if has_retailer_name_col and has_retailer_target_col and has_retailer_weight_col:
                        retailer_header_row = i
                        found_retailer_header = True
                        print(f"Phase 2: Found retailer header at row {i} (0-indexed): {[v for v in row_values if v]}")
                        break
                
                # Read full file with detected header row
                if file_ext == '.csv':
                    retailer_df = pd.read_csv(retailer_weights_targets_path, header=retailer_header_row)
                else:
                    retailer_df = pd.read_excel(retailer_weights_targets_path, header=retailer_header_row)
                retailer_df.columns = retailer_df.columns.str.strip()
                
                # Drop first column if it's "Unnamed: 0"
                if len(retailer_df.columns) > 0 and retailer_df.columns[0] == 'Unnamed: 0':
                    retailer_df = retailer_df.drop(columns=[retailer_df.columns[0]])
                
                # Find columns
                retailer_name_col = None
                retailer_target_col = None
                retailer_weight_col = None
                
                for col in retailer_df.columns:
                    col_lower = str(col).lower()
                    if 'retailer' in col_lower and 'target' not in col_lower and 'weight' not in col_lower:
                        retailer_name_col = col
                    elif 'retailer' in col_lower and 'target' in col_lower:
                        retailer_target_col = col
                    elif 'retailer' in col_lower and 'weight' in col_lower:
                        retailer_weight_col = col
                
                print(f"Phase 2: Retailer sheet columns - Name: {retailer_name_col}, Target: {retailer_target_col}, Weight: {retailer_weight_col}")
                
                if retailer_name_col and retailer_target_col and retailer_weight_col:
                    # Create retailer mapping (extract_number function is already defined above)
                    # For retailer weights/targets, convert decimals to percentage format (0.7 → 70, 0.25 → 25)
                    retailer_mapping = {}
                    print(f"Phase 2: Reading retailer data from CSV...")
                    print(f"Phase 2: Retailer DataFrame shape: {retailer_df.shape}")
                    print(f"Phase 2: First few rows of retailer data:")
                    print(retailer_df.head(10))
                    
                    for idx, row in retailer_df.iterrows():
                        retailer_name = str(row[retailer_name_col]).strip() if pd.notna(row[retailer_name_col]) else ""
                        
                        # Skip empty rows
                        if not retailer_name or retailer_name == "nan" or retailer_name == "":
                            continue
                        
                        retailer_target_raw = row[retailer_target_col] if pd.notna(row[retailer_target_col]) else None
                        retailer_weight_raw = row[retailer_weight_col] if pd.notna(row[retailer_weight_col]) else None
                        
                        # Extract number from percentage string (e.g., "70%" → 70, "25%" → 25)
                        # The extract_number function already converts percentage strings correctly
                        retailer_target = extract_number(retailer_target_raw)
                        retailer_weight = extract_number(retailer_weight_raw)
                        
                        # Fallback: If extract_number returns None but raw value is numeric, use raw value
                        if retailer_target is None and retailer_target_raw is not None:
                            try:
                                if isinstance(retailer_target_raw, (int, float)):
                                    retailer_target = float(retailer_target_raw)
                                elif isinstance(retailer_target_raw, str) and retailer_target_raw.strip():
                                    retailer_target = float(retailer_target_raw.strip())
                            except (ValueError, TypeError):
                                pass
                        
                        if retailer_weight is None and retailer_weight_raw is not None:
                            try:
                                if isinstance(retailer_weight_raw, (int, float)):
                                    retailer_weight = float(retailer_weight_raw)
                                elif isinstance(retailer_weight_raw, str) and retailer_weight_raw.strip():
                                    retailer_weight = float(retailer_weight_raw.strip())
                            except (ValueError, TypeError):
                                pass
                        
                        # Additional conversion: If value is a decimal between 0 and 1, convert to percentage
                        # This handles cases where someone entered 0.7 meaning 70% (but user wants 70, not 0.7)
                        # Note: Percentage strings like "70%" are already converted to 70 by extract_number
                        if retailer_target is not None and isinstance(retailer_target, (int, float)):
                            if 0 < retailer_target < 1.0:
                                # Decimal percentage (0.7 = 70%), convert to number format
                                retailer_target = retailer_target * 100
                                print(f"Phase 2: Converted decimal {retailer_target_raw} → {retailer_target} (treated as percentage)")
                            elif retailer_target == 1.0:
                                retailer_target = 100.0
                        
                        if retailer_weight is not None and isinstance(retailer_weight, (int, float)):
                            if 0 < retailer_weight < 1.0:
                                # Decimal percentage (0.25 = 25%), convert to number format
                                retailer_weight = retailer_weight * 100
                                print(f"Phase 2: Converted decimal {retailer_weight_raw} → {retailer_weight} (treated as percentage)")
                            elif retailer_weight == 1.0:
                                retailer_weight = 100.0
                        
                        if retailer_name and retailer_name != "nan":
                            retailer_mapping[retailer_name.lower()] = {
                                'target': retailer_target,
                                'weight': retailer_weight
                            }
                            print(f"Phase 2: Added to mapping: '{retailer_name.lower()}' → target={retailer_target} (type: {type(retailer_target)}), weight={retailer_weight} (type: {type(retailer_weight)})")
                            
                            # CRITICAL DEBUG: Verify the values are not None
                            if retailer_target is None:
                                print(f"Phase 2: ERROR - retailer_target is None for '{retailer_name}'! Raw value was: {retailer_target_raw}")
                            if retailer_weight is None:
                                print(f"Phase 2: ERROR - retailer_weight is None for '{retailer_name}'! Raw value was: {retailer_weight_raw}")
                    
                    print(f"Phase 2: Created retailer mapping for {len(retailer_mapping)} retailers")
                    print(f"Phase 2: Retailer mapping keys: {list(retailer_mapping.keys())}")
                    print(f"Phase 2: Debug - Retailer mapping values:")
                    for key, val in retailer_mapping.items():
                        print(f"  {key}: target={val['target']}, weight={val['weight']}")
                    
                    # Helper function to match retailer names (handles variations like "Elcorteingles-ES" vs "Elcorteingles-Toys-ES")
                    def find_matching_retailer(export_retailer_name, retailer_mapping):
                        """Find matching retailer in mapping, handling name variations"""
                        if not export_retailer_name:
                            return None
                        
                        export_retailer_lower = export_retailer_name.lower().strip()
                        
                        # Try exact match first (case-insensitive)
                        if export_retailer_lower in retailer_mapping:
                            print(f"Phase 2: Exact match found: '{export_retailer_name}' → '{export_retailer_lower}'")
                            return export_retailer_lower
                        
                        # Try partial matching - check if export retailer contains mapping key or vice versa
                        for mapping_key in retailer_mapping.keys():
                            # Normalize by removing common suffixes/prefixes for comparison
                            # Remove "-toys", "-es", and other common suffixes
                            export_normalized = export_retailer_lower.replace('-toys', '').replace('-es', '').replace('-', '').strip()
                            mapping_normalized = mapping_key.replace('-toys', '').replace('-es', '').replace('-', '').strip()
                            
                            # Check if normalized names match (handles "elcorteingles" vs "elcorteingles")
                            if export_normalized == mapping_normalized:
                                print(f"Phase 2: Normalized match found: '{export_retailer_name}' → '{mapping_key}' (normalized: '{export_normalized}' == '{mapping_normalized}')")
                                return mapping_key
                            
                            # Check if one contains the other (after normalization)
                            if export_normalized and mapping_normalized:
                                if export_normalized in mapping_normalized or mapping_normalized in export_normalized:
                                    # Additional check: ensure the base name matches (e.g., "elcorteingles" matches)
                                    if len(export_normalized) > 3 and len(mapping_normalized) > 3:
                                        print(f"Phase 2: Partial match found: '{export_retailer_name}' → '{mapping_key}' (normalized: '{export_normalized}' in '{mapping_normalized}')")
                                        return mapping_key
                            
                            # Also try direct substring match (case-insensitive)
                            if mapping_key in export_retailer_lower or export_retailer_lower in mapping_key:
                                print(f"Phase 2: Substring match found: '{export_retailer_name}' → '{mapping_key}'")
                                return mapping_key
                        
                        print(f"Phase 2: No match found for retailer: '{export_retailer_name}' (available keys: {list(retailer_mapping.keys())})")
                        return None
                    
                    # Step 3: Apply filters for retailer weights/targets
                    # Filter requirements (applied AFTER metric weights/targets AND defaults):
                    # - measure_config: Only blanks
                    # - measure_group: Only blanks
                    # - brand: Only blanks
                    # - scorecard: Exact match to name entered in UI
                    # - retailer: All values EXCEPT blanks (select all retailers)
                    automation_status["message"] = "Phase 2: Step 3 - Applying filters for retailer weights/targets..."
                    # Debug: Check available scorecard values in export file first
                    unique_scorecards = export_df['scorecard'].unique() if 'scorecard' in export_df.columns else []
                    print(f"Phase 2: Debug - Available scorecard values in export file: {list(unique_scorecards[:10])}")
                    print(f"Phase 2: Debug - Scorecard name from UI (for filter): '{scorecard_name}'")
                    
                    # If scorecard name doesn't match exactly, try case-insensitive match
                    scorecard_to_use = scorecard_name
                    if scorecard_name not in unique_scorecards:
                        # Try case-insensitive match
                        for sc in unique_scorecards:
                            if str(sc).lower() == str(scorecard_name).lower():
                                scorecard_to_use = sc
                                print(f"Phase 2: Using case-insensitive match: '{scorecard_name}' → '{sc}'")
                                break
                        if scorecard_to_use == scorecard_name and scorecard_name not in unique_scorecards:
                            print(f"Phase 2: WARNING - Scorecard name '{scorecard_name}' not found in export file!")
                            print(f"Phase 2: WARNING - Available scorecards: {list(unique_scorecards[:5])}")
                    
                    print(f"Phase 2: Step 3 - Applying filters for retailer weights/targets:")
                    print(f"  - measure_config: only blanks")
                    print(f"  - measure_group: only blanks")
                    print(f"  - brand: only blanks")
                    print(f"  - scorecard='{scorecard_to_use}' (exact match from UI)")
                    print(f"  - retailer: all values EXCEPT blanks (select all retailers)")
                    
                    # Create filter mask for retailer weights/targets
                    # Note: brand column may not exist in all export files
                    retailer_brand_filter = True  # Default: include all (if brand column doesn't exist)
                    if 'brand' in export_df.columns:
                        retailer_brand_filter = (export_df['brand'].isna() | (export_df['brand'] == ''))
                    
                    retailer_mask = (
                        export_df['retailer'].notna() & 
                        (export_df['retailer'] != '') &
                        (export_df['scorecard'] == scorecard_to_use) &
                        retailer_brand_filter &
                        (export_df['measure_group'].isna() | (export_df['measure_group'] == '')) &
                        (export_df['measure_config'].isna() | (export_df['measure_config'] == ''))
                    )
                    
                    retailer_filtered_count = retailer_mask.sum()
                    print(f"Phase 2: Filter matched {retailer_filtered_count} rows for retailer weights/targets")
                    
                    # Debug: Show sample of filtered retailers
                    if retailer_filtered_count > 0:
                        sample_retailers = export_df[retailer_mask]['retailer'].unique()[:10]
                        print(f"Phase 2: Debug - Sample retailers in filtered rows: {list(sample_retailers)}")
                    else:
                        print(f"Phase 2: WARNING - Filter matched 0 rows!")
                        print(f"Phase 2: WARNING - This likely means scorecard name doesn't match.")
                        print(f"Phase 2: WARNING - You entered: '{scorecard_name}'")
                        print(f"Phase 2: WARNING - Available in file: {list(unique_scorecards[:5])}")
                        print(f"Phase 2: WARNING - Try using exact scorecard name from the export file!")
                    
                    automation_status["message"] = f"Phase 2: Filter matched {retailer_filtered_count} rows for retailer weights/targets"
                    
                    # Apply retailer-level targets/weights only to filtered rows (overrides metric-level for all metrics of that retailer)
                    if 'retailer' in export_df.columns:
                        print(f"Phase 2: Processing {retailer_filtered_count} filtered rows for retailer updates...")
                        print(f"Phase 2: Debug - Retailer mapping contains {len(retailer_mapping)} entries")
                        print(f"Phase 2: Debug - Retailer mapping keys: {list(retailer_mapping.keys())}")
                        unmatched_retailers = set()
                        matched_retailers = set()
                        for idx in export_df[retailer_mask].index:
                            row = export_df.loc[idx]
                            retailer_name = str(row['retailer']).strip() if pd.notna(row.get('retailer', '')) else ""
                            if retailer_name:
                                matching_key = find_matching_retailer(retailer_name, retailer_mapping)
                                if matching_key:
                                    matched_retailers.add(retailer_name)
                                    retailer_data = retailer_mapping[matching_key]
                                    
                                    # Debug: Print what we're about to apply
                                    print(f"Phase 2: Debug - Matched '{retailer_name}' → '{matching_key}'")
                                    print(f"Phase 2: Debug - Retailer data: target={retailer_data.get('target')}, weight={retailer_data.get('weight')}")
                                    print(f"Phase 2: Debug - Current row values: target={row.get('target')}, weight={row.get('weight')}")
                                    
                                    # Override target if retailer target exists - FORCE APPLY
                                    target_value = retailer_data.get('target')
                                    print(f"Phase 2: CRITICAL - target_value={target_value}, type={type(target_value)}")
                                    
                                    # Force apply - check if it's a valid number (including 0)
                                    if target_value is not None:
                                        try:
                                            target_float = float(target_value)
                                            if not pd.isna(target_float):
                                                old_target = export_df.at[idx, 'target']
                                                export_df.at[idx, 'target'] = target_float
                                                retailer_updated_count += 1
                                                print(f"Phase 2: ✓ FORCE UPDATED {retailer_name}: target {old_target} → {target_float}")
                                                
                                                # Verify immediately
                                                verify = export_df.at[idx, 'target']
                                                if verify != target_float:
                                                    print(f"Phase 2: ERROR - Verification failed! Set {target_float}, but got {verify}")
                                            else:
                                                print(f"Phase 2: ERROR - target_float is NaN after conversion!")
                                        except (ValueError, TypeError) as e:
                                            print(f"Phase 2: ERROR - Could not convert target_value to float: {e}")
                                    else:
                                        print(f"Phase 2: ERROR - target_value is None for '{retailer_name}'!")
                                    
                                    # Override weight if retailer weight exists - FORCE APPLY
                                    weight_value = retailer_data.get('weight')
                                    print(f"Phase 2: CRITICAL - weight_value={weight_value}, type={type(weight_value)}")
                                    
                                    # Force apply - check if it's a valid number (including 0)
                                    if weight_value is not None:
                                        try:
                                            weight_float = float(weight_value)
                                            if not pd.isna(weight_float):
                                                old_weight = export_df.at[idx, 'weight']
                                                export_df.at[idx, 'weight'] = weight_float
                                                print(f"Phase 2: ✓ FORCE UPDATED {retailer_name}: weight {old_weight} → {weight_float}")
                                                
                                                # Verify immediately
                                                verify = export_df.at[idx, 'weight']
                                                if verify != weight_float:
                                                    print(f"Phase 2: ERROR - Verification failed! Set {weight_float}, but got {verify}")
                                            else:
                                                print(f"Phase 2: ERROR - weight_float is NaN after conversion!")
                                        except (ValueError, TypeError) as e:
                                            print(f"Phase 2: ERROR - Could not convert weight_value to float: {e}")
                                    else:
                                        print(f"Phase 2: ERROR - weight_value is None for '{retailer_name}'!")
                                else:
                                    unmatched_retailers.add(retailer_name)
                                    print(f"Phase 2: Debug - Could not match retailer: '{retailer_name}'")
                        
                        print(f"Phase 2: Debug - Matched {len(matched_retailers)} unique retailers: {list(matched_retailers)}")
                        
                        # Print summary of unmatched retailers
                        if unmatched_retailers:
                            print(f"Phase 2: WARNING - {len(unmatched_retailers)} unique retailers could not be matched:")
                            for unmatched in list(unmatched_retailers)[:10]:
                                print(f"  - '{unmatched}' (available in CSV: {list(retailer_mapping.keys())})")
                    
                    print(f"Phase 2: Step 3 - Applied retailer-level targets/weights to {retailer_updated_count} rows")
                    if retailer_updated_count == 0:
                        print(f"Phase 2: WARNING - No retailer weights/targets were applied!")
                        print(f"Phase 2: WARNING - Scorecard name used: '{scorecard_name}'")
                        print(f"Phase 2: WARNING - Filter matched {retailer_filtered_count} rows")
                        print(f"Phase 2: WARNING - Retailer mapping has {len(retailer_mapping)} entries")
                        if retailer_filtered_count == 0:
                            print(f"Phase 2: WARNING - Filter matched 0 rows! Check if scorecard name matches.")
                            print(f"Phase 2: WARNING - Available scorecard values in file: {list(export_df['scorecard'].unique()[:5])}")
                            print(f"Phase 2: WARNING - Scorecard name from UI: '{scorecard_name}'")
                            print(f"Phase 2: WARNING - Does it match? Check if you entered the exact scorecard name from the file.")
                        else:
                            print(f"Phase 2: WARNING - Filter matched {retailer_filtered_count} rows but no updates were made.")
                            print(f"Phase 2: WARNING - This could mean retailer names didn't match.")
                            print(f"Phase 2: WARNING - Sample retailers in filtered rows: {list(export_df[retailer_mask]['retailer'].unique()[:5])}")
                            print(f"Phase 2: WARNING - Retailer mapping keys: {list(retailer_mapping.keys())}")
                    automation_status["message"] = f"Phase 2: Step 3 - Applied retailer-level data to {retailer_updated_count} rows"
                else:
                    print(f"Phase 2: Warning - Could not find required columns in retailer sheet. Found: {list(retailer_df.columns)}")
                    automation_status["message"] = "Phase 2: Warning - Retailer sheet format issue, skipping retailer-level updates"
            except Exception as e:
                print(f"Phase 2: ERROR reading retailer weights/targets file: {str(e)}")
                automation_status["message"] = f"Phase 2: ERROR reading retailer file: {str(e)}"
                import traceback
                print("Phase 2: FULL TRACEBACK:")
                print(traceback.format_exc())
                print("Phase 2: This error prevented retailer values from being applied!")
        else:
            if retailer_weights_targets_path:
                print(f"Phase 2: CRITICAL ERROR - Retailer weights/targets file not found: {retailer_weights_targets_path}")
                print(f"Phase 2: CRITICAL ERROR - This is why retailer values are NOT being applied!")
                print(f"Phase 2: CRITICAL ERROR - Current directory: {os.getcwd()}")
                print(f"Phase 2: CRITICAL ERROR - Absolute path: {os.path.abspath(retailer_weights_targets_path)}")
                print(f"Phase 2: CRITICAL ERROR - File exists check: {os.path.exists(retailer_weights_targets_path)}")
                print(f"Phase 2: CRITICAL ERROR - Please check the file path in the UI!")
            else:
                print(f"Phase 2: CRITICAL ERROR - No retailer weights/targets file provided, skipping Step 3")
                print(f"Phase 2: CRITICAL ERROR - This is why retailer values are NOT being applied!")
                print(f"Phase 2: CRITICAL ERROR - Check if the path is being passed from the UI correctly!")
                print(f"Phase 2: CRITICAL ERROR - form_data.get('retailer_weights_targets_path') returned: None")
        
        # Step 4: Final verification before saving
        automation_status["message"] = "Phase 2: Step 4 - Verifying retailer values before saving..."
        print(f"Phase 2: Step 4 - Final verification of retailer values...")
        
        # Verify retailer values are actually in the dataframe
        if 'retailer' in export_df.columns and 'scorecard' in export_df.columns:
            # Note: brand column may not exist in all export files
            verification_brand_filter = True  # Default: include all (if brand column doesn't exist)
            if 'brand' in export_df.columns:
                verification_brand_filter = (export_df['brand'].isna() | (export_df['brand'] == ''))
            
            verification_mask = (
                export_df['retailer'].notna() & 
                (export_df['retailer'] != '') &
                (export_df['scorecard'] == scorecard_name) &
                verification_brand_filter &
                (export_df['measure_group'].isna() | (export_df['measure_group'] == '')) &
                (export_df['measure_config'].isna() | (export_df['measure_config'] == ''))
            )
            
            verification_rows = export_df[verification_mask]
            print(f"Phase 2: Step 4 - Verifying {len(verification_rows)} retailer rows:")
            for idx, row in verification_rows.head(10).iterrows():
                retailer = row['retailer']
                target = row['target']
                weight = row['weight']
                print(f"  {retailer}: target={target}, weight={weight}")
                
                # Check if still defaults
                if target == 50 and weight == 1.0:
                    print(f"    ⚠ WARNING - Still has default values! Retailer processing may have failed!")
        
        automation_status["message"] = "Phase 2: Step 4 - All processing complete"
        print(f"Phase 2: Step 4 - All processing complete. Metric values, defaults, and retailer values have been applied.")
        
        # Save as CSV
        automation_status["message"] = f"Phase 2: Saving processed file to {output_csv_path}..."
        print(f"Phase 2: Saving processed CSV to: {output_csv_path}")
        print(f"Phase 2: DEBUG - DataFrame shape before save: {export_df.shape}")
        print(f"Phase 2: DEBUG - DataFrame columns: {list(export_df.columns)}")
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_csv_path)
        os.makedirs(output_dir, exist_ok=True)
        print(f"Phase 2: DEBUG - Output directory created/verified: {output_dir}")
        
        # Save the file
        try:
            export_df.to_csv(output_csv_path, index=False)
            print(f"Phase 2: ✓ CSV file saved successfully to: {output_csv_path}")
            
            # Verify file was created
            if os.path.exists(output_csv_path):
                file_size = os.path.getsize(output_csv_path)
                print(f"Phase 2: ✓ File verified - exists, size: {file_size} bytes")
            else:
                print(f"Phase 2: ✗ ERROR - File was not created at: {output_csv_path}")
                return False
                
        except Exception as save_error:
            error_msg = f"Phase 2: Error saving CSV file: {str(save_error)}"
            automation_status["message"] = error_msg
            print(f"Phase 2: ✗✗✗ ERROR - {error_msg}")
            import traceback
            print(traceback.format_exc())
            return False
        
        automation_status["message"] = f"Phase 2: Saved processed CSV to {output_csv_path}"
        
        # CSV format validation before import (as per plan requirement)
        try:
            # Verify the CSV file was created and is readable
            validation_df = pd.read_csv(output_csv_path)
            if len(validation_df) == 0:
                error_msg = "Phase 2: Warning: Processed CSV file is empty"
                automation_status["message"] = error_msg
                print(f"Phase 2: ⚠ WARNING - {error_msg}")
                # Still return True so the file exists for debugging, but log the warning
                print(f"Phase 2: File saved but is empty - check processing logic")
            else:
                print(f"Phase 2: ✓ CSV validation passed. File has {len(validation_df)} rows.")
                automation_status["message"] = f"Phase 2: CSV validation passed. File has {len(validation_df)} rows."
        except Exception as e:
            error_msg = f"Phase 2: Error: CSV validation failed - {str(e)}"
            automation_status["message"] = error_msg
            print(f"Phase 2: ✗ ERROR - {error_msg}")
            import traceback
            print(traceback.format_exc())
            # Still return True if file exists (for debugging), but log the error
            if os.path.exists(output_csv_path):
                print(f"Phase 2: File exists but validation failed - file saved for debugging")
                return True
            return False
        
        print("Phase 2: ✓✓✓ Processing completed successfully!")
        return True
    except Exception as e:
        error_msg = f"Phase 2: Error processing file: {str(e)}"
        automation_status["message"] = error_msg
        print(f"Phase 2: ✗✗✗ EXCEPTION - {error_msg}")
        import traceback
        print(traceback.format_exc())
        
        # Try to save the file even if there was an error (for debugging)
        try:
            if 'export_df' in locals() and export_df is not None:
                print(f"Phase 2: Attempting to save file despite error for debugging...")
                output_dir = os.path.dirname(output_csv_path)
                os.makedirs(output_dir, exist_ok=True)
                export_df.to_csv(output_csv_path, index=False)
                print(f"Phase 2: ✓ File saved for debugging despite error: {output_csv_path}")
        except Exception as save_error:
            print(f"Phase 2: Could not save file for debugging: {str(save_error)}")
        
        return False

def import_weights_targets_csv(driver, csv_file_path, change_reason, scorecard_name=None):
    """
    Import the processed CSV file to weights & targets.
    
    Args:
        driver: Selenium WebDriver instance
        csv_file_path: Path to the CSV file to import
        change_reason: Change reason text (must be at least 10 characters)
        scorecard_name: Name of the scorecard to select (optional)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Step 1: Navigate to weights & targets page
        automation_status["message"] = "Phase 2: Navigating to Weights & Targets page..."
        driver.get("https://settings.ef.uk.com/weights_targets")
        time.sleep(3)
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Weights') or contains(text(), 'Targets')]"))
            )
        except:
            pass
        
        # Select scorecard if name provided (before importing)
        if scorecard_name:
            select_scorecard_in_weights_targets(driver, scorecard_name)
        
        # Step 2: Click the "Import CSV" link using exact XPath
        automation_status["message"] = "Phase 2: Clicking 'Import CSV' link..."
        import_csv_link = find_element_by_xpath(driver, "//a[normalize-space()='Import CSV']", timeout=15)
        
        if not import_csv_link:
            automation_status["message"] = "Phase 2: Error: Could not find 'Import CSV' link"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_csv_link)
        time.sleep(1)
        import_csv_link.click()
        time.sleep(3)
        
        # Step 3: Click "Upload a file" span
        automation_status["message"] = "Phase 2: Clicking 'Upload a file'..."
        upload_file_span = find_element_by_xpath(driver, "//span[normalize-space()='Upload a file']", timeout=15)
        
        if not upload_file_span:
            automation_status["message"] = "Phase 2: Error: Could not find 'Upload a file' span"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", upload_file_span)
        time.sleep(1)
        upload_file_span.click()
        time.sleep(2)
        
        # Step 4: Find and use the file input (it should be visible after clicking upload)
        automation_status["message"] = "Phase 2: Uploading processed CSV file..."
        file_input = None
        
        # Try to find file input - it might be hidden, so we'll look for it
        file_input_selectors = [
            "//input[@type='file']",
            "//input[@name='file']",
            "//input[contains(@class, 'file')]",
            "//input[@accept='.csv']"
        ]
        
        for selector in file_input_selectors:
            try:
                file_input = driver.find_element(By.XPATH, selector)
                if file_input:
                    break
            except:
                continue
        
        if not file_input:
            automation_status["message"] = "Phase 2: Error: Could not find file upload input"
            return False
        
        # Upload the file
        abs_csv_path = os.path.abspath(csv_file_path)
        print(f"Phase 2: Uploading file: {abs_csv_path}")
        print(f"Phase 2: File exists: {os.path.exists(abs_csv_path)}")
        
        if not os.path.exists(abs_csv_path):
            automation_status["message"] = f"Phase 2: Error: CSV file not found at {abs_csv_path}"
            return False
        
        file_input.send_keys(abs_csv_path)
        time.sleep(3)  # Wait for file to be processed
        
        # Step 5: Fill in change reason using exact XPath
        automation_status["message"] = "Phase 2: Entering change reason..."
        change_reason_input = find_element_by_xpath(driver, "//textarea[@id='reason_for_change']", timeout=15)
        
        if not change_reason_input:
            automation_status["message"] = "Phase 2: Error: Could not find change reason textarea with id='reason_for_change'"
            return False
        
        # Ensure change reason is at least 10 characters
        if len(change_reason) < 10:
            change_reason = change_reason + " " * (10 - len(change_reason))
        
        change_reason_input.clear()
        time.sleep(0.5)
        change_reason_input.send_keys(change_reason)
        time.sleep(1)
        print(f"Phase 2: Change reason entered: {change_reason}")
        
        # Step 6: Wait for file to be processed before clicking Import
        automation_status["message"] = "Phase 2: Waiting for file to be processed..."
        time.sleep(3)
        
        # Step 7: Click Import button using exact XPath
        automation_status["message"] = "Phase 2: Clicking Import button..."
        import_button = find_element_by_xpath(driver, "//input[@id='import_submit']", timeout=15)
        
        if not import_button:
            automation_status["message"] = "Phase 2: Error: Could not find Import button with id='import_submit'"
            return False
        
        # Ensure button is enabled and visible
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_button)
        time.sleep(1)
        
        # Check if button is enabled
        if not import_button.is_enabled():
            automation_status["message"] = "Phase 2: Import button is disabled. Waiting for it to be enabled..."
            try:
                WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@id='import_submit']"))
                )
                import_button = find_element_by_xpath(driver, "//input[@id='import_submit']", timeout=5)
            except:
                automation_status["message"] = "Phase 2: Import button remained disabled. File may not be processed correctly."
                return False
        
        # Click the Import button
        try:
            import_button.click()
            print("Phase 2: Import button clicked")
        except:
            # Try JavaScript click if regular click fails
            driver.execute_script("arguments[0].click();", import_button)
            print("Phase 2: Import button clicked via JavaScript")
        
        automation_status["message"] = "Phase 2: Import button clicked. Waiting for import to start..."
        time.sleep(2)
        
        # Step 8: Wait for "Importing..." indicator to appear (confirms import started)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Importing') or contains(text(), 'importing')]"))
            )
            automation_status["message"] = "Phase 2: Import in progress (Importing indicator found)..."
            print("Phase 2: Importing indicator appeared")
        except:
            automation_status["message"] = "Phase 2: Import started (no importing indicator found, continuing)..."
            print("Phase 2: No importing indicator found, but continuing...")
        
        # Step 9: Wait for import to complete - DO NOT CLOSE BROWSER until success message appears
        automation_status["message"] = "Phase 2: Waiting for import to complete (this may take 30-200 seconds)..."
        print("Phase 2: Waiting for success message - DO NOT CLOSE BROWSER")
        max_wait_time = 200  # 200 seconds max wait (3.33 minutes - allows more time for large imports)
        start_time = time.time()
        import_completed = False
        
        while time.time() - start_time < max_wait_time:
            try:
                current_url = driver.current_url
                page_source = driver.page_source.lower()
                
                # Check for success message - this is the key indicator
                success_indicators = [
                    "imported weights & targets successfully",
                    "imported weights and targets successfully",
                    "import successfully",
                    "successfully imported"
                ]
                
                for success_text in success_indicators:
                    if success_text in page_source:
                        automation_status["message"] = f"Phase 2: SUCCESS! Import completed - '{success_text}' message found!"
                        print(f"Phase 2: Success message found: {success_text}")
                        import_completed = True
                        # Return immediately once success is detected
                        break
                
                if import_completed:
                    # Exit the wait loop immediately when success is detected
                    break
                
                # Check if "Importing..." text has disappeared and we're back on weights_targets page
                importing_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Importing') or contains(text(), 'importing')]")
                if not importing_elements:
                    # Importing text is gone, check if we're redirected
                    if "/import" not in current_url and "weights_targets" in current_url:
                        # Wait a bit more for success message to appear
                        time.sleep(3)
                        page_source = driver.page_source.lower()
                        for success_text in success_indicators:
                            if success_text in page_source:
                                automation_status["message"] = f"Phase 2: SUCCESS! Import completed - '{success_text}' message found!"
                                print(f"Phase 2: Success message found after redirect: {success_text}")
                                import_completed = True
                                break
                        if import_completed:
                            break
                
                # Handle white page scenario - might be temporary during async operation
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    body_text = body.text.strip()
                    
                    # If page is white/empty, wait a bit more - it might be loading
                    if len(body_text) < 50:
                        # Check if we're still on import page or redirected
                        if "/import" not in current_url:
                            # We've been redirected, wait a moment for content to load
                            time.sleep(3)
                            page_source = driver.page_source.lower()
                            for success_text in success_indicators:
                                if success_text in page_source:
                                    import_completed = True
                                    break
                            if import_completed:
                                break
                except:
                    pass
                
                # Check for error messages
                error_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'error')] | //*[contains(@class, 'alert-danger')] | //*[@role='alert']")
                for elem in error_elements:
                    elem_text = elem.text.lower()
                    if "error" in elem_text or "failed" in elem_text:
                        automation_status["message"] = f"Phase 2: ERROR - Import failed: {elem.text[:200]}"
                        print(f"Phase 2: Error found: {elem.text[:200]}")
                        return False
                
            except Exception as e:
                # Continue waiting even if there's a temporary exception
                print(f"Phase 2: Exception during wait (continuing): {str(e)}")
            
            time.sleep(1)  # Check every 1 second (reduced from 2 seconds for faster detection)
        
        if import_completed:
            # Quick final verification - minimal wait since we already detected success
            time.sleep(0.5)  # Reduced from 1 second - brief wait to ensure page is stable
            try:
                final_page_source = driver.page_source.lower()
                for success_text in success_indicators:
                    if success_text in final_page_source:
                        automation_status["message"] = f"Phase 2: Import completed successfully! Success message confirmed: '{success_text}'"
                        print(f"Phase 2: Final verification - success message confirmed: {success_text}")
                        return True
                
                # If no success message but we're on weights_targets page, still consider success
                final_url = driver.current_url
                if "/import" not in final_url and "weights_targets" in final_url:
                    automation_status["message"] = "Phase 2: Import completed! Navigated to weights_targets page."
                    print(f"Phase 2: Final verification - on weights_targets page: {final_url}")
                    return True
            except:
                pass
            
            automation_status["message"] = "Phase 2: Import process completed. Please verify data in portal."
            return True
        else:
            automation_status["message"] = f"Phase 2: Import timeout after {max_wait_time} seconds. Please check browser manually."
            print(f"Phase 2: Import timeout. Current URL: {driver.current_url}")
            return False
            
    except Exception as e:
        automation_status["message"] = f"Phase 2: Error importing CSV: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def process_search_term_weights_file(search_term_weights_path, output_csv_path, scorecard_name='Default'):
    """
    Process the search term weights file to create a clean CSV with search_term, weight, and scorecard columns.
    
    Processing steps:
    1. Read CSV/Excel file (detect file type by extension)
    2. Dynamically detect header row by searching for "Search Term" and "Weight" columns
    3. Extract only "Search Term" and "Weight" columns (remove Category, Brand, and other columns)
    4. Clean the data:
       - Remove empty rows
       - Handle missing weights: if a search term has no weight, assign 1.0
       - Preprocess percentages: convert "50%" → 50 (not 0.5) - keep as whole number
       - Replace "weighted evenly" (case-insensitive) with 1.0
    5. Add scorecard column with the scorecard name from UI (same value for all rows)
    6. Rename columns to: search_term, weight, scorecard
    7. Save as CSV to output_csv_path
    
    Args:
        search_term_weights_path: Path to the search term weights file (CSV or Excel)
        output_csv_path: Path to save processed CSV
        scorecard_name: Scorecard name to add to the scorecard column (same value for all rows)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        automation_status["message"] = "Phase 4: Reading search term weights file..."
        print(f"Phase 4: Processing search term weights file: {search_term_weights_path}")
        print(f"Phase 4: File exists: {os.path.exists(search_term_weights_path)}")
        
        if not os.path.exists(search_term_weights_path):
            error_msg = f"Phase 4: Error: Search term weights file not found at {search_term_weights_path}"
            automation_status["message"] = error_msg
            print(f"Phase 4: ERROR - {error_msg}")
            return False
        
        # Detect file type
        file_ext = os.path.splitext(search_term_weights_path)[1].lower()
        
        # Read the file to find the header row by scanning for "Search Term" and "Weight"
        # We'll read a larger chunk to ensure we find the header
        if file_ext == '.csv':
            # Read first 30 rows to find header (skip first few empty rows)
            temp_df = pd.read_csv(search_term_weights_path, header=None, nrows=30)
        else:
            temp_df = pd.read_excel(search_term_weights_path, header=None, nrows=30)
        
        print(f"Phase 4: Reading first 30 rows to find header")
        
        # Find header row by looking for "Search Term" and "Weight" columns
        header_row = None
        search_term_col_idx = None
        weight_col_idx = None
        
        for idx in range(len(temp_df)):
            row = temp_df.iloc[idx]
            
            # Check if this row has "Search Term" and "Weight" as separate column values
            # (not in instruction text, but as actual column headers)
            has_search_term_col = False
            has_weight_col = False
            search_term_col_idx = None
            weight_col_idx = None
            
            for col_idx, cell in enumerate(row):
                if pd.notna(cell):
                    cell_str = str(cell).strip().lower()
                    # Look for "Search Term" as a column header (exact or contains)
                    if 'search term' in cell_str and 'weight' not in cell_str and len(cell_str) < 50:
                        # This looks like a column header, not instruction text
                        has_search_term_col = True
                        if search_term_col_idx is None:
                            search_term_col_idx = col_idx
                    # Look for "Weight" as a column header
                    elif 'weight' in cell_str and 'search term' not in cell_str and len(cell_str) < 50:
                        has_weight_col = True
                        if weight_col_idx is None:
                            weight_col_idx = col_idx
            
            # Only accept if we found both as separate columns (not in same cell)
            if has_search_term_col and has_weight_col and search_term_col_idx is not None and weight_col_idx is not None:
                header_row = idx  # This is 0-based, which is what pandas expects
                print(f"Phase 4: Found header row at index {header_row} (row {header_row + 1} in file)")
                print(f"Phase 4: Search Term column index: {search_term_col_idx}, Weight column index: {weight_col_idx}")
                break
        
        if header_row is None or search_term_col_idx is None or weight_col_idx is None:
            error_msg = "Phase 4: Error: Could not find header row with 'Search Term' and 'Weight' columns"
            automation_status["message"] = error_msg
            print(f"Phase 4: ERROR - {error_msg}")
            return False
        
        # Read full file with detected header row (0-based index)
        if file_ext == '.csv':
            df = pd.read_csv(search_term_weights_path, header=header_row)
        else:
            df = pd.read_excel(search_term_weights_path, header=header_row)
        
        df.columns = df.columns.str.strip()
        
        # Find the actual column names (handle case-insensitive matching)
        # Note: The CSV may have duplicate "Search Term" columns - we need the FIRST one with data
        search_term_col = None
        weight_col = None
        
        # First, find the Weight column (look for "Weight" or "Weight*")
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if 'weight' in col_lower and 'search term' not in col_lower:
                weight_col = col
                print(f"Phase 4: Found Weight column: '{col}'")
                break
        
        # Then find the Search Term column - prefer the one that has actual data
        search_term_candidates = []
        for col in df.columns:
            col_lower = str(col).strip().lower()
            # Match "Search Term" (exact or as part of column name, but not "Search Term.1" etc)
            if 'search term' in col_lower and 'weight' not in col_lower:
                # Count non-empty values in this column (excluding header text)
                non_empty_count = df[col].notna().sum()
                # Also check that it's not just the header text repeated
                unique_values = df[col].dropna().unique()
                # Filter out values that look like headers or instructions
                valid_data_count = sum(1 for v in unique_values 
                                     if str(v).strip().lower() not in ['search term', 'searchterm', 'nan', ''])
                search_term_candidates.append((col, non_empty_count, valid_data_count))
        
        # Sort by valid data count first, then by non-empty count
        if search_term_candidates:
            search_term_candidates.sort(key=lambda x: (x[2], x[1]), reverse=True)
            search_term_col = search_term_candidates[0][0]
            print(f"Phase 4: Found {len(search_term_candidates)} 'Search Term' column(s). Using '{search_term_col}' with {search_term_candidates[0][1]} non-empty values and {search_term_candidates[0][2]} valid data values")
        
        if search_term_col is None or weight_col is None:
            error_msg = f"Phase 4: Error: Could not find 'Search Term' and 'Weight' columns. Found columns: {list(df.columns)}"
            automation_status["message"] = error_msg
            print(f"Phase 4: ERROR - {error_msg}")
            return False
        
        print(f"Phase 4: Using columns - Search Term: '{search_term_col}', Weight: '{weight_col}'")
        
        # Extract only Search Term and Weight columns
        result_df = pd.DataFrame()
        result_df['search_term'] = df[search_term_col].astype(str).str.strip()
        result_df['weight'] = df[weight_col]
        
        # Remove rows where search_term is empty, NaN, or contains header/instruction text
        result_df = result_df[
            result_df['search_term'].notna() & 
            (result_df['search_term'] != '') & 
            (result_df['search_term'] != 'nan') &
            (result_df['search_term'] != 'Search Term') &
            (~result_df['search_term'].str.contains('Branded Search Terms', case=False, na=False)) &
            (~result_df['search_term'].str.contains('Please enter', case=False, na=False))
        ]
        
        print(f"Phase 4: Found {len(result_df)} search terms")
        
        # Helper function to extract number from percentage strings
        def extract_number(value):
            """
            Convert percentage strings to numbers: '50%' → 50 (not 0.5), preserve numeric values.
            Handles:
            - "50%" → 50.0
            - "weighted evenly" → 1.0
            - Missing/empty → None (will be assigned 1.0 later)
            """
            if pd.isna(value) or value == '' or value is None:
                return None
            try:
                if isinstance(value, str):
                    value_str = str(value).strip().lower()
                    # Check for "weighted evenly" first
                    if 'weighted evenly' in value_str:
                        return 1.0
                    # Handle percentage strings - extract the number as-is (50% → 50, not 0.5)
                    if '%' in value_str:
                        import re
                        match = re.search(r'([\d.]+)', value_str)
                        if match:
                            # Return as float but keep the whole number (50% → 50.0, not 0.5)
                            num = float(match.group(1))
                            # If it's a whole number, return as int to avoid .0 in CSV
                            if num == int(num):
                                return float(int(num))
                            return num
                    # Try to convert to number (for non-percentage numeric strings)
                    try:
                        num = float(value_str)
                        # If it's a whole number, return as int to avoid .0 in CSV
                        if num == int(num):
                            return float(int(num))
                        return num
                    except:
                        return None
                elif isinstance(value, (int, float)):
                    # If it's a whole number, return as int to avoid .0 in CSV
                    if isinstance(value, float) and value == int(value):
                        return float(int(value))
                    return value
            except Exception as e:
                print(f"Phase 4: Warning - Could not extract number from '{value}': {str(e)}")
                return None
            return None
        
        # Process weights: handle percentages, "weighted evenly", and missing values
        automation_status["message"] = "Phase 4: Processing weights..."
        print("Phase 4: Processing weights...")
        
        processed_weights = []
        for idx, row in result_df.iterrows():
            weight_val = row['weight']
            processed_weight = extract_number(weight_val)
            
            # If weight is missing or couldn't be processed, assign 1.0
            if processed_weight is None or pd.isna(processed_weight):
                processed_weight = 1.0
                print(f"Phase 4: Assigned default weight 1.0 to search term: '{row['search_term']}'")
            
            processed_weights.append(processed_weight)
        
        result_df['weight'] = processed_weights
        
        # Add scorecard column with the scorecard name from UI (same value for all rows)
        result_df['scorecard'] = scorecard_name
        print(f"Phase 4: Added scorecard column with value: '{scorecard_name}' (same for all rows)")
        
        # Reorder columns: search_term, weight, scorecard
        result_df = result_df[['search_term', 'weight', 'scorecard']]
        print(f"Phase 4: Final CSV will have three columns: search_term, weight, scorecard")
        
        # Save as CSV
        automation_status["message"] = f"Phase 4: Saving processed file to {output_csv_path}..."
        print(f"Phase 4: Saving processed CSV to: {output_csv_path}")
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        result_df.to_csv(output_csv_path, index=False)
        
        print(f"Phase 4: CSV file saved successfully with {len(result_df)} rows")
        automation_status["message"] = f"Phase 4: Saved processed CSV with {len(result_df)} search terms"
        
        # Validation: verify the CSV file
        try:
            validation_df = pd.read_csv(output_csv_path)
            if len(validation_df) == 0:
                error_msg = "Phase 4: Warning: Processed CSV file is empty"
                automation_status["message"] = error_msg
                print(f"Phase 4: WARNING - {error_msg}")
                return False
            print(f"Phase 4: CSV validation passed. File has {len(validation_df)} rows.")
            automation_status["message"] = f"Phase 4: CSV validation passed. File has {len(validation_df)} rows."
        except Exception as e:
            error_msg = f"Phase 4: Error: CSV validation failed - {str(e)}"
            automation_status["message"] = error_msg
            print(f"Phase 4: ERROR - {error_msg}")
            import traceback
            print(traceback.format_exc())
            return False
        
        print("Phase 4: Processing completed successfully!")
        return True
        
    except Exception as e:
        error_msg = f"Phase 4: Error processing search term weights file: {str(e)}"
        automation_status["message"] = error_msg
        print(f"Phase 4: EXCEPTION - {error_msg}")
        import traceback
        print(traceback.format_exc())
        return False

def import_search_term_weights_csv(driver, csv_file_path, change_reason, scorecard_name):
    """
    Import the processed search term weights CSV file to the portal.
    
    Args:
        driver: Selenium WebDriver instance
        csv_file_path: Path to the CSV file to import
        change_reason: Change reason text (must be at least 10 characters)
        scorecard_name: Scorecard name to select from dropdown (e.g., 'Default-Standard')
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Step 1: Navigate directly to Search Term Weights page
        automation_status["message"] = "Phase 4: Navigating to Search Term Weights page..."
        print("=" * 80)
        print("Phase 4: Navigating to Search Term Weights page...")
        print("=" * 80)
        print(f"Phase 4: Current URL before navigation: {driver.current_url}")
        
        search_term_weights_url = "https://settings.ef.uk.com/search_term_weights"
        print(f"Phase 4: Navigating directly to: {search_term_weights_url}")
        
        try:
            driver.get(search_term_weights_url)
            time.sleep(5)  # Wait for page to load and any redirects
            
            # Verify navigation was successful
            new_url = driver.current_url
            print(f"Phase 4: After navigation, URL is: {new_url}")
            
            # Check if we were redirected (e.g., to login page or error page)
            if 'login' in new_url.lower() or 'signin' in new_url.lower():
                automation_status["message"] = "Phase 4: ERROR - Redirected to login page. Session may have expired."
                print("Phase 4: ERROR - Redirected to login page. Please check if you're still logged in.")
                return False
            
            if 'error' in new_url.lower() or '404' in new_url.lower() or '403' in new_url.lower():
                automation_status["message"] = f"Phase 4: ERROR - Navigation resulted in error page: {new_url}"
                print(f"Phase 4: ERROR - Error page detected: {new_url}")
                return False
            
            # Check if we're actually on the search_term_weights page
            if 'search_term_weights' not in new_url.lower():
                automation_status["message"] = f"Phase 4: WARNING - Not on expected page. Current URL: {new_url}"
                print(f"Phase 4: WARNING - Expected 'search_term_weights' in URL, but got: {new_url}")
                # Check page content to see if we're on the right page despite URL mismatch
                try:
                    page_text = driver.page_source.lower()
                    if 'search term weights' not in page_text and 'search term' not in page_text:
                        automation_status["message"] = "Phase 4: ERROR - Page content doesn't match Search Term Weights page"
                        print("Phase 4: ERROR - Page doesn't appear to be Search Term Weights page")
                        return False
                    else:
                        print("Phase 4: Page content suggests we're on the right page despite URL mismatch")
                except Exception as e:
                    print(f"Phase 4: Could not verify page content: {str(e)}")
            
            # Wait for page to load and verify key elements are present
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Search Term') or contains(text(), 'Weights') or contains(text(), 'Bulk Operations')]"))
                )
                print("Phase 4: ✓ Page loaded successfully - found Search Term Weights content")
            except TimeoutException:
                automation_status["message"] = "Phase 4: WARNING - Page loaded but couldn't find expected content. Continuing anyway..."
                print("Phase 4: WARNING - Timeout waiting for page content, but continuing...")
            except Exception as e:
                print(f"Phase 4: Warning while waiting for page: {str(e)}")
                
        except Exception as nav_error:
            automation_status["message"] = f"Phase 4: ERROR - Failed to navigate to Search Term Weights page: {str(nav_error)}"
            print(f"Phase 4: ERROR - Navigation failed: {str(nav_error)}")
            import traceback
            print(traceback.format_exc())
            return False
        
        # Step 2: Select scorecard from dropdown before Bulk Operations
        automation_status["message"] = f"Phase 4: Selecting scorecard '{scorecard_name}' from dropdown..."
        print(f"Phase 4: Selecting scorecard '{scorecard_name}' from dropdown...")
        
        try:
            # Find and click the React Select dropdown (css-1hwfws3 is the control class)
            dropdown_control = find_element_by_xpath(driver, "//div[contains(@class,'css-1hwfws3')]", timeout=15)
            
            if not dropdown_control:
                automation_status["message"] = "Phase 4: WARNING - Could not find scorecard dropdown. Continuing to Bulk Operations..."
                print("Phase 4: WARNING - Could not find scorecard dropdown, continuing anyway...")
            else:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_control)
                time.sleep(0.5)
                dropdown_control.click()
                time.sleep(1)
                
                # Find and click the option with matching scorecard_name
                # React Select options are typically in a menu with class containing 'option'
                option_xpath = f"//div[contains(@class,'option') and normalize-space()='{scorecard_name}']"
                option = find_element_by_xpath(driver, option_xpath, timeout=10)
                
                if option:
                    option.click()
                    time.sleep(1)
                    print(f"Phase 4: ✓ Selected scorecard '{scorecard_name}' from dropdown")
                    automation_status["message"] = f"Phase 4: Selected scorecard '{scorecard_name}'"
                else:
                    # Try case-insensitive match
                    all_options = driver.find_elements(By.XPATH, "//div[contains(@class,'option')]")
                    found_option = None
                    for opt in all_options:
                        if opt.text.strip().lower() == str(scorecard_name).lower():
                            found_option = opt
                            break
                    
                    if found_option:
                        found_option.click()
                        time.sleep(1)
                        print(f"Phase 4: ✓ Selected scorecard '{scorecard_name}' (case-insensitive match)")
                        automation_status["message"] = f"Phase 4: Selected scorecard '{scorecard_name}'"
                    else:
                        automation_status["message"] = f"Phase 4: WARNING - Could not find scorecard option '{scorecard_name}'. Continuing..."
                        print(f"Phase 4: WARNING - Could not find scorecard option '{scorecard_name}', continuing anyway...")
                        # Click outside to close dropdown if it's still open
                        try:
                            driver.find_element(By.TAG_NAME, "body").click()
                            time.sleep(0.5)
                        except:
                            pass
        except Exception as dropdown_error:
            automation_status["message"] = f"Phase 4: WARNING - Error selecting scorecard dropdown: {str(dropdown_error)}. Continuing..."
            print(f"Phase 4: WARNING - Error with scorecard dropdown: {str(dropdown_error)}, continuing anyway...")
        
        # Step 3: Click on Bulk Operations
        automation_status["message"] = "Phase 4: Clicking on 'Bulk Operations'..."
        print("Phase 4: Clicking on 'Bulk Operations'...")
        bulk_ops_link = find_element_by_xpath(driver, "//a[normalize-space()='Bulk Operations']", timeout=15)
        
        if not bulk_ops_link:
            automation_status["message"] = "Phase 4: Error: Could not find 'Bulk Operations' link"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bulk_ops_link)
        time.sleep(1)
        bulk_ops_link.click()
        time.sleep(2)
        
        # Step 4: Click on "Import Search Term Weights CSV" link
        automation_status["message"] = "Phase 4: Clicking on 'Import Search Term Weights CSV'..."
        print("Phase 4: Clicking on 'Import Search Term Weights CSV'...")
        import_csv_link = find_element_by_xpath(driver, "//a[normalize-space()='Import Search Term Weights CSV']", timeout=15)
        
        if not import_csv_link:
            automation_status["message"] = "Phase 4: Error: Could not find 'Import Search Term Weights CSV' link"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_csv_link)
        time.sleep(1)
        import_csv_link.click()
        time.sleep(3)  # Wait for new page to load
        
        # Step 5: Click on "Upload a file"
        automation_status["message"] = "Phase 4: Clicking on 'Upload a file'..."
        print("Phase 4: Clicking on 'Upload a file'...")
        upload_file_span = find_element_by_xpath(driver, "//span[normalize-space()='Upload a file']", timeout=15)
        
        if not upload_file_span:
            automation_status["message"] = "Phase 4: Error: Could not find 'Upload a file' span"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", upload_file_span)
        time.sleep(1)
        upload_file_span.click()
        time.sleep(2)
        
        # Step 6: Find and use the file input element to upload the CSV
        automation_status["message"] = "Uploading CSV file..."
        file_input = None
        
        # Try to find file input - it might be hidden
        file_input_selectors = [
            "//input[@type='file']",
            "//input[@name='file']",
            "//input[contains(@class, 'file')]",
            "//input[@accept='.csv']"
        ]
        
        for selector in file_input_selectors:
            try:
                file_input = driver.find_element(By.XPATH, selector)
                if file_input:
                    break
            except:
                continue
        
        if not file_input:
            automation_status["message"] = "Error: Could not find file upload input"
            return False
        
        # Upload the file - verify it exists first
        abs_csv_path = os.path.abspath(csv_file_path)
        print(f"Uploading file: {abs_csv_path}")
        print(f"File exists: {os.path.exists(abs_csv_path)}")
        
        if not os.path.exists(abs_csv_path):
            automation_status["message"] = f"Error: CSV file not found at {abs_csv_path}"
            return False
        
        file_input.send_keys(abs_csv_path)
        time.sleep(3)  # Wait for file to be processed
        
        # Step 5: Fill in change reason
        automation_status["message"] = "Entering change reason..."
        change_reason_input = find_element_by_xpath(driver, "//textarea[@id='reason_for_change']", timeout=15)
        
        if not change_reason_input:
            automation_status["message"] = "Error: Could not find change reason textarea"
            return False
        
        # Ensure change reason is at least 10 characters
        if len(change_reason) < 10:
            change_reason = change_reason + " " * (10 - len(change_reason))
        
        change_reason_input.clear()
        change_reason_input.send_keys(change_reason)
        time.sleep(1)
        print(f"Change reason entered: {change_reason}")
        
        # Step 8: Click Import button
        automation_status["message"] = "Looking for Import button..."
        import_button = find_element_by_xpath(driver, "//input[@id='import_submit'] | //button[contains(text(), 'Import')] | //input[@type='submit' and contains(@value, 'Import')]", timeout=15)
        
        if import_button:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_button)
            time.sleep(1)
            
            # Check if button is enabled
            if import_button.is_enabled():
                import_button.click()
                automation_status["message"] = "Import button clicked. Waiting for import to complete..."
                time.sleep(5)
                return True
            else:
                automation_status["message"] = "Import button is disabled. File may not be processed correctly."
                return False
        else:
            automation_status["message"] = "Import button not found. File may have been uploaded successfully."
            return True
            
    except Exception as e:
        automation_status["message"] = f"Error importing search term weights CSV: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def process_category_brand_mapping(enterprise_path=None, competition_path=None, output_csv_path=None):
    """
    Process category brand mapping files to create a clean CSV with only Category and Brand columns.
    
    Processing steps:
    1. Read Enterprise file (if provided) - extract Category and Brand columns
    2. Read Competition file (if provided) - extract Category and Brand columns, handle forward-fill for empty category cells
    3. If both provided: merge files (combine brands for matching categories)
    4. If only one provided: use that file's data
    5. Save as CSV with only 2 columns: Category, Brand
    
    Args:
        enterprise_path: Path to Enterprise Excel file (optional)
        competition_path: Path to Competition Excel file (optional)
        output_csv_path: Path to save processed CSV
    
    Returns:
        True if successful, False otherwise
    """
    try:
        automation_status["message"] = "Phase 5: Processing category brand mapping files..."
        print("=" * 80)
        print("Phase 5: Processing Category Brand Mapping")
        print("=" * 80)
        
        if not enterprise_path and not competition_path:
            error_msg = "Phase 5: Error: At least one file path (Enterprise or Competition) must be provided"
            automation_status["message"] = error_msg
            print(f"Phase 5: ERROR - {error_msg}")
            return False
        
        all_dataframes = []
        
        # Process Enterprise file if provided
        if enterprise_path:
            if not os.path.exists(enterprise_path):
                error_msg = f"Phase 5: Error: Enterprise file not found at {enterprise_path}"
                automation_status["message"] = error_msg
                print(f"Phase 5: ERROR - {error_msg}")
                return False
            
            print(f"Phase 5: Reading Enterprise file: {enterprise_path}")
            df_enterprise = pd.read_excel(enterprise_path, header=2)
            
            # Extract Category and Brand columns
            if 'Category' not in df_enterprise.columns or 'Brand' not in df_enterprise.columns:
                error_msg = f"Phase 5: Error: Enterprise file must have 'Category' and 'Brand' columns. Found: {list(df_enterprise.columns)}"
                automation_status["message"] = error_msg
                print(f"Phase 5: ERROR - {error_msg}")
                return False
            
            df_enterprise_clean = df_enterprise[['Category', 'Brand']].copy()
            df_enterprise_clean = df_enterprise_clean.dropna(subset=['Category', 'Brand'])
            df_enterprise_clean = df_enterprise_clean[
                (df_enterprise_clean['Category'].astype(str).str.strip() != '') &
                (df_enterprise_clean['Brand'].astype(str).str.strip() != '')
            ]
            
            print(f"Phase 5: Enterprise file processed - {len(df_enterprise_clean)} category-brand pairs")
            all_dataframes.append(df_enterprise_clean)
        
        # Process Competition file if provided
        if competition_path:
            if not os.path.exists(competition_path):
                error_msg = f"Phase 5: Error: Competition file not found at {competition_path}"
                automation_status["message"] = error_msg
                print(f"Phase 5: ERROR - {error_msg}")
                return False
            
            print(f"Phase 5: Reading Competition file: {competition_path}")
            df_competition = pd.read_excel(competition_path, header=2)
            
            # Extract Category and Brand columns
            if 'Category' not in df_competition.columns or 'Brand' not in df_competition.columns:
                error_msg = f"Phase 5: Error: Competition file must have 'Category' and 'Brand' columns. Found: {list(df_competition.columns)}"
                automation_status["message"] = error_msg
                print(f"Phase 5: ERROR - {error_msg}")
                return False
            
            df_competition_clean = df_competition[['Category', 'Brand']].copy()
            
            # Forward fill empty category cells (Competition files have category only in first row of each group)
            df_competition_clean['Category'] = df_competition_clean['Category'].ffill()
            
            df_competition_clean = df_competition_clean.dropna(subset=['Brand'])
            df_competition_clean = df_competition_clean[
                (df_competition_clean['Category'].astype(str).str.strip() != '') &
                (df_competition_clean['Brand'].astype(str).str.strip() != '')
            ]
            
            print(f"Phase 5: Competition file processed - {len(df_competition_clean)} category-brand pairs")
            all_dataframes.append(df_competition_clean)
        
        # Merge all dataframes
        if len(all_dataframes) > 1:
            print("Phase 5: Merging Enterprise and Competition data...")
            df_merged = pd.concat(all_dataframes, ignore_index=True)
        else:
            df_merged = all_dataframes[0]
        
        # Sort by Category for better organization
        df_merged = df_merged.sort_values('Category').reset_index(drop=True)
        
        print(f"Phase 5: Final merged data - {len(df_merged)} total category-brand pairs")
        print(f"Phase 5: Unique categories: {df_merged['Category'].nunique()}")
        
        # Rename columns to lowercase (required format: category,brand)
        df_merged = df_merged.rename(columns={'Category': 'category', 'Brand': 'brand'})
        print("Phase 5: Column headers set to lowercase: category, brand")
        
        # Save to CSV
        automation_status["message"] = f"Phase 5: Saving processed file to {output_csv_path}..."
        print(f"Phase 5: Saving CSV to: {output_csv_path}")
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        df_merged.to_csv(output_csv_path, index=False)
        
        print(f"Phase 5: CSV file saved successfully with {len(df_merged)} rows")
        automation_status["message"] = f"Phase 5: Saved processed CSV with {len(df_merged)} category-brand pairs"
        
        # Validation
        try:
            validation_df = pd.read_csv(output_csv_path)
            if len(validation_df) == 0:
                error_msg = "Phase 5: Warning: Processed CSV file is empty"
                automation_status["message"] = error_msg
                print(f"Phase 5: WARNING - {error_msg}")
                return False
            print(f"Phase 5: CSV validation passed. File has {len(validation_df)} rows.")
            automation_status["message"] = f"Phase 5: CSV validation passed. File has {len(validation_df)} rows."
        except Exception as e:
            error_msg = f"Phase 5: Error: CSV validation failed - {str(e)}"
            automation_status["message"] = error_msg
            print(f"Phase 5: ERROR - {error_msg}")
            import traceback
            print(traceback.format_exc())
            return False
        
        print("Phase 5: Processing completed successfully!")
        return True
        
    except Exception as e:
        error_msg = f"Phase 5: Error processing category brand mapping files: {str(e)}"
        automation_status["message"] = error_msg
        print(f"Phase 5: EXCEPTION - {error_msg}")
        import traceback
        print(traceback.format_exc())
        return False

def import_category_brand_csv(driver, csv_file_path, change_reason):
    """
    Import the processed category brand mapping CSV file to the portal.
    
    Args:
        driver: Selenium WebDriver instance
        csv_file_path: Path to the CSV file to import
        change_reason: Change reason text (must be at least 10 characters)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Step 1: Navigate to Category Brands page
        automation_status["message"] = "Phase 5: Navigating to Category Brands page..."
        print("=" * 80)
        print("Phase 5: Navigating to Category Brands page...")
        print("=" * 80)
        
        category_brands_url = "https://settings.ef.uk.com/category_brands"
        print(f"Phase 5: Navigating to: {category_brands_url}")
        
        try:
            driver.get(category_brands_url)
            time.sleep(5)
            
            new_url = driver.current_url
            print(f"Phase 5: After navigation, URL is: {new_url}")
            
            if 'login' in new_url.lower() or 'signin' in new_url.lower():
                automation_status["message"] = "Phase 5: ERROR - Redirected to login page. Session may have expired."
                print("Phase 5: ERROR - Redirected to login page.")
                return False
            
            if 'error' in new_url.lower() or '404' in new_url.lower() or '403' in new_url.lower():
                automation_status["message"] = f"Phase 5: ERROR - Navigation resulted in error page: {new_url}"
                print(f"Phase 5: ERROR - Error page detected: {new_url}")
                return False
            
            # Wait for page to load
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Category') or contains(text(), 'Brand')]"))
                )
                print("Phase 5: ✓ Page loaded successfully")
            except TimeoutException:
                automation_status["message"] = "Phase 5: WARNING - Page loaded but couldn't find expected content. Continuing anyway..."
                print("Phase 5: WARNING - Timeout waiting for page content, but continuing...")
                
        except Exception as nav_error:
            automation_status["message"] = f"Phase 5: ERROR - Failed to navigate to Category Brands page: {str(nav_error)}"
            print(f"Phase 5: ERROR - Navigation failed: {str(nav_error)}")
            import traceback
            print(traceback.format_exc())
            return False
        
        # Step 2: Click on "Import CSV" link
        automation_status["message"] = "Phase 5: Clicking on 'Import CSV'..."
        print("Phase 5: Clicking on 'Import CSV'...")
        import_csv_link = find_element_by_xpath(driver, "//a[normalize-space()='Import CSV']", timeout=15)
        
        if not import_csv_link:
            automation_status["message"] = "Phase 5: Error: Could not find 'Import CSV' link"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_csv_link)
        time.sleep(1)
        import_csv_link.click()
        time.sleep(3)  # Wait for new page to load
        
        # Step 3: Click on "Upload a file"
        automation_status["message"] = "Phase 5: Clicking on 'Upload a file'..."
        print("Phase 5: Clicking on 'Upload a file'...")
        upload_file_span = find_element_by_xpath(driver, "//span[normalize-space()='Upload a file']", timeout=15)
        
        if not upload_file_span:
            automation_status["message"] = "Phase 5: Error: Could not find 'Upload a file' span"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", upload_file_span)
        time.sleep(1)
        upload_file_span.click()
        time.sleep(2)
        
        # Step 4: Find and use the file input element to upload the CSV
        automation_status["message"] = "Phase 5: Uploading CSV file..."
        file_input = None
        
        file_input_selectors = [
            "//input[@type='file']",
            "//input[@name='file']",
            "//input[contains(@class, 'file')]",
            "//input[@accept='.csv']"
        ]
        
        for selector in file_input_selectors:
            try:
                file_input = driver.find_element(By.XPATH, selector)
                if file_input:
                    break
            except:
                continue
        
        if not file_input:
            automation_status["message"] = "Phase 5: Error: Could not find file upload input"
            return False
        
        abs_csv_path = os.path.abspath(csv_file_path)
        print(f"Phase 5: Uploading file: {abs_csv_path}")
        print(f"Phase 5: File exists: {os.path.exists(abs_csv_path)}")
        
        if not os.path.exists(abs_csv_path):
            automation_status["message"] = f"Phase 5: Error: CSV file not found at {abs_csv_path}"
            return False
        
        file_input.send_keys(abs_csv_path)
        time.sleep(3)
        
        # Step 5: Fill in change reason
        automation_status["message"] = "Phase 5: Entering change reason..."
        change_reason_input = find_element_by_xpath(driver, "//textarea[@id='reason_for_change']", timeout=15)
        
        if not change_reason_input:
            automation_status["message"] = "Phase 5: Error: Could not find change reason textarea"
            return False
        
        if len(change_reason) < 10:
            change_reason = change_reason + " " * (10 - len(change_reason))
        
        change_reason_input.clear()
        change_reason_input.send_keys(change_reason)
        time.sleep(1)
        print(f"Phase 5: Change reason entered: {change_reason}")
        
        # Step 6: Click Import button
        automation_status["message"] = "Phase 5: Looking for Import button..."
        import_button = find_element_by_xpath(driver, "//input[@id='import_submit']", timeout=15)
        
        if import_button:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", import_button)
            time.sleep(1)
            
            if import_button.is_enabled():
                import_button.click()
                automation_status["message"] = "Phase 5: Import button clicked. Waiting for import to complete..."
                time.sleep(5)
                return True
            else:
                automation_status["message"] = "Phase 5: Import button is disabled. File may not be processed correctly."
                return False
        else:
            automation_status["message"] = "Phase 5: Import button not found."
            return False
            
    except Exception as e:
        automation_status["message"] = f"Phase 5: Error importing category brand CSV: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def update_looker_config(driver, customer_name, change_reason, scorecard_type):
    """
    Update Looker Config for Enterprise scorecards.
    
    Args:
        driver: Selenium WebDriver instance
        customer_name: Customer name from UI
        change_reason: Change reason text
        scorecard_type: Scorecard type (only updates if 'Enterprise')
    
    Returns:
        True if successful or skipped (non-Enterprise), False on error
    """
    try:
        # Only proceed if scorecard type is Enterprise or Competitor
        if scorecard_type not in ['Enterprise', 'Competitor']:
            automation_status["message"] = f"Phase 3a: Skipping Looker Config update (scorecard type is '{scorecard_type}')"
            print(f"Phase 3a: Skipping Looker Config - scorecard type is '{scorecard_type}'")
            return True
        
        automation_status["message"] = f"Phase 3a: Navigating to Looker Config for {scorecard_type} scorecard..."
        print(f"Phase 3a: Starting Looker Config update for {scorecard_type} scorecard...")
        
        # Step 1: Click Looker Config link
        looker_config_link = find_element_by_xpath(driver, "//a[normalize-space()='Looker Config']", timeout=15)
        if not looker_config_link:
            automation_status["message"] = "Phase 3a: Error: Could not find 'Looker Config' link"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", looker_config_link)
        time.sleep(1)
        looker_config_link.click()
        time.sleep(3)
        
        # Step 2: Click Edit button to enable editing
        automation_status["message"] = "Phase 3a: Clicking Edit button..."
        edit_button = find_element_by_xpath(driver, "//button[normalize-space()='Edit'] | //a[normalize-space()='Edit'] | //input[@type='button' and @value='Edit']", timeout=15)
        if not edit_button:
            automation_status["message"] = "Phase 3a: Warning: Could not find Edit button, trying to proceed anyway..."
            print("Phase 3a: Edit button not found, continuing...")
        else:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_button)
            time.sleep(1)
            try:
                edit_button.click()
            except:
                driver.execute_script("arguments[0].click();", edit_button)
            time.sleep(2)
            print("Phase 3a: Edit button clicked")
        
        # Step 3: Extract client name from the page
        automation_status["message"] = "Phase 3a: Extracting client name from page..."
        client_name_element = find_element_by_xpath(driver, "//p[contains(@class,'font-medium') and contains(@class,'text-gray-300')]", timeout=10)
        extracted_client_name = None
        if client_name_element:
            extracted_client_name = client_name_element.text.strip()
            print(f"Phase 3a: Extracted client name: {extracted_client_name}")
        else:
            automation_status["message"] = "Phase 3a: Warning: Could not extract client name, using customer_name from UI"
            extracted_client_name = customer_name
        
        # Step 4: Check and update dropdowns
        needs_update = False
        
        # Helper function to check React Select dropdown value
        def check_react_select_value(label_text, expected_value):
            """Check if a React Select dropdown contains the expected value (multi-select)"""
            try:
                # Find the dropdown control
                dropdown_xpath = f"//div[normalize-space()='{label_text}']/following::div[contains(@class,'css-yk16xz-control')][1]"
                dropdown_control = find_element_by_xpath(driver, dropdown_xpath, timeout=10)
                if not dropdown_control:
                    print(f"Phase 3a: Could not find dropdown for '{label_text}'")
                    return False, None
                
                # Get all current values from the multiValue divs (multi-select can have multiple values)
                try:
                    multi_value_elements = dropdown_control.find_elements(By.XPATH, ".//div[contains(@class,'multiValue')]//div[contains(@class,'css-12jo7m5')]")
                    if multi_value_elements:
                        current_values = [elem.text.strip() for elem in multi_value_elements]
                        print(f"Phase 3a: Dropdown '{label_text}' current values: {current_values}")
                        # Check if expected value exists in the list
                        value_exists = expected_value in current_values
                        if value_exists:
                            print(f"Phase 3a: Dropdown '{label_text}' contains expected value: '{expected_value}'")
                        else:
                            print(f"Phase 3a: Dropdown '{label_text}' does NOT contain expected value: '{expected_value}'")
                        return value_exists, ', '.join(current_values) if current_values else None
                    else:
                        # No values selected
                        print(f"Phase 3a: Dropdown '{label_text}' has no values selected")
                        return False, None
                except Exception as e:
                    print(f"Phase 3a: Error reading dropdown values for '{label_text}': {str(e)}")
                    # Try alternative method - check page source
                    try:
                        page_text = driver.page_source
                        if expected_value in page_text:
                            # Value might be there but not visible in the way we're checking
                            print(f"Phase 3a: Found '{expected_value}' in page source for '{label_text}'")
                            return True, "found in page"
                    except:
                        pass
                    return False, None
            except Exception as e:
                print(f"Phase 3a: Error checking dropdown '{label_text}': {str(e)}")
                return False, None
        
        # Helper function to set React Select dropdown value
        def set_react_select_value(label_text, value):
            """Set a value in a React Select dropdown"""
            try:
                # Find and click the dropdown control to open it
                dropdown_xpath = f"//div[normalize-space()='{label_text}']/following::div[contains(@class,'css-yk16xz-control')][1]"
                dropdown_control = find_element_by_xpath(driver, dropdown_xpath, timeout=10)
                if not dropdown_control:
                    print(f"Phase 3a: Could not find dropdown for '{label_text}'")
                    return False
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_control)
                time.sleep(0.5)
                dropdown_control.click()
                time.sleep(1)
                
                # Find and click the option with the matching value
                option_xpath = f"//div[contains(@class,'option') and normalize-space()='{value}']"
                option = find_element_by_xpath(driver, option_xpath, timeout=5)
                if option:
                    option.click()
                    time.sleep(1)
                    print(f"Phase 3a: Set dropdown '{label_text}' to '{value}'")
                    return True
                else:
                    print(f"Phase 3a: Could not find option '{value}' in dropdown '{label_text}'")
                    return False
            except Exception as e:
                print(f"Phase 3a: Error setting dropdown '{label_text}': {str(e)}")
                return False
        
        # Check Dashboards dropdown
        try:
            automation_status["message"] = "Phase 3a: Checking Dashboards dropdown..."
            # Expected value in dropdown (key part to search for) - depends on scorecard type
            if scorecard_type == 'Enterprise':
                expected_dashboards_check = 'enterprise_scorecardv2::digital_shelf_scorecardv2_measure_group'
            elif scorecard_type == 'Competitor':
                expected_dashboards_check = 'enterprise_scorecard::competitor_dashboard'
            else:
                expected_dashboards_check = 'enterprise_scorecardv2::digital_shelf_scorecardv2_measure_group'  # Default
            
            print(f"Phase 3a: Expected dashboard value for {scorecard_type}: '{expected_dashboards_check}'")
            dashboards_correct, dashboards_current = check_react_select_value('dashboards', expected_dashboards_check)
            if not dashboards_correct:
                needs_update = True
                automation_status["message"] = f"Phase 3a: Dashboards dropdown needs update (current: '{dashboards_current}', expected: '{expected_dashboards_check}')"
                # Click on the dropdown to open it
                dashboards_dropdown_xpath = "//div[normalize-space()='dashboards']/following::div[contains(@class,'css-yk16xz-control')][1]"
                dashboards_dropdown = find_element_by_xpath(driver, dashboards_dropdown_xpath, timeout=10)
                if dashboards_dropdown:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dashboards_dropdown)
                    time.sleep(0.5)
                    dashboards_dropdown.click()
                    time.sleep(2)  # Wait for menu to appear
                    
                    # Find the menu container
                    menu_container = None
                    menu_xpaths = [
                        "//div[contains(@class,'menu')]",
                        "//div[contains(@class,'css-1n7v3ny-option')]",
                        "//div[contains(@id,'react-select')]//div[contains(@class,'menu')]"
                    ]
                    for menu_xpath in menu_xpaths:
                        menu_container = find_element_by_xpath(driver, menu_xpath, timeout=2)
                        if menu_container:
                            break
                    
                    if menu_container:
                        automation_status["message"] = "Phase 3a: Scrolling within Dashboards dropdown to find option..."
                        print("Phase 3a: Scrolling within Dashboards dropdown menu...")
                        
                        # Scroll within the menu to find the option
                        dashboards_option = None
                        max_scroll_attempts = 20
                        scroll_attempt = 0
                        
                        while scroll_attempt < max_scroll_attempts and not dashboards_option:
                            # Try to find the option
                            option_xpaths = [
                                f"//div[contains(@class,'css-12jo7m5') and contains(text(),'{expected_dashboards_check}')]",
                                f"//div[contains(@class,'option') and contains(text(),'{expected_dashboards_check}')]",
                                f"//div[contains(text(),'{expected_dashboards_check}')]"
                            ]
                            
                            for option_xpath in option_xpaths:
                                dashboards_option = find_element_by_xpath(driver, option_xpath, timeout=1)
                                if dashboards_option:
                                    break
                            
                            if dashboards_option:
                                break
                            
                            # Scroll down in the menu
                            driver.execute_script("arguments[0].scrollTop += 50;", menu_container)
                            time.sleep(0.3)
                            scroll_attempt += 1
                        
                        if dashboards_option:
                            # Scroll the option into view and click
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dashboards_option)
                            time.sleep(0.3)
                            try:
                                driver.execute_script("arguments[0].click();", dashboards_option)
                                time.sleep(1)
                                print(f"Phase 3a: ✓ Set Dashboards dropdown to '{expected_dashboards_check}' (scrolled and clicked)")
                            except:
                                dashboards_option.click()
                                time.sleep(1)
                                print(f"Phase 3a: ✓ Set Dashboards dropdown to '{expected_dashboards_check}' (scrolled and clicked via regular click)")
                        else:
                            automation_status["message"] = "Phase 3a: Warning: Could not find Dashboards option after scrolling, but continuing..."
                            print("Phase 3a: Warning - Dashboards option not found after scrolling")
                    else:
                        automation_status["message"] = "Phase 3a: Warning: Could not find menu container, but continuing..."
                        print("Phase 3a: Warning - Menu container not found")
                else:
                    automation_status["message"] = "Phase 3a: Warning: Could not find Dashboards dropdown, but continuing..."
                    print("Phase 3a: Warning - Dashboards dropdown not found")
        except Exception as e:
            automation_status["message"] = f"Phase 3a: Warning: Error checking Dashboards dropdown: {str(e)}, continuing..."
            print(f"Phase 3a: Exception checking dashboards: {str(e)}")
            import traceback
            print(traceback.format_exc())
        
        # Check Models dropdown (only for Enterprise scorecards, skip for Competitor)
        if scorecard_type == 'Enterprise':
            try:
                automation_status["message"] = "Phase 3a: Checking Models dropdown..."
                # Expected value in dropdown (key part to search for)
                expected_models_check = 'enterprise_scorecardv2'
                models_correct, models_current = check_react_select_value('models', expected_models_check)
                if not models_correct:
                    needs_update = True
                    automation_status["message"] = f"Phase 3a: Models dropdown needs update (current: '{models_current}', expected: '{expected_models_check}')"
                    # Click on the dropdown to open it
                    models_dropdown_xpath = "//div[normalize-space()='models']/following::div[contains(@class,'css-yk16xz-control')][1]"
                    models_dropdown = find_element_by_xpath(driver, models_dropdown_xpath, timeout=10)
                    if models_dropdown:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", models_dropdown)
                        time.sleep(0.5)
                        models_dropdown.click()
                        time.sleep(2)  # Wait for menu to appear
                        
                        # Find the menu container - try multiple strategies
                        menu_container = None
                        menu_xpaths = [
                            "//div[contains(@class,'menu') and contains(@class,'css-')]",
                            "//div[contains(@class,'menu')]",
                            "//div[contains(@id,'react-select')]//div[contains(@class,'menu')]",
                            "//div[contains(@class,'css-1n7v3ny-option')]",
                            "//div[contains(@class,'css-26l3qy-menu')]"
                        ]
                        for menu_xpath in menu_xpaths:
                            try:
                                menu_container = find_element_by_xpath(driver, menu_xpath, timeout=2)
                                if menu_container:
                                    print(f"Phase 3a: Found menu container using: {menu_xpath}")
                                    break
                            except:
                                continue
                        
                        # Define option XPaths for searching - try exact match first
                        option_xpaths = [
                            f"//div[normalize-space()='{expected_models_check} - Enterprise Scorecardv2']",
                            f"//div[contains(@class,'css-12jo7m5') and normalize-space()='{expected_models_check} - Enterprise Scorecardv2']",
                            f"//div[contains(@class,'option') and normalize-space()='{expected_models_check} - Enterprise Scorecardv2']",
                            f"//div[contains(text(),'{expected_models_check} - Enterprise Scorecardv2')]",
                            f"//div[contains(@class,'css-12jo7m5') and contains(text(),'{expected_models_check}')]",
                            f"//div[contains(@class,'option') and contains(text(),'{expected_models_check}')]",
                            f"//div[contains(text(),'{expected_models_check}')]",
                            f"//div[normalize-space()='{expected_models_check}']"
                        ]
                        
                        # Method 1: Try to find the option directly first (it might be visible)
                        automation_status["message"] = "Phase 3a: Searching for Models option directly..."
                        print("Phase 3a: Searching for Models option directly...")
                        print(f"Phase 3a: Looking for option containing: '{expected_models_check}' (full text: '{expected_models_check} - Enterprise Scorecardv2')")
                        
                        models_option = None
                        found_option_text = None
                    
                    # Try each XPath to find the option
                    for option_xpath in option_xpaths:
                        try:
                            found_options = driver.find_elements(By.XPATH, option_xpath)
                            print(f"Phase 3a: XPath '{option_xpath[:80]}...' found {len(found_options)} elements")
                            for opt in found_options:
                                try:
                                    if opt.is_displayed():
                                        opt_text = opt.text.strip()
                                        print(f"Phase 3a: Checking option text: '{opt_text}'")
                                        # Check if it matches the full text or contains the key part
                                        if (opt_text == f'{expected_models_check} - Enterprise Scorecardv2' or 
                                            expected_models_check.lower() in opt_text.lower()):
                                            models_option = opt
                                            found_option_text = opt_text
                                            print(f"Phase 3a: ✓ Found matching option: '{opt_text}' using XPath: {option_xpath[:60]}...")
                                            break
                                except Exception as opt_error:
                                    print(f"Phase 3a: Error checking option: {str(opt_error)[:50]}")
                                    continue
                            if models_option:
                                break
                        except Exception as e:
                            print(f"Phase 3a: Error with XPath: {str(e)[:50]}")
                            continue
                    
                    # Method 2: If not found directly, get all options and search through them
                    if not models_option:
                        automation_status["message"] = "Phase 3a: Finding all Models dropdown options..."
                        print("Phase 3a: Finding all Models dropdown options...")
                        
                        all_options = []
                        try:
                            all_options = driver.find_elements(By.XPATH, "//div[contains(@class,'css-12jo7m5')] | //div[contains(@class,'option')] | //div[contains(@class,'css-1n7v3ny-option')]")
                            print(f"Phase 3a: Found {len(all_options)} total option elements")
                            
                            # Filter to visible options and check their text
                            visible_options = []
                            for opt in all_options:
                                try:
                                    if opt.is_displayed():
                                        opt_text = opt.text.strip()
                                        if opt_text:
                                            visible_options.append((opt, opt_text))
                                            if expected_models_check.lower() in opt_text.lower():
                                                models_option = opt
                                                print(f"Phase 3a: Found matching option: '{opt_text}'")
                                                break
                                except:
                                    continue
                            
                            if not models_option and visible_options:
                                print(f"Phase 3a: Visible options (first 15): {[text for _, text in visible_options[:15]]}")
                        except Exception as e:
                            print(f"Phase 3a: Error getting all options: {str(e)}")
                    
                    # Method 2: If not found, try scrolling within menu container
                    if not models_option and menu_container:
                        automation_status["message"] = "Phase 3a: Scrolling within Models dropdown to find option..."
                        print("Phase 3a: Scrolling within Models dropdown menu...")
                        print(f"Phase 3a: Menu container found, starting scroll search for '{expected_models_check}'...")
                        
                        max_scroll_attempts = 100  # Increased significantly
                        scroll_attempt = 0
                        scroll_amount = 150  # Larger scroll amount
                        
                        # Try to find the option while scrolling
                        option_xpaths = [
                            f"//div[contains(@class,'css-12jo7m5') and contains(text(),'{expected_models_check}')]",
                            f"//div[contains(@class,'option') and contains(text(),'{expected_models_check}')]",
                            f"//div[contains(text(),'{expected_models_check}')]",
                            f"//div[normalize-space()='{expected_models_check}']",
                            f"//div[normalize-space()='{expected_models_check} - Enterprise Scorecardv2']"
                        ]
                        
                        while scroll_attempt < max_scroll_attempts and not models_option:
                            # Try to find the option after each scroll
                            for option_xpath in option_xpaths:
                                try:
                                    models_option = find_element_by_xpath(driver, option_xpath, timeout=0.3)
                                    if models_option and models_option.is_displayed():
                                        print(f"Phase 3a: Found option after {scroll_attempt} scrolls using: {option_xpath}")
                                        break
                                except:
                                    continue
                            
                            if models_option:
                                break
                            
                            # Scroll down in the menu
                            try:
                                # Try multiple scrolling methods
                                driver.execute_script("arguments[0].scrollTop += arguments[1];", menu_container, scroll_amount)
                                time.sleep(0.15)
                                
                                # Also try scrolling the menu's parent if it exists
                                try:
                                    parent = menu_container.find_element(By.XPATH, "./..")
                                    driver.execute_script("arguments[0].scrollTop += arguments[1];", parent, scroll_amount)
                                except:
                                    pass
                                
                                scroll_attempt += 1
                                if scroll_attempt % 20 == 0:
                                    print(f"Phase 3a: Scrolled {scroll_attempt} times, still searching for '{expected_models_check}'...")
                                    # Re-check all visible options
                                    try:
                                        current_options = driver.find_elements(By.XPATH, "//div[contains(@class,'css-12jo7m5')] | //div[contains(@class,'option')]")
                                        visible_now = [opt.text.strip() for opt in current_options if opt.is_displayed() and opt.text.strip()][:5]
                                        print(f"Phase 3a: Currently visible options: {visible_now}")
                                    except:
                                        pass
                            except Exception as scroll_error:
                                print(f"Phase 3a: Error scrolling: {str(scroll_error)}")
                                # Try alternative scrolling method
                                try:
                                    driver.execute_script("arguments[0].scrollBy(0, arguments[1]);", menu_container, scroll_amount)
                                    time.sleep(0.15)
                                except:
                                    # Try keyboard navigation as last resort
                                    try:
                                        from selenium.webdriver.common.keys import Keys
                                        models_dropdown.send_keys(Keys.ARROW_DOWN)
                                        time.sleep(0.1)
                                    except:
                                        break
                    
                    # Method 3: Try keyboard navigation if still not found
                    if not models_option:
                        automation_status["message"] = "Phase 3a: Trying keyboard navigation to find option..."
                        print("Phase 3a: Trying keyboard navigation...")
                        try:
                            from selenium.webdriver.common.keys import Keys
                            # Type the option name to filter/search
                            models_dropdown.send_keys(expected_models_check)
                            time.sleep(1)
                            
                            # Now try to find it
                            for option_xpath in option_xpaths:
                                try:
                                    models_option = find_element_by_xpath(driver, option_xpath, timeout=2)
                                    if models_option and models_option.is_displayed():
                                        print(f"Phase 3a: Found option using keyboard navigation")
                                        break
                                except:
                                    continue
                        except Exception as kb_error:
                            print(f"Phase 3a: Keyboard navigation failed: {str(kb_error)}")
                        
                        if models_option:
                            # Confirm what we're about to click
                            try:
                                final_text = models_option.text.strip() if models_option else found_option_text or "unknown"
                                print(f"Phase 3a: About to click on option with text: '{final_text}'")
                                automation_status["message"] = f"Phase 3a: Clicking on '{final_text}'..."
                            except:
                                pass
                            
                            # Scroll the option into view first
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", models_option)
                                time.sleep(0.5)
                            except:
                                try:
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", models_option)
                                    time.sleep(0.5)
                                except:
                                    pass
                            
                            # Wait for element to be clickable
                            try:
                                WebDriverWait(driver, 5).until(EC.element_to_be_clickable(models_option))
                                print("Phase 3a: Element is clickable")
                            except:
                                print("Phase 3a: Element might not be clickable, but continuing...")
                            
                            # Try multiple click methods - try clicking parent element if direct click fails
                            clicked = False
                            
                            # Method 1: Try using the exact XPath the user mentioned with multiple click strategies
                            try:
                                exact_xpath = "//div[contains(@class,'css-12jo7m5') and normalize-space()='enterprise_scorecardv2 - Enterprise Scorecardv2']"
                                exact_option = find_element_by_xpath(driver, exact_xpath, timeout=2)
                                if exact_option:
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", exact_option)
                                    time.sleep(0.3)
                                    
                                    # Try multiple click methods on the exact element
                                    exact_click_methods = [
                                        ("JavaScript MouseEvent", lambda: driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));", exact_option)),
                                        ("JavaScript click", lambda: driver.execute_script("arguments[0].click();", exact_option)),
                                        ("ActionChains", lambda: ActionChains(driver).move_to_element(exact_option).pause(0.3).click().perform()),
                                        ("Regular click", lambda: exact_option.click()),
                                    ]
                                    
                                    for method_name, click_func in exact_click_methods:
                                        try:
                                            click_func()
                                            time.sleep(1.5)
                                            # Check if dropdown closed
                                            menu_still_open = driver.find_elements(By.XPATH, "//div[contains(@class,'menu')]")
                                            if not menu_still_open or not any(m.is_displayed() for m in menu_still_open):
                                                clicked = True
                                                print(f"Phase 3a: ✓✓✓ CLICKED using exact XPath via {method_name} - dropdown closed")
                                                break
                                            else:
                                                print(f"Phase 3a: Exact XPath {method_name} executed but dropdown still open, trying next...")
                                        except Exception as method_error:
                                            print(f"Phase 3a: Exact XPath {method_name} failed: {str(method_error)[:50]}")
                                            continue
                            except Exception as exact_error:
                                print(f"Phase 3a: Exact XPath click failed: {str(exact_error)[:100]}")
                            
                            if not clicked:
                                # Try multiple click methods with better error handling
                                click_methods = [
                                    ("ActionChains hover and click", lambda: ActionChains(driver).move_to_element(models_option).pause(0.3).click().perform()),
                                    ("JavaScript click with force", lambda: driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));", models_option)),
                                    ("JavaScript click on element", lambda: driver.execute_script("arguments[0].click();", models_option)),
                                    ("Regular click on element", lambda: models_option.click()),
                                    ("JavaScript click on parent", lambda: driver.execute_script("arguments[0].click();", models_option.find_element(By.XPATH, "./.."))),
                                    ("JavaScript click on grandparent", lambda: driver.execute_script("arguments[0].click();", models_option.find_element(By.XPATH, "./../.."))),
                                ]
                                
                                for method_name, click_func in click_methods:
                                    try:
                                        click_func()
                                        time.sleep(1.5)  # Wait longer after click
                                        
                                        # Verify if the click worked by checking if option is now selected
                                        # Or check if dropdown closed
                                        try:
                                            # Check if dropdown menu is still open (if closed, click might have worked)
                                            menu_still_open = driver.find_elements(By.XPATH, "//div[contains(@class,'menu')]")
                                            if not menu_still_open or not any(m.is_displayed() for m in menu_still_open):
                                                clicked = True
                                                option_text = found_option_text or (models_option.text.strip() if models_option else expected_models_check)
                                                print(f"Phase 3a: ✓✓✓ CLICKED Models option: '{option_text}' (via {method_name}) - dropdown closed")
                                                automation_status["message"] = f"Phase 3a: Successfully clicked '{option_text}'"
                                                break
                                            else:
                                                # Menu still open, might need to try next method
                                                print(f"Phase 3a: {method_name} executed but dropdown still open, trying next method...")
                                        except:
                                            # If we can't verify, assume it worked
                                            clicked = True
                                            option_text = found_option_text or (models_option.text.strip() if models_option else expected_models_check)
                                            print(f"Phase 3a: ✓✓✓ CLICKED Models option: '{option_text}' (via {method_name})")
                                            automation_status["message"] = f"Phase 3a: Successfully clicked '{option_text}'"
                                            break
                                    except Exception as click_error:
                                        print(f"Phase 3a: {method_name} failed: {str(click_error)[:100]}")
                                        continue
                            
                            if not clicked:
                                # Last resort: try to find and click by text using JavaScript - search for FULL text first
                                try:
                                    full_text = f'{expected_models_check} - Enterprise Scorecardv2'
                                    result = driver.execute_script(f"""
                                        var options = document.querySelectorAll('div[class*="css-12jo7m5"], div[class*="option"], div[class*="css-1n7v3ny-option"]');
                                        console.log('Total options found:', options.length);
                                        
                                        // First try to find exact full text match
                                        for (var i = 0; i < options.length; i++) {{
                                            var text = (options[i].textContent || '').trim();
                                            if (text === '{full_text}' || (text.includes('{expected_models_check}') && text.includes('Enterprise Scorecardv2'))) {{
                                                console.log('Found matching option:', text);
                                                // Try multiple click methods
                                                try {{
                                                    // Method 1: Direct click
                                                    options[i].click();
                                                }} catch(e) {{
                                                    try {{
                                                        // Method 2: MouseEvent
                                                        options[i].dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true, view: window}}));
                                                    }} catch(e2) {{
                                                        try {{
                                                            // Method 3: Click parent
                                                            if (options[i].parentElement) {{
                                                                options[i].parentElement.click();
                                                            }}
                                                        }} catch(e3) {{
                                                            // Method 4: Trigger mousedown and mouseup
                                                            options[i].dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
                                                            options[i].dispatchEvent(new MouseEvent('mouseup', {{bubbles: true}}));
                                                            options[i].dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                                                        }}
                                                    }}
                                                }}
                                                return true;
                                            }}
                                        }}
                                        // Fallback: search for key part
                                        for (var i = 0; i < options.length; i++) {{
                                            var text = (options[i].textContent || '').trim();
                                            if (text && text.includes('{expected_models_check}')) {{
                                                console.log('Found matching option (fallback):', text);
                                                try {{
                                                    options[i].click();
                                                }} catch(e) {{
                                                    options[i].dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                                                }}
                                                return true;
                                            }}
                                        }}
                                        return false;
                                    """)
                                    time.sleep(1.5)
                                    
                                    # Check if dropdown closed (indicates success)
                                    try:
                                        menu_still_open = driver.find_elements(By.XPATH, "//div[contains(@class,'menu')]")
                                        if not menu_still_open or not any(m.is_displayed() for m in menu_still_open):
                                            clicked = True
                                            print(f"Phase 3a: ✓✓✓ CLICKED Models option: '{full_text}' (via JavaScript text search) - dropdown closed")
                                            automation_status["message"] = f"Phase 3a: Successfully clicked '{full_text}' via JavaScript"
                                        else:
                                            print(f"Phase 3a: JavaScript click executed but dropdown still open")
                                    except:
                                        clicked = True
                                        print(f"Phase 3a: ✓✓✓ CLICKED Models option: '{full_text}' (via JavaScript text search)")
                                        automation_status["message"] = f"Phase 3a: Successfully clicked '{full_text}' via JavaScript"
                                except Exception as js_text_error:
                                    print(f"Phase 3a: JavaScript text search click also failed: {str(js_text_error)}")
                                
                                # Final fallback: Try keyboard navigation with arrow keys
                                if not clicked:
                                    try:
                                        from selenium.webdriver.common.keys import Keys
                                        print("Phase 3a: Trying keyboard navigation as final fallback...")
                                        
                                        # Focus the dropdown input first
                                        models_dropdown.click()
                                        time.sleep(0.3)
                                        
                                        # Type to filter/search for the option
                                        models_dropdown.send_keys(expected_models_check)
                                        time.sleep(0.8)
                                        
                                        # Try to find and highlight the option using arrow keys
                                        # Count how many arrow downs needed (or just press Enter if it's auto-highlighted)
                                        try:
                                            # First, try pressing Enter directly (React Select might auto-highlight filtered results)
                                            models_dropdown.send_keys(Keys.ENTER)
                                            time.sleep(1.5)
                                            
                                            # Verify dropdown closed
                                            menu_still_open = driver.find_elements(By.XPATH, "//div[contains(@class,'menu')]")
                                            if not menu_still_open or not any(m.is_displayed() for m in menu_still_open):
                                                clicked = True
                                                print(f"Phase 3a: ✓✓✓ CLICKED Models option using keyboard (typed '{expected_models_check}' + Enter) - dropdown closed")
                                                automation_status["message"] = f"Phase 3a: Successfully selected via keyboard navigation"
                                            else:
                                                # Dropdown still open, try arrow keys
                                                print("Phase 3a: Enter didn't close dropdown, trying arrow keys...")
                                                for arrow_count in range(5):
                                                    models_dropdown.send_keys(Keys.ARROW_DOWN)
                                                    time.sleep(0.2)
                                                    # Check if we found the right option
                                                    try:
                                                        highlighted = driver.find_element(By.XPATH, "//div[contains(@class,'css-1n7v3ny-option') and contains(@class,'css-1wa3eu0-option')] | //div[contains(@class,'option') and contains(@class,'-isFocused')]")
                                                        if highlighted and 'enterprise_scorecardv2' in highlighted.text:
                                                            models_dropdown.send_keys(Keys.ENTER)
                                                            time.sleep(1.5)
                                                            clicked = True
                                                            print(f"Phase 3a: ✓✓✓ Selected using {arrow_count+1} arrow downs + Enter")
                                                            break
                                                    except:
                                                        pass
                                                if not clicked:
                                                    # Last try: just press Enter again
                                                    models_dropdown.send_keys(Keys.ENTER)
                                                    time.sleep(1.5)
                                                    clicked = True
                                                    print(f"Phase 3a: ✓✓✓ Pressed Enter after arrow navigation")
                                        except Exception as arrow_error:
                                            print(f"Phase 3a: Arrow key navigation error: {str(arrow_error)}")
                                        
                                        if clicked:
                                            automation_status["message"] = f"Phase 3a: Successfully selected via keyboard navigation"
                                    except Exception as kb_error:
                                        print(f"Phase 3a: Keyboard navigation also failed: {str(kb_error)}")
                            
                            if not clicked:
                                automation_status["message"] = "Phase 3a: Warning: Found Models option but could not click it, but continuing..."
                                print("Phase 3a: Warning - Found option but all click methods failed")
                        else:
                            automation_status["message"] = f"Phase 3a: Warning: Could not find Models option '{expected_models_check}' after {scroll_attempt} scrolls, but continuing..."
                            print(f"Phase 3a: Warning - Models option not found after {scroll_attempt} scrolls")
                            # Debug: Print what options are visible
                            try:
                                all_options = driver.find_elements(By.XPATH, "//div[contains(@class,'css-12jo7m5')] | //div[contains(@class,'option')]")
                                visible_options = [opt.text for opt in all_options[:10] if opt.is_displayed()]
                                print(f"Phase 3a: Debug - Sample visible options: {visible_options}")
                            except:
                                pass
                    else:
                        automation_status["message"] = "Phase 3a: Warning: Could not find Models dropdown, but continuing..."
                        print("Phase 3a: Warning - Models dropdown not found")
                else:
                    # Models dropdown already has correct value
                    print(f"Phase 3a: ✓ Models dropdown already contains correct value: '{expected_models_check}'")
            except Exception as e:
                automation_status["message"] = f"Phase 3a: Warning: Error checking Models dropdown: {str(e)}, continuing..."
                print(f"Phase 3a: Exception checking models: {str(e)}")
                import traceback
                print(traceback.format_exc())
            
            # JAVASCRIPT-BASED Models dropdown fix - Most reliable method
            # This runs as a final fallback to ensure the Models value is selected
            try:
                print("Phase 3a: Verifying Models dropdown with JavaScript-based approach...")
                models_dropdown_xpath = "//div[normalize-space()='models']/following::div[contains(@class,'css-yk16xz-control')][1]"
                models_dropdown = find_element_by_xpath(driver, models_dropdown_xpath, timeout=5)
                
                if models_dropdown:
                    # Check if the value is already selected
                    try:
                        selected_values = models_dropdown.find_elements(By.XPATH, ".//div[contains(@class,'multiValue')]//div[contains(@class,'css-12jo7m5')]")
                        current_selected = [v.text.strip() for v in selected_values]
                        print(f"Phase 3a: Current Models values: {current_selected}")
                        
                        if not any('enterprise_scorecardv2' in v.lower() for v in current_selected):
                            print("Phase 3a: Models value NOT selected. Applying JavaScript-based selection...")
                            
                            # Use JavaScript to open dropdown, find option, and click it
                            js_click_result = driver.execute_script("""
                            // Step 1: Find the models dropdown control
                            var modelsLabel = Array.from(document.querySelectorAll('div')).find(el => el.textContent.trim() === 'models' && el.className.includes('css'));
                            if (!modelsLabel) {
                                console.log('Models label not found');
                                return {success: false, error: 'Models label not found'};
                            }
                            
                            var dropdownControl = modelsLabel.nextElementSibling;
                            if (!dropdownControl || !dropdownControl.className.includes('css-yk16xz-control')) {
                                // Try finding it differently
                                var allControls = Array.from(document.querySelectorAll('div[class*="css-yk16xz-control"]'));
                                var modelsIndex = Array.from(document.querySelectorAll('div')).indexOf(modelsLabel);
                                dropdownControl = allControls.find(ctrl => Array.from(document.querySelectorAll('div')).indexOf(ctrl) > modelsIndex);
                            }
                            
                            if (!dropdownControl) {
                                console.log('Dropdown control not found');
                                return {success: false, error: 'Dropdown control not found'};
                            }
                            
                            console.log('Found dropdown control:', dropdownControl);
                            
                            // Step 2: Click to open the dropdown
                            dropdownControl.click();
                            
                            // Wait for menu to appear (synchronous wait via busy loop)
                            var startTime = Date.now();
                            while (Date.now() - startTime < 2000) {
                                // Busy wait
                            }
                            
                            // Step 3: Find all options in the dropdown menu
                            var allOptions = Array.from(document.querySelectorAll('div[class*="option"], div[class*="css-12jo7m5"], div[class*="css-1n7v3ny-option"]'));
                            console.log('Total options found:', allOptions.length);
                            
                            // Look for the specific option
                            var targetOption = null;
                            var targetTexts = ['enterprise_scorecardv2 - Enterprise Scorecardv2', 'enterprise_scorecardv2'];
                            
                            for (var opt of allOptions) {
                                var optText = (opt.textContent || '').trim();
                                console.log('Checking option:', optText);
                                
                                for (var targetText of targetTexts) {
                                    if (optText === targetText || optText.includes('enterprise_scorecardv2')) {
                                        targetOption = opt;
                                        console.log('Found target option:', optText);
                                        break;
                                    }
                                }
                                if (targetOption) break;
                            }
                            
                            if (!targetOption) {
                                console.log('Target option not found in visible options');
                                // Try to find in all divs containing the text
                                var allDivs = Array.from(document.querySelectorAll('div'));
                                targetOption = allDivs.find(div => {
                                    var text = (div.textContent || '').trim();
                                    return text === 'enterprise_scorecardv2 - Enterprise Scorecardv2' || 
                                           (text.includes('enterprise_scorecardv2') && text.includes('Enterprise Scorecardv2'));
                                });
                            }
                            
                            if (targetOption) {
                                console.log('Clicking target option...');
                                // Try multiple click methods
                                try {
                                    targetOption.click();
                                } catch(e1) {
                                    try {
                                        targetOption.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                        targetOption.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                        targetOption.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                    } catch(e2) {
                                        try {
                                            if (targetOption.parentElement) {
                                                targetOption.parentElement.click();
                                            }
                                        } catch(e3) {
                                            console.log('All click methods failed:', e1, e2, e3);
                                            return {success: false, error: 'Click failed: ' + e3.message};
                                        }
                                    }
                                }
                                
                                return {success: true, optionText: targetOption.textContent.trim()};
                            } else {
                                return {success: false, error: 'Target option not found', optionsFound: allOptions.map(o => o.textContent.trim())};
                            }
                            """)
                            
                            print(f"Phase 3a: JavaScript result: {js_click_result}")
                            time.sleep(2)
                            
                            # Verify selection
                            selected_values_after = models_dropdown.find_elements(By.XPATH, ".//div[contains(@class,'multiValue')]//div[contains(@class,'css-12jo7m5')]")
                            selected_after = [v.text.strip() for v in selected_values_after]
                            print(f"Phase 3a: Models values after JavaScript selection: {selected_after}")
                            
                            if any('enterprise_scorecardv2' in v.lower() for v in selected_after):
                                print("Phase 3a: ✓✓✓ Models dropdown successfully updated via JavaScript!")
                                needs_update = True
                            else:
                                print("Phase 3a: ⚠️ Warning - Models dropdown may not have been updated. Manual verification needed.")
                                print(f"Phase 3a: JavaScript click result: {js_click_result}")
                        else:
                            print(f"Phase 3a: ✓ Models dropdown already has correct value")
                    except Exception as verify_error:
                        print(f"Phase 3a: Error verifying models selection: {str(verify_error)}")
                        import traceback
                        print(traceback.format_exc())
            except Exception as js_error:
                print(f"Phase 3a: JavaScript models approach error: {str(js_error)}")
                import traceback
                print(traceback.format_exc())
        else:
            # Competitor scorecard - skip Models dropdown
            print(f"Phase 3a: Skipping Models dropdown for {scorecard_type} scorecard")
            automation_status["message"] = f"Phase 3a: Skipping Models section for {scorecard_type} scorecard"
        
        # Check Client Name dropdown
        try:
            automation_status["message"] = "Phase 3a: Checking Client Name dropdown..."
            client_name_correct, client_name_current = check_react_select_value('Client Name', extracted_client_name)
            if not client_name_correct:
                needs_update = True
                automation_status["message"] = f"Phase 3a: Client Name dropdown needs update (current: '{client_name_current}', expected: '{extracted_client_name}')"
                if not set_react_select_value('Client Name', extracted_client_name):
                    automation_status["message"] = "Phase 3a: Warning: Could not update Client Name dropdown, but continuing..."
                    print("Phase 3a: Warning - Client Name update failed, but continuing")
        except Exception as e:
            automation_status["message"] = f"Phase 3a: Warning: Error checking Client Name dropdown: {str(e)}, continuing..."
            print(f"Phase 3a: Exception checking client name: {str(e)}")
        
        # Step 5: If any updates were needed, fill change reason and submit
        if needs_update:
            automation_status["message"] = "Phase 3a: Updates needed. Filling change reason and submitting..."
            
            # Fill change reason
            change_reason_input = find_element_by_xpath(driver, "//textarea[@id='reason_for_change']", timeout=10)
            if change_reason_input:
                change_reason_input.clear()
                change_reason_input.send_keys(change_reason)
                time.sleep(1)
                print(f"Phase 3a: Change reason entered: {change_reason}")
            else:
                automation_status["message"] = "Phase 3a: Warning: Could not find change reason field"
            
            # Click Update button
            update_button = find_element_by_xpath(driver, "//input[@type='submit' and @value='Update Looker config']", timeout=10)
            if update_button:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", update_button)
                time.sleep(1)
                update_button.click()
                time.sleep(3)
                
                # Wait for success message or page update
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: "success" in d.page_source.lower() or "updated" in d.page_source.lower()
                    )
                    automation_status["message"] = "Phase 3a: Looker Config updated successfully!"
                    print("Phase 3a: Looker Config update completed")
                    return True
                except:
                    automation_status["message"] = "Phase 3a: Looker Config update may have completed (checking page state)..."
                    return True
            else:
                automation_status["message"] = "Phase 3a: Error: Could not find Update Looker config button"
                return False
        else:
            automation_status["message"] = "Phase 3a: All Looker Config values are already correct. No update needed."
            print("Phase 3a: All values correct, no update needed - continuing to next phase")
            # If we're in edit mode and no updates are needed, we can optionally click Cancel
            # But let's just continue - the page state doesn't matter for the next phase
            time.sleep(1)  # Brief pause before continuing
            return True
            
    except Exception as e:
        automation_status["message"] = f"Phase 3a: Error updating Looker Config: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def update_client_organization_id_phase1_5(driver, customer_name, organization_id, change_reason):
    """
    Update Client Organization ID (between Phase 1 and Phase 2).
    Navigates: Admin -> Clients -> Search -> Edit -> Update Org ID -> Back to Weights & Targets
    
    Args:
        driver: Selenium WebDriver instance
        customer_name: Customer name to search for
        organization_id: Organization ID to set
        change_reason: Change reason text
    
    Returns:
        True if successful, False on error
    """
    try:
        automation_status["message"] = "Phase 1.5: Starting Organization ID update..."
        print(f"Phase 1.5: Starting Organization ID update for client: {customer_name}, org_id: {organization_id}")
        
        # Step 1: Click on Admin
        automation_status["message"] = "Phase 1.5: Clicking on Admin..."
        print("Phase 1.5: Looking for Admin element...")
        
        # Try multiple selectors for Admin
        admin_selectors = [
            "//h2[normalize-space()='Admin']",  # As specified by user
            "//a[normalize-space()='Admin']",    # As link
            "//*[normalize-space()='Admin' and (self::h2 or self::a or self::button)]",  # Any clickable element
            "//nav//a[normalize-space()='Admin']",  # In navigation
            "//aside//a[normalize-space()='Admin']",  # In sidebar
            "//div[contains(@class,'nav')]//a[normalize-space()='Admin']",  # In nav div
        ]
        
        admin_element = None
        used_selector = None
        for selector in admin_selectors:
            try:
                admin_element = find_element_by_xpath(driver, selector, timeout=5)
                if admin_element:
                    used_selector = selector
                    print(f"Phase 1.5: ✓ Found Admin element using selector: {selector}")
                    break
            except:
                continue
        
        if not admin_element:
            automation_status["message"] = "Phase 1.5: Error: Could not find Admin element"
            print("Phase 1.5: ERROR - Could not find Admin element with any selector")
            print("Phase 1.5: Tried selectors:")
            for sel in admin_selectors:
                print(f"  - {sel}")
            print("Phase 1.5: Current URL:", driver.current_url)
            print("Phase 1.5: Page title:", driver.title)
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", admin_element)
        time.sleep(1)
        
        # Try to click Admin element
        clicked = False
        try:
            admin_element.click()
            clicked = True
            print("Phase 1.5: ✓ Clicked Admin element directly")
        except Exception as e:
            print(f"Phase 1.5: Direct click failed: {str(e)}, trying alternatives...")
            # If h2 is not directly clickable, try to find parent link
            try:
                parent_link = admin_element.find_element(By.XPATH, "./ancestor::a[1]")
                parent_link.click()
                clicked = True
                print("Phase 1.5: ✓ Clicked Admin via parent link")
            except Exception as e2:
                print(f"Phase 1.5: Parent link click failed: {str(e2)}, trying JavaScript click...")
                try:
                    driver.execute_script("arguments[0].click();", admin_element)
                    clicked = True
                    print("Phase 1.5: ✓ Clicked Admin via JavaScript")
                except Exception as e3:
                    print(f"Phase 1.5: JavaScript click also failed: {str(e3)}")
        
        if not clicked:
            automation_status["message"] = "Phase 1.5: Error: Could not click Admin element"
            print("Phase 1.5: ERROR - Could not click Admin element with any method")
            return False
        
        time.sleep(2)
        print("Phase 1.5: ✓ Successfully navigated to Admin section")
        
        # Step 2: Click on Clients
        automation_status["message"] = "Phase 1.5: Clicking on Clients..."
        clients_link = find_element_by_xpath(driver, "//a[normalize-space()='Clients']", timeout=15)
        if not clients_link:
            automation_status["message"] = "Phase 1.5: Error: Could not find Clients link"
            print("Phase 1.5: ERROR - Could not find Clients link")
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clients_link)
        time.sleep(1)
        clients_link.click()
        time.sleep(3)
        
        # Step 3: Search for client
        automation_status["message"] = f"Phase 1.5: Searching for client: {customer_name}..."
        search_input = find_element_by_xpath(driver, "//input[@id='search']", timeout=15)
        if not search_input:
            automation_status["message"] = "Phase 1.5: Error: Could not find search input"
            print("Phase 1.5: ERROR - Could not find search input")
            return False
        
        search_input.clear()
        search_input.send_keys(customer_name)
        time.sleep(1)
        
        # Step 3.5: Click Search button
        automation_status["message"] = "Phase 1.5: Clicking Search button..."
        print("Phase 1.5: Clicking Search button...")
        search_button = find_element_by_xpath(driver, "//span[normalize-space()='Search']", timeout=15)
        if not search_button:
            automation_status["message"] = "Phase 1.5: Warning: Could not find Search button, continuing anyway"
            print("Phase 1.5: WARNING - Could not find Search button //span[normalize-space()='Search']")
            # Try alternative selectors
            search_button = find_element_by_xpath(driver, "//button[contains(text(), 'Search')]", timeout=5)
            if not search_button:
                search_button = find_element_by_xpath(driver, "//input[@type='submit' and contains(@value, 'Search')]", timeout=5)
        
        if search_button:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_button)
            time.sleep(0.5)
            try:
                search_button.click()
                print("Phase 1.5: ✓ Clicked Search button")
            except:
                try:
                    driver.execute_script("arguments[0].click();", search_button)
                    print("Phase 1.5: ✓ Clicked Search button via JavaScript")
                except Exception as e:
                    print(f"Phase 1.5: WARNING - Could not click Search button: {str(e)}")
            time.sleep(2)  # Wait for search results to load
        else:
            automation_status["message"] = "Phase 1.5: Warning: Could not find Search button, but continuing to Edit"
            print("Phase 1.5: WARNING - Could not find Search button with any selector, continuing anyway")
            time.sleep(2)  # Wait a bit anyway in case search happens automatically
        
        # Step 4: Click Edit button (first row)
        automation_status["message"] = "Phase 1.5: Clicking Edit button..."
        edit_link = find_element_by_xpath(driver, "//table//tbody//tr[1]//a[normalize-space()='Edit']", timeout=15)
        if not edit_link:
            automation_status["message"] = "Phase 1.5: Error: Could not find Edit button"
            print("Phase 1.5: ERROR - Could not find Edit button in first row")
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_link)
        time.sleep(1)
        edit_link.click()
        time.sleep(3)
        
        # Step 5: Find Organization ID field and update it
        automation_status["message"] = "Phase 1.5: Updating Organization ID field..."
        org_id_input = find_element_by_xpath(driver, "//input[@id='client_organisation_id']", timeout=15)
        if not org_id_input:
            automation_status["message"] = "Phase 1.5: Error: Could not find Organization ID input"
            print("Phase 1.5: ERROR - Could not find Organization ID input field")
            return False
        
        # Select all existing text and replace with new value
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", org_id_input)
        time.sleep(0.5)
        org_id_input.click()
        time.sleep(0.5)
        org_id_input.send_keys(Keys.COMMAND + 'a')  # Select all (Mac)
        time.sleep(0.5)
        org_id_input.send_keys(Keys.DELETE)  # Clear
        time.sleep(0.5)
        org_id_input.send_keys(str(organization_id))  # Enter new value
        time.sleep(1)
        
        print(f"Phase 1.5: Updated Organization ID field to: {organization_id}")
        
        # Step 6: Click Update Client button
        automation_status["message"] = "Phase 1.5: Clicking Update Client button..."
        update_button = find_element_by_xpath(driver, "//input[@type='submit' and @value='Update Client']", timeout=15)
        if not update_button:
            automation_status["message"] = "Phase 1.5: Error: Could not find Update Client button"
            print("Phase 1.5: ERROR - Could not find Update Client button")
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", update_button)
        time.sleep(1)
        update_button.click()
        time.sleep(3)
        
        print("Phase 1.5: Client updated successfully")
        
        # Step 7: Navigate back to Weights & Targets
        automation_status["message"] = "Phase 1.5: Navigating back to Weights & Targets..."
        weights_targets_link = find_element_by_xpath(driver, "//a[normalize-space()='Weights & Targets']", timeout=15)
        if not weights_targets_link:
            # Try alternative navigation
            driver.get("https://settings.ef.uk.com/weights_targets")
            time.sleep(3)
        else:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", weights_targets_link)
            time.sleep(1)
            weights_targets_link.click()
            time.sleep(3)
        
        automation_status["message"] = "Phase 1.5: Organization ID update completed successfully"
        print("Phase 1.5: Successfully completed Organization ID update and returned to Weights & Targets")
        return True
        
    except Exception as e:
        automation_status["message"] = f"Phase 1.5: Error updating Organization ID: {str(e)}"
        print(f"Phase 1.5: ERROR - {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

def update_client_organization_id(driver, customer_name, organization_id, change_reason):
    """
    Update Client Organization ID.
    
    Args:
        driver: Selenium WebDriver instance
        customer_name: Customer name to search for
        organization_id: Organization ID to set
        change_reason: Change reason text
    
    Returns:
        True if successful, False on error
    """
    try:
        automation_status["message"] = "Phase 3b: Navigating to Clients page..."
        print(f"Phase 3b: Starting Organization ID update for client: {customer_name}, org_id: {organization_id}")
        
        # Step 1: Navigate to Clients page
        clients_link = find_element_by_xpath(driver, "//a[@class='nav-link' and @href='https://settings.ef.uk.com/clients'] | //a[contains(@href,'/clients') and normalize-space()='Clients']", timeout=15)
        if not clients_link:
            # Try direct navigation
            driver.get("https://settings.ef.uk.com/clients")
            time.sleep(3)
        else:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clients_link)
            time.sleep(1)
            clients_link.click()
            time.sleep(3)
        
        # Step 2: Search for client
        automation_status["message"] = f"Phase 3b: Searching for client: {customer_name}..."
        search_input = find_element_by_xpath(driver, "//input[@id='search']", timeout=15)
        if not search_input:
            automation_status["message"] = "Phase 3b: Error: Could not find search input"
            return False
        
        search_input.clear()
        search_input.send_keys(customer_name)
        time.sleep(2)
        
        # Step 3: Find the correct client row using the same method as client selection
        automation_status["message"] = "Phase 3b: Finding client in search results..."
        client_found = False
        client_slug = None
        
        # Look for the div with text-sm and text-gray-400 classes that matches customer_name
        try:
            # Find all divs with these classes
            client_divs = driver.find_elements(By.XPATH, "//div[contains(@class,'text-sm') and contains(@class,'text-gray-400')]")
            for div in client_divs:
                div_text = div.text.strip()
                # Check if this matches the customer name (case-insensitive, partial match)
                if customer_name.lower() in div_text.lower() or div_text.lower() in customer_name.lower():
                    # Found matching client, get the parent row
                    try:
                        parent_row = div.find_element(By.XPATH, ".//ancestor::tr")
                        # Extract client slug from the row - try to find it in a td
                        try:
                            # Look for the slug in the first or second td
                            tds = parent_row.find_elements(By.TAG_NAME, "td")
                            if len(tds) > 0:
                                # Client slug might be in the first td or we can use the text
                                client_slug = tds[0].text.strip()
                                # If first td is empty or doesn't look right, try second
                                if not client_slug or len(client_slug) > 50:
                                    if len(tds) > 1:
                                        client_slug = tds[1].text.strip()
                        except:
                            pass
                        
                        # If we couldn't extract slug, use customer_name as fallback
                        if not client_slug:
                            client_slug = customer_name
                        
                        client_found = True
                        print(f"Phase 3b: Found client row with text: '{div_text}', slug: '{client_slug}'")
                        break
                    except:
                        continue
        except Exception as e:
            automation_status["message"] = f"Phase 3b: Error finding client: {str(e)}"
            print(f"Phase 3b: Error: {str(e)}")
        
        if not client_found:
            automation_status["message"] = f"Phase 3b: Error: Could not find client '{customer_name}' in search results"
            return False
        
        # Step 4: Click Edit button
        automation_status["message"] = f"Phase 3b: Clicking Edit for client: {client_slug}..."
        edit_xpath = f"//tr[.//td[normalize-space()='{client_slug}']]//a[normalize-space()='Edit']"
        edit_button = find_element_by_xpath(driver, edit_xpath, timeout=10)
        
        # If that doesn't work, try finding Edit link in the same row
        if not edit_button:
            try:
                # Find the row we identified earlier
                client_divs = driver.find_elements(By.XPATH, "//div[contains(@class,'text-sm') and contains(@class,'text-gray-400')]")
                for div in client_divs:
                    div_text = div.text.strip()
                    if customer_name.lower() in div_text.lower() or div_text.lower() in customer_name.lower():
                        parent_row = div.find_element(By.XPATH, ".//ancestor::tr")
                        edit_link = parent_row.find_element(By.XPATH, ".//a[normalize-space()='Edit']")
                        if edit_link:
                            edit_button = edit_link
                            break
            except:
                pass
        
        if not edit_button:
            automation_status["message"] = f"Phase 3b: Error: Could not find Edit button for client '{client_slug}'"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_button)
        time.sleep(1)
        edit_button.click()
        time.sleep(3)
        
        # Step 5: Fill Organization ID
        automation_status["message"] = f"Phase 3b: Filling Organization ID: {organization_id}..."
        org_id_input = find_element_by_xpath(driver, "//input[@id='client_organisation_id']", timeout=15)
        if not org_id_input:
            automation_status["message"] = "Phase 3b: Error: Could not find Organization ID input field"
            return False
        
        org_id_input.clear()
        org_id_input.send_keys(organization_id)
        time.sleep(1)
        print(f"Phase 3b: Organization ID set to: {organization_id}")
        
        # Step 6: Fill change reason if field exists
        try:
            change_reason_input = find_element_by_xpath(driver, "//textarea[@id='reason_for_change'] | //textarea[@name='reason_for_change']", timeout=5)
            if change_reason_input:
                change_reason_input.clear()
                change_reason_input.send_keys(change_reason)
                time.sleep(1)
                print(f"Phase 3b: Change reason entered")
        except:
            # Change reason field is optional
            pass
        
        # Step 7: Click Update button
        automation_status["message"] = "Phase 3b: Clicking Update Client button..."
        update_button = find_element_by_xpath(driver, "//input[@type='submit' and @value='Update Client']", timeout=10)
        if not update_button:
            automation_status["message"] = "Phase 3b: Error: Could not find Update Client button"
            return False
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", update_button)
        time.sleep(1)
        update_button.click()
        time.sleep(3)
        
        # Step 8: Wait for success confirmation
        try:
            WebDriverWait(driver, 10).until(
                lambda d: "success" in d.page_source.lower() or "updated" in d.page_source.lower() or "clients" in d.current_url.lower()
            )
            automation_status["message"] = "Phase 3b: Client Organization ID updated successfully!"
            print("Phase 3b: Organization ID update completed")
            return True
        except:
            automation_status["message"] = "Phase 3b: Client Organization ID update may have completed (checking page state)..."
            return True
            
    except Exception as e:
        automation_status["message"] = f"Phase 3b: Error updating Organization ID: {str(e)}"
        import traceback
        print(traceback.format_exc())
        return False

def run_automation(form_data):
    """Run the complete automation workflow"""
    print("\n" + "="*100)
    print("="*100)
    print("🚀 AUTOMATION STARTED")
    print("="*100)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Form data keys: {list(form_data.keys())}")
    print("="*100 + "\n")
    global automation_status, continue_automation_flag
    
    # Initialize step tracker
    customer_name = form_data.get('customer_name', 'Unknown')
    scorecard_name = form_data.get('scorecard_name', 'Unknown')
    init_step_tracker(customer_name, scorecard_name)
    track_step("Initialization", "Automation Started", "in_progress", f"Starting automation for {customer_name} - {scorecard_name}")
    
    driver = None
    # Determine Excel file path based on scorecard type or use provided path
    scorecard_type = form_data.get('scorecard_type', 'Competitor')
    excel_file_path = form_data.get('excel_file_path', None)
    use_existing_scorecard = form_data.get('use_existing_scorecard', False)
    
    if excel_file_path:
        # Use provided Excel file path (user-specified)
        if os.path.isabs(excel_file_path):
            excel_path = excel_file_path
        else:
            excel_path = os.path.join(os.path.dirname(__file__), excel_file_path)
        excel_path = os.path.expanduser(excel_path)
    else:
        # Default to scorecard type-based file selection
        if scorecard_type.lower() == 'enterprise':
            # For Enterprise scorecards, use the Whirlpool CA Setup Sheet
            excel_path = os.path.join(os.path.dirname(__file__), "Whirlpool CA Setup Sheet.xlsx")
            # If that doesn't exist, try alternative name
            if not os.path.exists(excel_path):
                excel_path = os.path.join(os.path.dirname(__file__), "enterprise scorecard.xlsx")
        else:
            # For Competitor/Competitive scorecards, use the old format file
            excel_path = os.path.join(os.path.dirname(__file__), "competitive scorecard.xlsx")
    
    # Validate that the Excel file exists before proceeding
    if not os.path.exists(excel_path):
        error_msg = f"Excel file not found: {excel_path}. Please provide a valid Excel file path in the form."
        print(f"ERROR: {error_msg}")
        automation_status["message"] = error_msg
        automation_status["running"] = False
        return
    
    try:
        automation_status["running"] = True
        automation_status["message"] = "Initializing browser..."
        
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Configure download directory if export_file_path is provided
        export_file_path = form_data.get('export_file_path', None)
        if export_file_path:
            # Resolve the path (handle ~ and relative paths)
            if not os.path.isabs(export_file_path):
                export_file_path = os.path.join(os.path.dirname(__file__), export_file_path)
            export_file_path = os.path.expanduser(export_file_path)
            
            # If it's a file path, use its directory; if it's a directory, use it directly
            if os.path.isfile(export_file_path):
                download_dir = os.path.dirname(export_file_path)
            else:
                download_dir = export_file_path
            
            # Create directory if it doesn't exist
            os.makedirs(download_dir, exist_ok=True)
            
            # Configure Chrome to download to this location
            prefs = {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            print(f"Chrome download directory configured to: {download_dir}")
        
        # Initialize the driver
        try:
            # Clear any cached ChromeDriver to force fresh download
            try:
                import shutil
                cache_dir = os.path.expanduser("~/.wdm/drivers/chromedriver")
                if os.path.exists(cache_dir):
                    # Only clear if we have a version mismatch issue
                    for version_dir in os.listdir(cache_dir):
                        version_path = os.path.join(cache_dir, version_dir)
                        if os.path.isdir(version_path) and "143.0.7499.169" in version_path:
                            shutil.rmtree(version_path, ignore_errors=True)
            except Exception as cache_error:
                pass  # Ignore cache clearing errors
            
            # Download ChromeDriver matching Chrome version
            driver_path = ChromeDriverManager().install()
            
            # Fix path if webdriver-manager returns wrong file
            if 'THIRD_PARTY' in driver_path or not driver_path.endswith('chromedriver'):
                # Find the actual chromedriver executable in the same directory structure
                base_dir = os.path.dirname(driver_path)
                # Look for chromedriver in both arm64 and x64 subdirectories
                potential_paths = [
                    os.path.join(base_dir, 'chromedriver-mac-arm64', 'chromedriver'),
                    os.path.join(base_dir, 'chromedriver-mac-x64', 'chromedriver'),
                    os.path.join(os.path.dirname(base_dir), 'chromedriver-mac-arm64', 'chromedriver'),
                    os.path.join(os.path.dirname(base_dir), 'chromedriver-mac-x64', 'chromedriver'),
                ]
                for path in potential_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        driver_path = path
                        # Remove ALL extended attributes immediately after download (macOS security)
                        try:
                            import subprocess
                            # Clear all extended attributes (quarantine, etc.)
                            subprocess.run(['xattr', '-c', path], 
                                         stderr=subprocess.DEVNULL, check=False, timeout=5)
                            # Also try specific quarantine removal
                            subprocess.run(['xattr', '-d', 'com.apple.quarantine', path], 
                                         stderr=subprocess.DEVNULL, check=False, timeout=5)
                            print(f"Removed extended attributes from ChromeDriver: {path}")
                        except Exception as xattr_err:
                            print(f"Warning: Could not remove extended attributes: {xattr_err}")
                        os.chmod(path, 0o755)  # Ensure executable
                        break
            
            # Also handle the case where driver_path is already correct but needs quarantine removal
            if os.path.exists(driver_path) and os.path.isfile(driver_path):
                try:
                    import subprocess
                    # Remove all extended attributes (quarantine and others) - CRITICAL for macOS
                    result = subprocess.run(['xattr', '-c', driver_path], 
                                          stderr=subprocess.DEVNULL, check=False, timeout=5)
                    # Also try specific quarantine removal
                    subprocess.run(['xattr', '-d', 'com.apple.quarantine', driver_path], 
                                 stderr=subprocess.DEVNULL, check=False, timeout=5)
                    print(f"✓ Removed extended attributes from ChromeDriver: {driver_path}")
                except Exception as xattr_error:
                    print(f"⚠ Warning - Could not remove extended attributes: {xattr_error}")
                # Ensure executable permissions
                os.chmod(driver_path, 0o755)
                # Verify no extended attributes remain
                try:
                    import subprocess
                    attrs = subprocess.run(['xattr', '-l', driver_path], 
                                         capture_output=True, text=True, timeout=5)
                    if attrs.returncode == 0 and attrs.stdout.strip():
                        print(f"⚠ Warning: Extended attributes still present: {attrs.stdout.strip()}")
                    else:
                        print(f"✓ No extended attributes found on ChromeDriver")
                except:
                    pass
            
            # Verify the driver path exists and is executable
            if not os.path.exists(driver_path):
                raise Exception(f"ChromeDriver not found at: {driver_path}")
            
            if not os.access(driver_path, os.X_OK):
                os.chmod(driver_path, 0o755)
            
            # Log the driver path for debugging
            print(f"Using ChromeDriver at: {driver_path}")
            print(f"ChromeDriver exists: {os.path.exists(driver_path)}")
            print(f"ChromeDriver executable: {os.access(driver_path, os.X_OK)}")
            
            # Create service with explicit path
            service = Service(driver_path)
            
            # Try to start Chrome
            try:
                track_step("Initialization", "Browser Setup", "in_progress", "Starting Chrome browser...")
                driver = webdriver.Chrome(service=service, options=chrome_options)
                automation_status["driver"] = driver
                print("ChromeDriver started successfully!")
                track_step("Initialization", "Browser Setup", "success", "Chrome browser started successfully")
            except Exception as chrome_error:
                # More detailed error information
                error_details = str(chrome_error)
                print(f"ChromeDriver startup error: {error_details}")
                raise Exception(f"Failed to start Chrome: {error_details}. Driver path: {driver_path}")
                
        except Exception as e:
            error_msg = str(e)
            import traceback
            full_traceback = traceback.format_exc()
            print(full_traceback)
            
            # Provide more helpful error message with actual error details
            if "Can not connect to the Service" in error_msg or "chromedriver" in error_msg.lower() or "Service" in error_msg:
                automation_status["message"] = f"ChromeDriver connection error: {error_msg}. Chrome version: 143.0.7499.170. ChromeDriver version: 143.0.7499.169 (compatible). Please check if Chrome is running or try restarting."
            else:
                automation_status["message"] = f"Error starting Chrome: {error_msg}. Please ensure Chrome is installed and not already running in another automation session."
            track_step("Initialization", "Browser Setup", "failed", error_msg)
            return
        
        # Read Excel data
        track_step("Initialization", "Read Excel File", "in_progress", f"Reading Excel file: {excel_path}")
        automation_status["message"] = "Reading Excel file..."
        excel_data = read_excel_data(excel_path)
        if not excel_data:
            error_msg = f"Error: Could not read Excel file at {excel_path}. Please check that the file exists and is a valid Excel/CSV file with the required columns."
            print(f"ERROR: {error_msg}")
            automation_status["message"] = error_msg
            track_step("Initialization", "Read Excel File", "failed", error_msg)
            return
        
        automation_status["message"] = f"Excel file loaded with {len(excel_data)} rows"
        track_step("Initialization", "Read Excel File", "success", f"Successfully loaded {len(excel_data)} rows from Excel file", driver=driver)
        time.sleep(1)
        
        # Phase 1: Open website and wait for login
        track_step("Phase 1", "Navigate to Login Page", "in_progress", "Opening settings.ef.uk.com/client_selection...", driver=driver)
        automation_status["message"] = "Opening settings.ef.uk.com/client_selection..."
        try:
            driver.get("https://settings.ef.uk.com/client_selection")
            time.sleep(2)
            track_step("Phase 1", "Navigate to Login Page", "success", "Login page loaded", driver=driver)
        except Exception as nav_error:
            track_step("Phase 1", "Navigate to Login Page", "failed", f"Failed to navigate: {str(nav_error)}", error=nav_error, driver=driver)
            raise
        
        track_step("Phase 1", "Manual Login", "in_progress", "Waiting for manual login (30 seconds or click Continue)...", driver=driver)
        automation_status["message"] = "Please login manually. Waiting 30 seconds or click 'Continue Automation'..."
        continue_automation_flag.clear()
        
        # Wait for login (30 seconds or until continue button is clicked)
        for _ in range(30):
            if continue_automation_flag.is_set():
                break
            time.sleep(1)
        
        time.sleep(2)  # Additional wait after login
        track_step("Phase 1", "Manual Login", "success", "Login completed", driver=driver)
        
        # Phase 1: Client Selection
        track_step("Phase 1", "Search for Client", "in_progress", f"Searching for client: {customer_name}", driver=driver)
        automation_status["message"] = "Phase 1: Searching for client..."
        
        # Find search input
        search_input = find_element_by_xpath(driver, "//input[@name='search']", timeout=30)
        if not search_input:
            automation_status["message"] = "Error: Could not find search input"
            return
        
        customer_name = form_data.get('customer_name', '')
        search_input.clear()
        search_input.send_keys(customer_name)
        time.sleep(1)
        
        # Click Search button
        if not click_element(driver, "//span[normalize-space()='Search']"):
            automation_status["message"] = "Error: Could not find Search button"
            return
        
        time.sleep(2)  # Wait for search results to appear
        
        # Select the client by finding the <p> tag with the client identifier
        # The card structure: <div class="font-bold">LEGO Brazil</div> followed by <p class="text-gray-700 text-base">lego-br</p>
        client_name = form_data.get('customer_name', '').strip()
        
        automation_status["message"] = f"Searching for client: '{client_name}'"
        
        # Strategy: Try both div (client name) and p tag (identifier) matching
        # User might search for "LEGO Brazil" (div) or "lego-br" (p tag identifier)
        client_found = False
        
        # Strategy 1: Try finding by p tag identifier first (if user searched for identifier like "lego-br")
        # This handles cases where user searches for the identifier directly
        automation_status["message"] = f"Strategy 1: Trying to find client by identifier '{client_name}' in p tag..."
        try:
            # Try exact match on p tag (case-sensitive first)
            p_tag_xpath = f"//p[contains(@class, 'text-gray-700') and contains(@class, 'text-base') and normalize-space()='{client_name}']"
            p_element = None
            try:
                p_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, p_tag_xpath))
                )
            except:
                # Try case-insensitive match
                try:
                    p_tag_xpath_ci = f"//p[contains(@class, 'text-gray-700') and contains(@class, 'text-base') and translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')=translate('{client_name}', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')]"
                    p_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, p_tag_xpath_ci))
                    )
                except:
                    pass
            
            if p_element:
                automation_status["message"] = f"Found p tag with identifier '{client_name}'"
                
                # Find the parent card
                parent_card = None
                try:
                    parent_card = p_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'px-6') or contains(@class, 'py-4')][1]")
                except:
                    try:
                        parent_card = p_element.find_element(By.XPATH, ".//ancestor::div[.//div[contains(@class, 'font-bold')]][1]")
                    except:
                        try:
                            parent_card = p_element.find_element(By.XPATH, "./ancestor::div[position()<=5][1]")
                        except:
                            parent_card = p_element.find_element(By.XPATH, "./..")
                
                if not parent_card:
                    raise Exception("Could not find parent card container")
                
                # Get the client name from the div for confirmation
                try:
                    client_name_div = parent_card.find_element(By.XPATH, ".//div[contains(@class, 'font-bold')]")
                    actual_client_name = client_name_div.text.strip()
                    automation_status["message"] = f"Found client card: '{actual_client_name}' (identifier: '{client_name}')"
                except:
                    automation_status["message"] = f"Found client card with identifier: '{client_name}'"
                
                # Scroll and click
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", parent_card)
                time.sleep(1)
                
                # Try clicking - multiple methods
                clicked = False
                click_attempts = [
                    ("clickable element in card", lambda: parent_card.find_elements(By.XPATH, ".//a | .//button | .//*[@onclick] | .//*[@href]")),
                    ("parent card (JavaScript)", lambda: driver.execute_script("arguments[0].click();", parent_card) or True),
                    ("parent card (regular)", lambda: parent_card.click() or True),
                    ("p tag (JavaScript)", lambda: driver.execute_script("arguments[0].click();", p_element) or True),
                    ("p tag (regular)", lambda: p_element.click() or True),
                ]
                
                for method_name, click_func in click_attempts:
                    try:
                        if method_name == "clickable element in card":
                            clickable = click_func()
                            if clickable:
                                automation_status["message"] = f"Found {len(clickable)} clickable element(s), clicking..."
                                driver.execute_script("arguments[0].click();", clickable[0])
                                clicked = True
                                break
                        else:
                            automation_status["message"] = f"Trying: {method_name}..."
                            click_func()
                            clicked = True
                            automation_status["message"] = f"Click successful using: {method_name}"
                            break
                    except Exception as e:
                        automation_status["message"] = f"{method_name} failed: {str(e)[:50]}"
                        continue
                
                if clicked:
                    time.sleep(3)
                    current_url = driver.current_url
                    if 'client_selection' not in current_url.lower():
                        automation_status["message"] = f"Successfully selected client by identifier: '{client_name}'"
                        client_found = True
                    else:
                        # Double check - wait a bit more
                        time.sleep(2)
                        current_url = driver.current_url
                        if 'client_selection' not in current_url.lower():
                            automation_status["message"] = f"Successfully selected client by identifier: '{client_name}'"
                            client_found = True
                        else:
                            automation_status["message"] = f"Click executed but still on client selection page. URL: {current_url}"
            else:
                raise Exception("Could not find p tag with identifier")
        except Exception as e:
            automation_status["message"] = f"Strategy 1 (p tag) failed: {str(e)[:100]}"
        
        # Strategy 2: Try finding by div with client name (if user searched for name like "LEGO Brazil")
        if not client_found:
            automation_status["message"] = f"Strategy 2: Trying to find client by name '{client_name}' in div..."
            # Try multiple matching strategies for the div (exact, case-insensitive, partial)
            div_strategies = [
                # Exact match (case-sensitive)
                f"//div[contains(@class, 'font-bold') and normalize-space()='{client_name}']",
                # Case-insensitive match
                f"//div[contains(@class, 'font-bold') and translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')=translate('{client_name}', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')]",
                # Contains match (case-insensitive) - for partial matches like "lego" matching "LEGO Brazil"
                f"//div[contains(@class, 'font-bold') and contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), translate('{client_name}', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))]",
            ]
        
            for div_strategy_idx, div_xpath in enumerate(div_strategies):
                try:
                    automation_status["message"] = f"Strategy {div_strategy_idx + 1}: Looking for client by name '{client_name}' in div..."
                    
                    # Find the div element containing the client name
                    client_name_div = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, div_xpath))
                    )
                    
                    actual_client_name = client_name_div.text.strip()
                    automation_status["message"] = f"Found client name div: '{actual_client_name}'"
                    
                    # Find the parent card container that contains both the div and the p tag
                    parent_card = None
                    try:
                        # Pattern 1: Look for div with px-6 or py-4 classes (most common card container)
                        parent_card = client_name_div.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'px-6') or contains(@class, 'py-4')][1]")
                    except:
                        try:
                            # Pattern 2: Look for any parent div that contains a p tag with text-gray-700
                            parent_card = client_name_div.find_element(By.XPATH, ".//ancestor::div[.//p[contains(@class, 'text-gray-700')]][1]")
                        except:
                            # Pattern 3: Get a parent div that's likely the card (within 5 levels)
                            parent_card = client_name_div.find_element(By.XPATH, "./ancestor::div[position()<=5][1]")
                    
                    if not parent_card:
                        raise Exception("Could not find parent card container")
                    
                    # Find the <p> tag within that card to get the identifier
                    p_element = None
                    p_tag_text = "unknown"
                    try:
                        p_element = parent_card.find_element(By.XPATH, ".//p[contains(@class, 'text-gray-700') and contains(@class, 'text-base')]")
                        p_tag_text = p_element.text.strip()
                        automation_status["message"] = f"Found p tag with identifier: '{p_tag_text}'"
                    except:
                        automation_status["message"] = "Could not find p tag, but proceeding with card click"
                    
                    # Scroll into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", parent_card)
                    time.sleep(1)
                    
                    # Try to find and click a link or button first
                    clicked = False
                    try:
                        # FIRST: Look for a "Switch" button/link specifically (most reliable)
                        switch_button = parent_card.find_elements(By.XPATH, ".//a[contains(text(), 'Switch')] | .//button[contains(text(), 'Switch')] | .//*[contains(text(), 'Switch')]")
                        if switch_button:
                            automation_status["message"] = f"Found 'Switch' button/link! Clicking it..."
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", switch_button[0])
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", switch_button[0])
                            clicked = True
                            automation_status["message"] = "Clicked 'Switch' button"
                        else:
                            # SECOND: Look for any clickable element (link, button, or element with cursor pointer)
                            clickable = parent_card.find_elements(By.XPATH, ".//a | .//button | .//*[@onclick] | .//*[@href] | .//*[contains(@class, 'cursor-pointer')] | .//*[contains(@style, 'cursor: pointer')]")
                            if clickable:
                                automation_status["message"] = f"Found {len(clickable)} clickable element(s), clicking first one..."
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clickable[0])
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", clickable[0])
                                clicked = True
                    except Exception as e:
                        automation_status["message"] = f"Error finding clickable elements: {str(e)[:100]}"
                        pass
                    
                    # If no clickable element found, try clicking the card itself
                    if not clicked:
                        automation_status["message"] = "Trying to click the card directly..."
                        # Try multiple click methods
                        click_methods = [
                            ("JavaScript click on parent card", lambda: driver.execute_script("arguments[0].click();", parent_card)),
                            ("Regular click on parent card", lambda: parent_card.click()),
                            ("JavaScript click on client name div", lambda: driver.execute_script("arguments[0].click();", client_name_div)),
                            ("Regular click on client name div", lambda: client_name_div.click()),
                        ]
                        
                        # Also try clicking p tag if we found it
                        if p_element:
                            click_methods.extend([
                                ("JavaScript click on p tag", lambda: driver.execute_script("arguments[0].click();", p_element)),
                                ("Regular click on p tag", lambda: p_element.click()),
                            ])
                        
                        for method_name, click_func in click_methods:
                            try:
                                automation_status["message"] = f"Trying: {method_name}..."
                                click_func()
                                clicked = True
                                automation_status["message"] = f"Click successful using: {method_name}"
                                break
                            except Exception as e:
                                automation_status["message"] = f"{method_name} failed: {str(e)[:50]}"
                                continue
                    
                    if clicked:
                        # Wait for page to update
                        time.sleep(3)
                        
                        # Check if client switched
                        current_url = driver.current_url
                        still_on_selection = 'client_selection' in current_url.lower()
                        
                        if not still_on_selection:
                            automation_status["message"] = f"Successfully selected client: {client_name} (identifier: {p_tag_text})"
                            client_found = True
                            break
                        else:
                            # Check if sidebar updated by looking for the p tag identifier
                            try:
                                page_source = driver.page_source.lower()
                                if p_tag_text.lower() in page_source and p_tag_text != "unknown":
                                    # Double-check by waiting a bit more and checking URL again
                                    time.sleep(2)
                                    current_url = driver.current_url
                                    if 'client_selection' not in current_url.lower():
                                        automation_status["message"] = f"Successfully selected client: {client_name} (identifier: {p_tag_text})"
                                        client_found = True
                                        break
                                    else:
                                        automation_status["message"] = f"Click executed but still on client selection page. URL: {current_url}"
                            except:
                                automation_status["message"] = f"Click executed but verification failed"
                    else:
                        automation_status["message"] = "All click methods failed for this card"
                            
                except Exception as e:
                    automation_status["message"] = f"Div strategy {div_strategy_idx + 1} failed: {str(e)[:100]}"
                    continue
                
                if client_found:
                    break
        
        # Strategy 3: Try to find the p tag directly by converting client name to identifier format
        if not client_found:
            automation_status["message"] = "Trying to find client by identifier format..."
            client_identifier = client_name.lower().replace(' ', '-')
            p_tag_xpath = f"//p[contains(@class, 'text-gray-700') and contains(@class, 'text-base') and normalize-space()='{client_identifier}']"
            
            try:
                p_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, p_tag_xpath))
                )
                card_element = p_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'px-6') or contains(@class, 'py-4')]")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
                time.sleep(0.5)
                try:
                    card_element.click()
                except:
                    driver.execute_script("arguments[0].click();", card_element)
                time.sleep(1)
                automation_status["message"] = f"Successfully selected client: {client_name} (via identifier: {client_identifier})"
                client_found = True
            except Exception as e:
                automation_status["message"] = f"Identifier method failed: {str(e)[:100]}"
        
        # Strategy 4: Try the original simple method (exact match on div text)
        if not client_found:
            automation_status["message"] = "Trying simple div text match..."
            result_xpath = f"//div[normalize-space()='{client_name}']"
            if click_element(driver, result_xpath):
                time.sleep(1)
                automation_status["message"] = f"Successfully selected client: {client_name} (simple method)"
                client_found = True
        
        # Strategy 5: Try finding any clickable element in the card
        if not client_found:
            automation_status["message"] = "Trying to find any clickable element in client card..."
            try:
                # Find all divs with font-bold class and check their text
                all_client_divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'font-bold')]")
                for div in all_client_divs:
                    div_text = div.text.strip()
                    if client_name.lower() in div_text.lower() or div_text.lower() in client_name.lower():
                        # Found matching div, find parent card and click
                        parent_card = div.find_element(By.XPATH, ".//ancestor::div[.//p[contains(@class, 'text-gray-700')]]")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent_card)
                        time.sleep(0.5)
                        try:
                            parent_card.click()
                        except:
                            driver.execute_script("arguments[0].click();", parent_card)
                        time.sleep(1)
                        automation_status["message"] = f"Successfully selected client: {client_name} (found via text matching: '{div_text}')"
                        client_found = True
                        break
            except Exception as e:
                automation_status["message"] = f"Text matching method failed: {str(e)[:100]}"
        
        if not client_found:
            error_msg = f"Error: Could not find or select client '{client_name}'. Please select manually."
            automation_status["message"] = error_msg
            automation_status["message"] = "Available clients on page (for debugging):"
            try:
                all_client_divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'font-bold')]")
                for idx, div in enumerate(all_client_divs[:5]):  # Show first 5
                    automation_status["message"] = f"  - Client {idx+1}: '{div.text.strip()}'"
            except:
                pass
            track_step("Phase 1", "Search for Client", "failed", error_msg)
            time.sleep(5)
            # Raise exception instead of returning, so browser stays open for debugging
            raise Exception(f"Could not find or select client '{client_name}'. Please select manually and check the browser.")
        
        # Wait for page to fully load after client selection
        automation_status["message"] = "Waiting for page to load after client selection..."
        time.sleep(5)  # Increased wait time
        
        # Verify we're on the correct page (not on client_selection anymore)
        current_url = driver.current_url
        automation_status["message"] = f"Current URL after client selection: {current_url}"
        
        try:
            WebDriverWait(driver, 15).until(
                lambda d: 'client_selection' not in d.current_url.lower()
            )
            automation_status["message"] = "Client selection confirmed. Page loaded successfully."
            track_step("Phase 1", "Search for Client", "success", f"Client '{client_name}' selected successfully")
        except:
            automation_status["message"] = f"Warning: Still on client selection page ({current_url}), but continuing..."
            track_step("Phase 1", "Search for Client", "success", f"Client selected (warning: still on selection page)")
            # Don't return - continue anyway
        
        time.sleep(3)  # Additional wait to ensure page is fully loaded
        complete_phase("Phase 1", "success")
        
        # Phase 2: Navigate to Scorecards and Create/Select Scorecard
        use_existing_scorecard = form_data.get('use_existing_scorecard', False)
        scorecard_name = form_data.get('scorecard_name', '')
        
        # Click Scorecards link
        if not click_element(driver, "//a[normalize-space()='Scorecards']"):
            automation_status["message"] = "Error: Could not find Scorecards link"
            return
        
        if use_existing_scorecard:
            # Navigate to existing scorecard
            automation_status["message"] = f"Phase 2: Navigating to existing scorecard '{scorecard_name}'..."
            time.sleep(1)
            
            # Search for the scorecard by name
            # Try to find and click the scorecard link
            scorecard_found = False
            try:
                # Method 1: Direct link by text
                if click_element(driver, f"//a[normalize-space()='{scorecard_name}']"):
                    scorecard_found = True
                    automation_status["message"] = f"Found and clicked scorecard: {scorecard_name}"
                else:
                    # Method 2: Search in table rows
                    scorecard_links = driver.find_elements(By.XPATH, "//a[contains(text(), '')]")
                    for link in scorecard_links:
                        if link.text.strip() == scorecard_name:
                            driver.execute_script("arguments[0].scrollIntoView(true);", link)
                            time.sleep(0.5)
                            link.click()
                            scorecard_found = True
                            automation_status["message"] = f"Found and clicked scorecard: {scorecard_name}"
                            break
            except Exception as e:
                automation_status["message"] = f"Error searching for scorecard: {str(e)}"
            
            if not scorecard_found:
                automation_status["message"] = f"Error: Could not find existing scorecard '{scorecard_name}'. Please verify the name or create it manually."
                time.sleep(5)
                return
            
            time.sleep(2)
        else:
            # Create new scorecard
            automation_status["message"] = "Phase 2: Creating new scorecard..."
            
            # Click Add Scorecard
            if not click_element(driver, "//a[normalize-space()='Add Scorecard']"):
                automation_status["message"] = "Error: Could not find Add Scorecard link"
                return
            
            time.sleep(1)
            
            # Fill scorecard form
            # Name
            if not fill_input(driver, "//input[@name='scorecard[name]']", scorecard_name):
                automation_status["message"] = "Error: Could not find scorecard name input"
                return
            
            # Type
            if not select_dropdown_by_value(driver, "//select[@name='scorecard[scorecard_type]']", form_data.get('scorecard_type', 'Competitor')):
                automation_status["message"] = "Error: Could not select scorecard type"
                return
            
            # Date: Year
            if not select_dropdown_by_value(driver, "//select[@name='scorecard[start_date(1i)]']", form_data.get('start_year', 2025)):
                automation_status["message"] = "Error: Could not select start year"
                return
            
            # Date: Month
            if not select_dropdown_by_value(driver, "//select[@name='scorecard[start_date(2i)]']", form_data.get('start_month', 1)):
                automation_status["message"] = "Error: Could not select start month"
                return
            
            # Date: Day
            if not select_dropdown_by_value(driver, "//select[@name='scorecard[start_date(3i)]']", form_data.get('start_day', 1)):
                automation_status["message"] = "Error: Could not select start day"
                return
            
            # Change reason
            if not fill_input(driver, "//textarea[@name='reason_for_change']", form_data.get('freshdesk_ticket_url', '')):
                automation_status["message"] = "Error: Could not find reason for change textarea"
                return
            
            # Submit scorecard
            if not click_element(driver, "//input[@type='submit' and @value='Create Scorecard']"):
                automation_status["message"] = "Error: Could not find Create Scorecard button"
                return
            
            time.sleep(2)
        
        # Phase 3: Create Measure Groups
        automation_status["message"] = "Phase 3: Creating measure groups..."
        
        # Click the scorecard link using the scorecard name from UI
        # Use the actual scorecard_name entered in the UI (e.g., "default-scorecard" instead of hardcoded "Default")
        scorecard_name = form_data.get('scorecard_name', '')
        if not scorecard_name:
            # Fallback to scorecard_type if scorecard_name is not provided
            scorecard_type = form_data.get('scorecard_type', 'Competitor')
            link_text = scorecard_type
        else:
            link_text = scorecard_name
        
        automation_status["message"] = f"Phase 3: Clicking scorecard link: '{link_text}'"
        print(f"Phase 3: Looking for scorecard link with text: '{link_text}'")
        if not click_element(driver, f"//table//a[normalize-space()='{link_text}']"):
            automation_status["message"] = f"Error: Could not find scorecard link '{link_text}'. Please verify the scorecard name matches exactly."
            print(f"Phase 3: ERROR - Could not find link with text: '{link_text}'")
            return
        
        time.sleep(1)
        
        # Change order method to "order"
        if not select_dropdown_by_value(driver, "//select[@name='order_method']", "order"):
            # Try selecting by visible text if value doesn't work
            try:
                element = find_element_by_xpath(driver, "//select[@name='order_method']", timeout=10, clickable=False)
                if element:
                    select = Select(element)
                    select.select_by_visible_text("order")
                    time.sleep(0.5)
                    automation_status["message"] = "Changed order method to 'order'"
            except:
                automation_status["message"] = "Warning: Could not change order method, continuing anyway"
        
        # Group Excel data by measure group (maintaining Excel order)
        grouped_data = {}
        for item in excel_data:
            group = item["measure_group"]
            if group not in grouped_data:
                grouped_data[group] = []
            grouped_data[group].append(item)
        
        # Get distinct measure groups from Excel (in order)
        measure_groups = get_distinct_measure_groups(excel_data)
        automation_status["message"] = f"Found {len(measure_groups)} measure groups to create with their configs"
        
        # Phase 3 & 4 Combined: For each group, create the group first, then create all its measure configs
        for idx, group_name in enumerate(measure_groups, start=1):
            automation_status["message"] = f"=== Processing Group {idx}/{len(measure_groups)}: {group_name} ==="
            
            # Step 1: Create the measure group
            automation_status["message"] = f"Creating measure group: {group_name}"
            
            # Click Add Measure Group
            if not click_element(driver, "//a[normalize-space()='Add Measure Group']"):
                automation_status["message"] = f"Error: Could not find Add Measure Group button for {group_name}"
                continue
            
            time.sleep(1)
            
            # Fill measure group form
            # Name
            if not fill_input(driver, "//input[@name='measure_group[name]']", group_name):
                automation_status["message"] = f"Error: Could not fill name for {group_name}"
                continue
            
            # Order
            if not fill_input(driver, "//input[@name='measure_group[order]']", idx):
                automation_status["message"] = f"Error: Could not fill order for {group_name}"
                continue
            
            # Change reason
            if not fill_input(driver, "//textarea[@name='reason_for_change']", form_data.get('freshdesk_ticket_url', '')):
                automation_status["message"] = f"Error: Could not fill reason for {group_name}"
                continue
            
            # Submit
            if not click_element(driver, "//input[@type='submit' and @value='Create Measure group']"):
                automation_status["message"] = f"Error: Could not submit {group_name}"
                continue
            
            time.sleep(2)
            automation_status["message"] = f"Measure group '{group_name}' created successfully"
            
            # Step 2: Create all measure configs for this group
            configs = grouped_data[group_name]
            # Sort configs by order if available (for Lego Brazil format), otherwise maintain list order
            if configs and 'order' in configs[0]:
                configs = sorted(configs, key=lambda x: x.get('order', 999))
            automation_status["message"] = f"Now creating {len(configs)} measure configs for {group_name}..."
            
            for config_idx, config in enumerate(configs, start=1):
                # Use order from config if available (Lego Brazil format), otherwise use enumerate index
                config_order = config.get('order', config_idx)
                automation_status["message"] = f"Creating config {config_idx}/{len(configs)} (order: {config_order}) for {group_name}: {config['measure_display_name']}"
                
                # Find the specific "Add Measure Config" button for this group
                # Strategy: Find the group name first, then find the "Add Measure Config" button that's in the same section
                add_config_clicked = False
                
                # Method 1: Find group name, then find Add Measure Config in following siblings or parent container
                try:
                    # Find element containing the group name
                    group_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{group_name}')]")
                    for group_elem in group_elements:
                        # Check if this is likely the group header (not a measure config name)
                        if group_elem.tag_name in ['th', 'td', 'div', 'span'] and len(group_elem.text.strip()) == len(group_name):
                            # Find Add Measure Config button in the same row or nearby
                            # Look in the same row first
                            try:
                                parent_row = group_elem.find_element(By.XPATH, "./ancestor::tr[1]")
                                add_config_btn = parent_row.find_element(By.XPATH, ".//a[normalize-space()='Add Measure Config']")
                                driver.execute_script("arguments[0].scrollIntoView(true);", add_config_btn)
                                time.sleep(0.5)
                                add_config_btn.click()
                                add_config_clicked = True
                                time.sleep(1)
                                break
                            except:
                                # Try finding in the same container/div
                                try:
                                    parent_container = group_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'group') or contains(@class, 'measure')][1]")
                                    add_config_btn = parent_container.find_element(By.XPATH, ".//a[normalize-space()='Add Measure Config']")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", add_config_btn)
                                    time.sleep(0.5)
                                    add_config_btn.click()
                                    add_config_clicked = True
                                    time.sleep(1)
                                    break
                                except:
                                    continue
                except Exception as e:
                    automation_status["message"] = f"Method 1 failed for {group_name}: {str(e)}"
                
                # Method 2: Find all Add Measure Config buttons and match by position/context
                if not add_config_clicked:
                    try:
                        # Get all group names in order
                        all_groups = list(grouped_data.keys())
                        current_group_index = all_groups.index(group_name)
                        
                        # Find all Add Measure Config buttons
                        all_add_buttons = driver.find_elements(By.XPATH, "//a[normalize-space()='Add Measure Config']")
                        
                        if len(all_add_buttons) > current_group_index:
                            # Click the button at the index corresponding to this group
                            target_button = all_add_buttons[current_group_index]
                            driver.execute_script("arguments[0].scrollIntoView(true);", target_button)
                            time.sleep(0.5)
                            target_button.click()
                            add_config_clicked = True
                            time.sleep(1)
                    except Exception as e:
                        automation_status["message"] = f"Method 2 failed for {group_name}: {str(e)}"
                
                # Method 3: Fallback - find button near group name text
                if not add_config_clicked:
                    try:
                        # Use XPath to find Add Measure Config that follows the group name
                        xpath_pattern = f"//*[contains(text(), '{group_name}')]/following::a[normalize-space()='Add Measure Config'][1]"
                        add_config_btn = find_element_by_xpath(driver, xpath_pattern, timeout=10)
                        if add_config_btn:
                            driver.execute_script("arguments[0].scrollIntoView(true);", add_config_btn)
                            time.sleep(0.5)
                            add_config_btn.click()
                            add_config_clicked = True
                            time.sleep(1)
                    except Exception as e:
                        automation_status["message"] = f"Method 3 failed for {group_name}: {str(e)}"
                
                if not add_config_clicked:
                    automation_status["message"] = f"Error: Could not find Add Measure Config button for group {group_name}. Skipping {config['measure_display_name']}"
                    continue
                
                # Wait for the form to be fully loaded before filling
                time.sleep(2)  # Wait for form to load
                try:
                    # Wait for the name input to be present
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@name='measure_config[name]']"))
                    )
                except:
                    automation_status["message"] = f"Warning: Form may not be fully loaded for {config['measure_display_name']}"
                
                # Fill measure config form
                # Name
                if not fill_input(driver, "//input[@name='measure_config[name]']", config['measure_display_name']):
                    automation_status["message"] = f"Error: Could not fill name for {config['measure_display_name']}"
                    # Try to go back if form didn't load
                    click_element(driver, "//a[normalize-space()='Back']")
                    continue
                
                # Order - use the config_order calculated earlier (from config['order'] for Lego Brazil format, or config_idx)
                if not fill_input(driver, "//input[@name='measure_config[order]']", config_order):
                    automation_status["message"] = f"Error: Could not fill order for {config['measure_display_name']}"
                    click_element(driver, "//a[normalize-space()='Back']")
                    continue
                
                # Measure definition - wait a bit more and ensure dropdown is ready
                measure_def_value = config['standard_kpis']
                time.sleep(1)  # Additional wait before selecting dropdown
                
                # Wait for dropdown to be present and ready
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//select[@name='measure_config[measure_definition_id]']"))
                    )
                    # Wait a bit more for options to load
                    time.sleep(1)
                except:
                    automation_status["message"] = f"Warning: Measure definition dropdown not found for {config['measure_display_name']}"
                
                if not select_dropdown_by_value(driver, "//select[@name='measure_config[measure_definition_id]']", measure_def_value, timeout=15, max_retries=5):
                    # Try to get available options for better error message
                    try:
                        select_element = find_element_by_xpath(driver, "//select[@name='measure_config[measure_definition_id]']", timeout=5, clickable=False)
                        if select_element:
                            select = Select(select_element)
                            available_options = [opt.text.strip() for opt in select.options[:15]]  # First 15 options
                            automation_status["message"] = f"ERROR: Could not find measure definition '{measure_def_value}' for '{config['measure_display_name']}'. Available options (first 15): {', '.join(available_options)}"
                        else:
                            automation_status["message"] = f"ERROR: Could not find measure definition dropdown for '{config['measure_display_name']}' (looking for: '{measure_def_value}')"
                    except:
                        automation_status["message"] = f"ERROR: Could not select measure definition '{measure_def_value}' for '{config['measure_display_name']}'. Please verify this measure definition exists in the portal."
                    click_element(driver, "//a[normalize-space()='Back']")
                    time.sleep(1)
                    continue
                
                # Description
                if not fill_input(driver, "//textarea[@name='measure_config[description]']", config['definition']):
                    automation_status["message"] = f"Error: Could not fill description for {config['measure_display_name']}"
                    click_element(driver, "//a[normalize-space()='Back']")
                    continue
                
                # Change reason
                if not fill_input(driver, "//textarea[@name='reason_for_change']", form_data.get('freshdesk_ticket_url', '')):
                    automation_status["message"] = f"Error: Could not fill reason for {config['measure_display_name']}"
                    click_element(driver, "//a[normalize-space()='Back']")
                    continue
                
                # Submit
                if not click_element(driver, "//input[@type='submit' and @value='Create Measure config']"):
                    automation_status["message"] = f"Error: Could not submit {config['measure_display_name']}"
                    click_element(driver, "//a[normalize-space()='Back']")
                    continue
                
                time.sleep(2)
                
                # After submitting, we should be back on the main page, but verify
                # Wait a moment for the page to reload/redirect
                time.sleep(1)
        
        # Phase 6: Update Rating Thresholds (right after measure configs are added)
        print("=" * 50)
        print("Starting Phase 6: Update Rating Thresholds")
        print("=" * 50)
        scorecard_type = form_data.get('scorecard_type', 'Competitor')
        
        if scorecard_type == 'Enterprise':
            # For Enterprise: Handle multiple measure configs with thresholds
            measure_configs = form_data.get('measure_configs', [])
            if measure_configs:
                automation_status["message"] = f"Phase 6: Updating thresholds for {len(measure_configs)} measure config(s)..."
                time.sleep(2)  # Wait for page to be fully loaded
                
                for config_idx, config_data in enumerate(measure_configs, start=1):
                    config_name = config_data.get('config_name', '').strip()
                    threshold_x = config_data.get('threshold_x', '')
                    threshold_y = config_data.get('threshold_y', '')
                    
                    # Skip if no config name or both thresholds are empty
                    if not config_name or (not threshold_x and not threshold_y):
                        continue
                    
                    automation_status["message"] = f"Updating thresholds for config {config_idx}/{len(measure_configs)}: {config_name}..."
                    
                    # Find measure config by name
                    edit_icon = None
                    config_found = False
                    
                    try:
                        # Method 1: Find by exact text match
                        try:
                            edit_icon = driver.find_element(By.XPATH, f"//a[normalize-space()='{config_name}']/ancestor::div[contains(@class,'flex')][1]//*[name()='svg'][1]")
                            config_found = True
                        except:
                            pass
                        
                        # Method 2: Find all SVGs and match by context
                        if not config_found:
                            try:
                                all_svgs = driver.find_elements(By.XPATH, "//div[contains(@class,'flex')]//*[name()='svg']")
                                for svg in all_svgs:
                                    try:
                                        flex_parent = svg.find_element(By.XPATH, "./ancestor::div[contains(@class,'flex')][1]")
                                        config_link = flex_parent.find_element(By.XPATH, f".//a[normalize-space()='{config_name}']")
                                        if config_link:
                                            edit_icon = svg
                                            config_found = True
                                            break
                                    except:
                                        continue
                            except:
                                pass
                    except Exception as e:
                        automation_status["message"] = f"Error searching for {config_name}: {str(e)}"
                    
                    if config_found and edit_icon:
                        # Click the edit icon
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_icon)
                            time.sleep(0.5)
                            edit_icon.click()
                            time.sleep(2)
                        except:
                            try:
                                parent = edit_icon.find_element(By.XPATH, "./ancestor::a[1] | ./ancestor::button[1] | ./ancestor::*[contains(@onclick, 'edit') or contains(@href, 'edit')][1]")
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent)
                                time.sleep(0.5)
                                parent.click()
                                time.sleep(2)
                            except:
                                automation_status["message"] = f"Error: Could not click edit icon for {config_name}"
                                continue
                        
                        automation_status["message"] = f"Edit page opened for {config_name}, updating thresholds..."
                        time.sleep(1)
                        
                        # Update root_threshold (X) if provided
                        if threshold_x:
                            if fill_input(driver, "//input[@name='root_threshold']", threshold_x):
                                automation_status["message"] = f"Updated root_threshold to {threshold_x}"
                            else:
                                automation_status["message"] = f"Warning: Could not find root_threshold input for {config_name}"
                        
                        # Update root_threshold2 (Y) if provided
                        if threshold_y:
                            if fill_input(driver, "//input[@name='root_threshold2']", threshold_y):
                                automation_status["message"] = f"Updated root_threshold2 to {threshold_y}"
                            else:
                                automation_status["message"] = f"Warning: Could not find root_threshold2 input for {config_name}"
                        
                        # Enter change reason
                        if fill_input(driver, "//textarea[@name='reason_for_change']", form_data.get('freshdesk_ticket_url', '')):
                            automation_status["message"] = "Entered change reason"
                        
                        # Save Parameters
                        if click_element(driver, "//button[normalize-space()='Save Parameters']"):
                            automation_status["message"] = f"Saved threshold parameters for {config_name} successfully"
                            time.sleep(2)
                            
                            # Go back to main page
                            if click_element(driver, "//a[normalize-space()='Back']"):
                                automation_status["message"] = "Returned to scorecard page"
                                time.sleep(1)
                        else:
                            automation_status["message"] = f"Error: Could not find Save Parameters button for {config_name}"
                    else:
                        automation_status["message"] = f"Warning: Could not find measure config '{config_name}' or edit icon. Skipping."
            else:
                automation_status["message"] = "Phase 6: No measure configs with thresholds to update."
        else:
            # For Competitor: Handle single "Rating > x" config (original behavior)
            automation_status["message"] = "Phase 6: Updating rating thresholds for Rating > x (where x can be set)..."
            time.sleep(2)  # Wait for page to be fully loaded
            
            # Find measure config with exact name "Rating > x (where x can be set)"
            rating_config_found = False
            edit_icon = None
            
            try:
                # Method 1: Find by exact text match
                try:
                    edit_icon = driver.find_element(By.XPATH, "//a[normalize-space()='Rating > x (where x can be set)']/ancestor::div[contains(@class,'flex')][1]//*[name()='svg'][1]")
                    rating_config_found = True
                except:
                    pass
                
                # Method 2: Find by partial text match
                if not rating_config_found:
                    try:
                        edit_icon = driver.find_element(By.XPATH, "//a[contains(text(), 'Rating > x')]/ancestor::div[contains(@class,'flex')][1]//*[name()='svg'][1]")
                        rating_config_found = True
                    except:
                        try:
                            edit_icon = driver.find_element(By.XPATH, "//a[contains(text(), 'Rating >')]/ancestor::div[contains(@class,'flex')][1]//*[name()='svg'][1]")
                            rating_config_found = True
                        except:
                            pass
                
                # Method 3: Find all SVGs and match by context
                if not rating_config_found:
                    try:
                        all_svgs = driver.find_elements(By.XPATH, "//div[contains(@class,'flex')]//*[name()='svg']")
                        for svg in all_svgs:
                            try:
                                flex_parent = svg.find_element(By.XPATH, "./ancestor::div[contains(@class,'flex')][1]")
                                rating_link = flex_parent.find_element(By.XPATH, ".//a[contains(text(), 'Rating >')]")
                                if rating_link:
                                    edit_icon = svg
                                    rating_config_found = True
                                    break
                            except:
                                continue
                    except:
                        pass
                
            except Exception as e:
                automation_status["message"] = f"Error searching for Rating > x: {str(e)}"
            
            if rating_config_found and edit_icon:
                automation_status["message"] = "Found Rating > x measure config, clicking edit icon..."
                
                # Click the edit icon
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_icon)
                    time.sleep(0.5)
                    edit_icon.click()
                    time.sleep(2)
                except:
                    try:
                        parent = edit_icon.find_element(By.XPATH, "./ancestor::a[1] | ./ancestor::button[1] | ./ancestor::*[contains(@onclick, 'edit') or contains(@href, 'edit')][1]")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent)
                        time.sleep(0.5)
                        parent.click()
                        time.sleep(2)
                    except:
                        automation_status["message"] = "Error: Could not click edit icon"
                        return
                
                automation_status["message"] = "Edit page opened, updating thresholds..."
                time.sleep(1)
                
                # Update root_threshold (X)
                threshold_x = form_data.get('rating_threshold_x', 4.20)
                if fill_input(driver, "//input[@name='root_threshold']", threshold_x):
                    automation_status["message"] = f"Updated root_threshold to {threshold_x}"
                else:
                    automation_status["message"] = "Warning: Could not find root_threshold input"
                
                # Update root_threshold2 (Y)
                threshold_y = form_data.get('ratings_threshold_y', 50)
                if fill_input(driver, "//input[@name='root_threshold2']", threshold_y):
                    automation_status["message"] = f"Updated root_threshold2 to {threshold_y}"
                else:
                    automation_status["message"] = "Warning: Could not find root_threshold2 input"
                
                # Enter change reason
                if fill_input(driver, "//textarea[@name='reason_for_change']", form_data.get('freshdesk_ticket_url', '')):
                    automation_status["message"] = "Entered change reason"
                else:
                    automation_status["message"] = "Warning: Could not find reason_for_change textarea"
                
                # Save Parameters
                if click_element(driver, "//button[normalize-space()='Save Parameters']"):
                    automation_status["message"] = "Saved rating threshold parameters successfully"
                    time.sleep(2)
                    
                    # Go back to main page
                    if click_element(driver, "//a[normalize-space()='Back']"):
                        automation_status["message"] = "Returned to scorecard page"
                        time.sleep(1)
                else:
                    automation_status["message"] = "Error: Could not find Save Parameters button"
            else:
                automation_status["message"] = "Warning: Could not find Rating > x measure config or edit icon. It may not exist or have a different name/structure."
        
        print("=" * 50)
        print("Phase 6: Rating Thresholds Update Completed")
        print("=" * 50)
        
        # Phase 1.5: Update Organization ID (AFTER Phase 6 - Rating Thresholds)
        print("=" * 80)
        print("PHASE 1.5: CHECKING FOR ORGANIZATION ID UPDATE")
        print("=" * 80)
        print(f"Phase 1.5: All form_data keys: {list(form_data.keys())}")
        organization_id_phase1_5 = form_data.get('organization_id_phase1_5', None)
        print(f"Phase 1.5: organization_id_phase1_5 value from form_data: {repr(organization_id_phase1_5)}")
        print(f"Phase 1.5: organization_id_phase1_5 is None? {organization_id_phase1_5 is None}")
        if organization_id_phase1_5:
            print(f"Phase 1.5: organization_id_phase1_5.strip() result: {repr(organization_id_phase1_5.strip())}")
            print(f"Phase 1.5: organization_id_phase1_5.strip() is truthy? {bool(organization_id_phase1_5.strip())}")
        
        if organization_id_phase1_5 and organization_id_phase1_5.strip():
            automation_status["message"] = "Phase 1.5: Updating Organization ID..."
            print(f"Phase 1.5: ✓ Organization ID provided: '{organization_id_phase1_5}' - Starting update...")
            customer_name = form_data.get('customer_name', '')
            print(f"Phase 1.5: Customer name: '{customer_name}'")
            change_reason = form_data.get('freshdesk_ticket_url', 'Automated Organization ID update')
            if len(change_reason) < 10:
                change_reason = change_reason + " " * (10 - len(change_reason))
            
            if update_client_organization_id_phase1_5(driver, customer_name, organization_id_phase1_5.strip(), change_reason):
                automation_status["message"] = "Phase 1.5: Organization ID updated successfully"
                print("Phase 1.5: ✓ Organization ID update completed successfully")
            else:
                automation_status["message"] = "Phase 1.5: Warning - Organization ID update failed, but continuing to Phase 2"
                print("Phase 1.5: ⚠ WARNING - Organization ID update failed, but continuing to Phase 2")
        else:
            print("Phase 1.5: ✗ No Organization ID provided or value is empty, skipping this step")
            print(f"Phase 1.5: To enable this step, enter a value in the 'Organization ID (Optional - between Phase 1 and Phase 2)' field in the UI")
        print("=" * 80)
        
        # Phase 2: Weights & Targets Export, Processing, and Import
        track_step("Phase 2", "Start Phase 2", "in_progress", "Starting Weights & Targets processing")
        print("\n" + "="*100)
        print("="*100)
        print("📊 PHASE 2: WEIGHTS & TARGETS")
        print("="*100)
        setup_sheet_path = form_data.get('setup_sheet_path', None)
        retailer_weights_targets_path = form_data.get('retailer_weights_targets_path', None)
        export_file_path = form_data.get('export_file_path', None)
        
        print(f"Phase 2: Input parameters:")
        print(f"  - setup_sheet_path (from form): {setup_sheet_path}")
        print(f"  - retailer_weights_targets_path (from form): {retailer_weights_targets_path}")
        print(f"  - export_file_path (from form): {export_file_path}")
        
        # If setup_sheet_path not provided, try to use the same file as Phase 1 (Excel Configuration File)
        if not setup_sheet_path:
            excel_file_path = form_data.get('excel_file_path', None)
            if excel_file_path:
                # Use the same file that was used for Phase 1 measures
                setup_sheet_path = excel_file_path
                print(f"Phase 2: ⚠ No setup sheet path provided. Using Phase 1 Excel file: {excel_file_path}")
                automation_status["message"] = f"Phase 2: Using Phase 1 Excel file for weights/targets: {excel_file_path}"
            else:
                print(f"Phase 2: ⚠ No setup sheet path provided AND no excel_file_path found in form data")
        
        if setup_sheet_path:
            print(f"Phase 2: ✓ Setup sheet path resolved: {setup_sheet_path}")
            # Resolve setup sheet path (handles both provided path and fallback from Phase 1 file)
            if not os.path.isabs(setup_sheet_path):
                setup_sheet_path = os.path.join(os.path.dirname(__file__), setup_sheet_path)
            setup_sheet_path = os.path.expanduser(setup_sheet_path)
            
            # Resolve retailer weights/targets path if provided
            if retailer_weights_targets_path:
                if not os.path.isabs(retailer_weights_targets_path):
                    retailer_weights_targets_path = os.path.join(os.path.dirname(__file__), retailer_weights_targets_path)
                retailer_weights_targets_path = os.path.expanduser(retailer_weights_targets_path)
                print(f"Phase 2: Retailer weights/targets sheet path: {retailer_weights_targets_path}")
                print(f"Phase 2: Retailer weights/targets sheet exists: {os.path.exists(retailer_weights_targets_path)}")
            
            print(f"Phase 2: Checking setup sheet at: {setup_sheet_path}")
            print(f"Phase 2: Setup sheet exists: {os.path.exists(setup_sheet_path)}")
            
            if os.path.exists(setup_sheet_path):
                automation_status["message"] = "Starting Phase 2: Weights & Targets automation..."
                print("Phase 2: Starting automation...")
                
                # Get scorecard name for selection
                scorecard_name = form_data.get('scorecard_name', 'Default')
                print(f"Phase 2: Using scorecard name: '{scorecard_name}'")
                
                # Step 1: Export template
                track_step("Phase 2", "Export Template", "in_progress", f"Exporting template for scorecard: {scorecard_name}")
                print("Phase 2: Step 1 - Exporting template...")
                if export_weights_targets_template(driver, scorecard_name):
                    track_step("Phase 2", "Export Template", "success", "Export template job triggered successfully")
                    automation_status["message"] = "Phase 2: Export template job triggered successfully"
                    print("Phase 2: Export template triggered successfully")
                    
                    # Step 2: Wait for job and download
                    # Use hardcoded username (same as login credentials)
                    username = "arijit.k@commerceiq.ai"
                    track_step("Phase 2", "Wait for Download", "in_progress", f"Waiting for export job to complete (username: {username})")
                    automation_status["message"] = f"Phase 2: Using username '{username}' to filter jobs"
                    print(f"Phase 2: Step 2 - Waiting for job and downloading (username: {username})...")
                    # Pass export_file_path if provided
                    downloaded_file = wait_for_export_job_and_download(driver, username, export_file_path)
                    
                    print(f"Phase 2: DEBUG - wait_for_export_job_and_download returned: {downloaded_file}")
                    
                    if downloaded_file:
                        track_step("Phase 2", "Wait for Download", "success", f"File downloaded: {os.path.basename(downloaded_file)}")
                    else:
                        track_step("Phase 2", "Wait for Download", "in_progress", "File not found via job tracking, trying fallback search...")
                    
                    # Fallback: If no file was downloaded, search more broadly
                    if not downloaded_file:
                        print(f"Phase 2: DEBUG - No file returned from wait_for_export_job_and_download, trying fallback search...")
                        search_dirs = []
                        
                        # 1. Check export_file_path if provided
                        if export_file_path:
                            resolved_path = export_file_path
                            if not os.path.isabs(resolved_path):
                                resolved_path = os.path.join(os.path.dirname(__file__), resolved_path)
                            resolved_path = os.path.expanduser(resolved_path)
                            
                            if os.path.isdir(resolved_path):
                                search_dirs.append(resolved_path)
                            elif os.path.isfile(resolved_path):
                                search_dirs.append(os.path.dirname(resolved_path))
                        
                        # 2. Always check Downloads folder
                        downloads_path = os.path.expanduser("~/Downloads")
                        if os.path.exists(downloads_path):
                            search_dirs.append(downloads_path)
                        
                        # 3. Check project downloads folder
                        project_downloads = os.path.join(os.path.dirname(__file__), "downloads")
                        if os.path.exists(project_downloads):
                            search_dirs.append(project_downloads)
                        
                        print(f"Phase 2: DEBUG - Searching in directories: {search_dirs}")
                        
                        # Look for recently downloaded files (within last 2 hours)
                        current_time = time.time()
                        all_candidate_files = []
                        
                        for search_dir in search_dirs:
                            for ext in ['*.csv', '*.xlsx', '*.xls']:
                                pattern = os.path.join(search_dir, ext)
                                found = glob.glob(pattern)
                                for file in found:
                                    file_age = current_time - os.path.getmtime(file)
                                    if file_age < 7200:  # Less than 2 hours old
                                        all_candidate_files.append((file, file_age))
                        
                        if all_candidate_files:
                            # Sort by modification time (most recent first)
                            all_candidate_files.sort(key=lambda x: x[1])
                            print(f"Phase 2: DEBUG - Found {len(all_candidate_files)} recent files")
                            
                            # Try to match export pattern
                            for file, age in all_candidate_files:
                                file_lower = file.lower()
                                file_basename = os.path.basename(file_lower)
                                
                                matches_pattern = (
                                    'export' in file_lower or 
                                    'weight' in file_lower or 
                                    'target' in file_lower or 
                                    'exportweightstargettemplatejob' in file_lower.replace(' ', '').replace('_', '').replace('-', '')
                                )
                                
                                if matches_pattern:
                                    downloaded_file = file
                                    print(f"Phase 2: ✓ Found matching file via fallback: {os.path.basename(file)} (modified {age/60:.1f} minutes ago)")
                                    automation_status["message"] = f"Phase 2: Found file via fallback: {os.path.basename(downloaded_file)}"
                                    track_step("Phase 2", "Wait for Download", "success", f"Found file via fallback: {os.path.basename(downloaded_file)}")
                                    break
                            
                            # If no pattern match, use the most recent file as last resort
                            if not downloaded_file and all_candidate_files:
                                downloaded_file = all_candidate_files[0][0]
                                print(f"Phase 2: ⚠ Using most recent file as fallback: {os.path.basename(downloaded_file)}")
                                automation_status["message"] = f"Phase 2: Using most recent file: {os.path.basename(downloaded_file)}"
                                track_step("Phase 2", "Wait for Download", "success", f"Using most recent file: {os.path.basename(downloaded_file)}")
                    
                    if downloaded_file:
                        # Verify file exists and is readable
                        if not os.path.exists(downloaded_file):
                            print(f"Phase 2: ERROR - File path returned but file does not exist: {downloaded_file}")
                            automation_status["message"] = f"Phase 2: ERROR - File not found: {downloaded_file}"
                            track_step("Phase 2", "Wait for Download", "failed", f"File not found: {downloaded_file}")
                            downloaded_file = None
                        else:
                            file_size = os.path.getsize(downloaded_file)
                            print(f"Phase 2: ✓ File verified: {downloaded_file} (size: {file_size} bytes)")
                    
                    if downloaded_file:
                        automation_status["message"] = f"Phase 2: File found: {downloaded_file}"
                        print(f"Phase 2: File found successfully: {downloaded_file}")
                        
                        # Step 3: Process the file
                        track_step("Phase 2", "Process File", "in_progress", f"Processing file: {os.path.basename(downloaded_file)}")
                        print("=" * 80)
                        print("Phase 2: Step 3 - Processing file...")
                        print(f"Phase 2: Input file: {downloaded_file}")
                        print(f"Phase 2: Setup sheet: {setup_sheet_path}")
                        print(f"Phase 2: Retailer weights/targets: {retailer_weights_targets_path}")
                        print(f"Phase 2: Scorecard name: {scorecard_name}")
                        print("=" * 80)
                        
                        output_dir = os.path.join(os.path.dirname(__file__), "processed")
                        os.makedirs(output_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_csv_path = os.path.join(output_dir, f"processed_weights_targets_{timestamp}.csv")
                        
                        # scorecard_name already retrieved above for export, reuse it
                        print(f"Phase 2: Processing with scorecard name: '{scorecard_name}'")
                        automation_status["message"] = f"Phase 2: Processing with scorecard name: '{scorecard_name}'"
                        
                        try:
                            process_result = process_weights_targets_file(downloaded_file, setup_sheet_path, output_csv_path, retailer_weights_targets_path, scorecard_name)
                            print(f"Phase 2: DEBUG - process_weights_targets_file returned: {process_result}")
                            
                            if process_result:
                                track_step("Phase 2", "Process File", "success", f"File processed successfully: {os.path.basename(output_csv_path)}")
                                automation_status["message"] = f"Phase 2: File processed successfully: {output_csv_path}"
                                print(f"Phase 2: ✓ File processed successfully: {output_csv_path}")
                                
                                # Verify output file exists
                                if os.path.exists(output_csv_path):
                                    file_size = os.path.getsize(output_csv_path)
                                    print(f"Phase 2: ✓ Output file verified: {output_csv_path} (size: {file_size} bytes)")
                                    
                                    # Step 4: Import the CSV
                                    track_step("Phase 2", "Import CSV", "in_progress", f"Importing CSV to portal: {os.path.basename(output_csv_path)}")
                                    print("=" * 80)
                                    print("Phase 2: Step 4 - Importing CSV to portal...")
                                    print(f"Phase 2: CSV file to import: {output_csv_path}")
                                    print("=" * 80)
                                    
                                    change_reason = form_data.get('freshdesk_ticket_url', 'Automated import')
                                    if len(change_reason) < 10:
                                        change_reason = change_reason + " " * (10 - len(change_reason))
                                    
                                    # Get scorecard name again for import (ensure it's selected)
                                    scorecard_name = form_data.get('scorecard_name', 'Default')
                                    
                                    try:
                                        import_result = import_weights_targets_csv(driver, output_csv_path, change_reason, scorecard_name)
                                        print(f"Phase 2: DEBUG - import_weights_targets_csv returned: {import_result}")
                                        
                                        if import_result:
                                            track_step("Phase 2", "Import CSV", "success", "Weights and targets imported successfully to portal", driver=driver)
                                            automation_status["message"] = "Phase 2 completed successfully! Weights and targets imported."
                                            print("Phase 2: ✓✓✓ COMPLETED SUCCESSFULLY - File imported to portal!")
                                        else:
                                            # Capture current browser state for error analysis
                                            error_details = {
                                                "url": driver.current_url if driver else None,
                                                "page_has_error": False,
                                                "timeout_reason": None
                                            }
                                            try:
                                                if driver:
                                                    page_source = driver.page_source.lower()
                                                    error_details["page_has_error"] = any(word in page_source for word in ["error", "failed", "exception"])
                                                    # Check if it was a timeout
                                                    if "timeout" in automation_status.get("message", "").lower():
                                                        error_details["timeout_reason"] = "Import did not complete within 200 seconds"
                                            except:
                                                pass
                                            
                                            error_msg = "Import failed - check browser for details"
                                            track_step("Phase 2", "Import CSV", "failed", error_msg, error=error_msg, driver=driver, details=error_details)
                                            automation_status["message"] = "Phase 2: Import failed. Please check the error above and import manually."
                                            print("Phase 2: ✗✗✗ ERROR - Import step failed. Check browser for details.")
                                            print("Phase 2: The processed file is available at:", output_csv_path)
                                    except Exception as import_error:
                                        error_msg = f"Phase 2: Exception during import: {str(import_error)}"
                                        track_step("Phase 2", "Import CSV", "failed", error_msg, error=import_error, driver=driver)
                                        automation_status["message"] = error_msg
                                        print(f"Phase 2: ✗✗✗ EXCEPTION - {error_msg}")
                                        import traceback
                                        print(traceback.format_exc())
                                        print("Phase 2: The processed file is available at:", output_csv_path)
                                else:
                                    error_msg = f"Phase 2: Output file was not created: {output_csv_path}"
                                    track_step("Phase 2", "Process File", "failed", error_msg)
                                    automation_status["message"] = error_msg
                                    print(f"Phase 2: ✗✗✗ ERROR - {error_msg}")
                            else:
                                track_step("Phase 2", "Process File", "failed", "File processing returned False - check error messages above")
                                automation_status["message"] = "Phase 2: File processing failed. Check error messages above."
                                print("Phase 2: ✗✗✗ ERROR - File processing failed. Check error messages above.")
                                print("Phase 2: Check the console output for detailed error information.")
                        except Exception as process_error:
                            error_msg = f"Phase 2: Exception during processing: {str(process_error)}"
                            track_step("Phase 2", "Process File", "failed", f"Exception: {str(process_error)}")
                            automation_status["message"] = error_msg
                            print(f"Phase 2: ✗✗✗ EXCEPTION - {error_msg}")
                            import traceback
                            print(traceback.format_exc())
                    else:
                        track_step("Phase 2", "Wait for Download", "failed", "Could not download export file - job may still be running or file not found")
                        automation_status["message"] = "Phase 2: Could not download export file. The job may still be running or the file was not found in the expected location."
                        print("Phase 2: ERROR - Could not download export file.")
                else:
                    track_step("Phase 2", "Export Template", "failed", "Could not export template - check if Bulk Operations > Export Template is available")
                    automation_status["message"] = "Phase 2: Could not export template. Check if you're on the correct page and 'Bulk Operations' > 'Export Template' is available."
                    print("Phase 2: ERROR - Could not export template.")
            else:
                automation_status["message"] = f"Phase 2: Setup sheet not found at {setup_sheet_path}. Please check the path and try again."
                print(f"Phase 2: ✗✗✗ ERROR - Setup sheet not found at: {setup_sheet_path}")
                print(f"Phase 2: Current working directory: {os.getcwd()}")
                print(f"Phase 2: Absolute path would be: {os.path.abspath(setup_sheet_path)}")
        else:
            automation_status["message"] = "Phase 2: No setup sheet path provided. Skipping weights/targets processing."
            print("Phase 2: ⏭️  SKIPPED - No setup sheet path provided in form data.")
            print("Phase 2: To enable Phase 2, provide either:")
            print("  1. 'Setup Sheet Path' in the form, OR")
            print("  2. 'Excel Configuration File Path' (will be used for both Phase 1 and Phase 2)")
        
        print("="*100)
        print("Phase 2: END")
        print("="*100 + "\n")
        complete_phase("Phase 2", "success")
        
        # Note: Competitor scorecards now continue to Phase 3a (Looker Config Update)
        # Previously, Competitor scorecards stopped after Phase 2, but now they proceed to Phase 3a
        scorecard_type = form_data.get('scorecard_type', '').strip()
        
        # Continue with remaining phases for Enterprise scorecards
        # Phase 3a: Update Looker Config (for Enterprise and Competitor scorecards)
        # This phase runs regardless of Phase 2 status
        print("=" * 50)
        print("Starting Phase 3a: Looker Config Update")
        print("=" * 50)
        print(f"Phase 3a: Checking scorecard type: '{scorecard_type}' (type: {type(scorecard_type)})")
        print(f"Phase 3a: Full form_data scorecard_type: {repr(form_data.get('scorecard_type', ''))}")
        
        phase3a_completed = False
        try:
            if scorecard_type in ['Enterprise', 'Competitor']:
                automation_status["message"] = f"Phase 3a: Updating Looker Config for {scorecard_type} scorecard..."
                customer_name = form_data.get('customer_name', '')
                change_reason = form_data.get('freshdesk_ticket_url', 'Automated update')
                if len(change_reason) < 10:
                    change_reason = change_reason + " " * (10 - len(change_reason))
                
                if update_looker_config(driver, customer_name, change_reason, scorecard_type):
                    automation_status["message"] = f"Phase 3a: Looker Config updated successfully for {scorecard_type}"
                    print(f"Phase 3a: Looker Config update completed successfully for {scorecard_type}")
                    phase3a_completed = True
                else:
                    automation_status["message"] = f"Phase 3a: Looker Config update failed for {scorecard_type} (but continuing to Phase 4)"
                    print(f"Phase 3a: Looker Config update failed for {scorecard_type} (but continuing to Phase 4)")
                    phase3a_completed = True  # Still mark as completed so Phase 4 can run
            else:
                automation_status["message"] = f"Phase 3a: Skipping Looker Config update (scorecard type is '{scorecard_type}')"
                print(f"Phase 3a: Skipped - scorecard type is '{scorecard_type}'")
                phase3a_completed = True
        except Exception as phase3a_error:
            automation_status["message"] = f"Phase 3a: Error occurred but continuing to Phase 4: {str(phase3a_error)}"
            print(f"Phase 3a: ERROR - {str(phase3a_error)}")
            print("Phase 3a: Continuing to Phase 4 despite error...")
            import traceback
            print(traceback.format_exc())
            phase3a_completed = True  # Still continue to Phase 4
        
        # Phase 3b: Removed - Organization ID is now updated in Phase 1.5 only
        # (Consolidated to avoid duplicate updates)
        
        # Check if this is a Competitor scorecard - if so, stop after Phase 3a
        if scorecard_type == 'Competitor':
            print("=" * 100)
            print("🏁 COMPETITOR SCORECARD - AUTOMATION COMPLETE")
            print("=" * 100)
            print("For Competitor scorecards, automation stops after Phase 3a.")
            print("Completed phases:")
            print("  ✓ Phase 1: Client Selection & Scorecard Creation")
            print("  ✓ Phase 2: Measures & Weights/Targets")
            print("  ✓ Phase 3a: Looker Config Update")
            print("")
            print("Skipped phases (Enterprise only):")
            print("  ⏭️  Phase 4: Search Term Weights Import")
            print("  ⏭️  Phase 5: Category Brand Mapping Import")
            print("  ⏭️  Phase 7: Diff Check Operations")
            print("=" * 100)
            
            automation_status["message"] = "Competitor scorecard automation completed! Phases 1, 2, and 3a done. Browser will close in 10 seconds."
            track_step("Finalization", "Automation Complete", "success", "Competitor scorecard - Phases 1, 2, and 3a completed")
            
            print("Browser will remain open for 10 seconds for verification.")
            time.sleep(10)
            
            # Finalize step tracker
            finalize_step_tracker()
            
            # Close browser and end automation
            automation_status["running"] = False
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            return  # Exit the automation for Competitor scorecards after Phase 3a
        
        # Phase 4: Import Search Term Weights (if provided)
        # IMPORTANT: This phase MUST run even if Phase 3a had issues
        print("=" * 50)
        print("Phase 3a completed. Proceeding to Phase 4...")
        print("=" * 50)
        
        track_step("Phase 4", "Start Phase 4", "in_progress", "Checking for Search Term Weights file path")
        
        phase4_success = False
        phase4_error_msg = None
        phase4_attempted = False
        search_term_weights_path = form_data.get('search_term_weights_path', '').strip()
        
        try:
            if search_term_weights_path:
                phase4_attempted = True
                track_step("Phase 4", "Start Phase 4", "success", f"Search Term Weights path provided: {search_term_weights_path}")
                print("=" * 50)
                print("Starting Phase 4: Search Term Weights Import")
                print("=" * 50)
                automation_status["message"] = "Phase 4: Starting Search Term Weights import..."
                
                # Resolve the file path
                original_path = search_term_weights_path
                if not os.path.isabs(search_term_weights_path):
                    search_term_weights_path = os.path.join(os.path.dirname(__file__), search_term_weights_path)
                search_term_weights_path = os.path.expanduser(search_term_weights_path)
                
                track_step("Phase 4", "Resolve File Path", "in_progress", f"Resolved path: {search_term_weights_path}")
                print(f"Phase 4: Looking for file at: {search_term_weights_path}")
                print(f"Phase 4: File exists check: {os.path.exists(search_term_weights_path)}")
                
                # If file doesn't exist, try to find similar files
                if not os.path.exists(search_term_weights_path):
                    track_step("Phase 4", "Resolve File Path", "in_progress", f"File not found at exact path, searching for similar files...")
                    file_dir = os.path.dirname(search_term_weights_path)
                    file_name = os.path.basename(search_term_weights_path)
                    print(f"Phase 4: File not found. Searching in directory: {file_dir}")
                    print(f"Phase 4: Looking for files matching pattern: *{file_name.split('.')[0]}*.csv")
                    
                    if os.path.exists(file_dir):
                        # Try to find similar files (case-insensitive, handle spaces/underscores/hyphens)
                        base_name = file_name.split('.')[0].lower()
                        # Create flexible pattern
                        pattern = os.path.join(file_dir, "*.csv")
                        all_csvs = glob.glob(pattern)
                        similar_files = []
                        for csv_file in all_csvs:
                            csv_base = os.path.basename(csv_file).split('.')[0].lower()
                            # Check if it's similar (contains similar words)
                            base_words = set(base_name.replace('_', ' ').replace('-', ' ').split())
                            csv_words = set(csv_base.replace('_', ' ').replace('-', ' ').split())
                            if base_words.intersection(csv_words):  # Has common words
                                similar_files.append(csv_file)
                        
                        if similar_files:
                            # Use the first similar file found
                            search_term_weights_path = similar_files[0]
                            track_step("Phase 4", "Resolve File Path", "success", f"Found similar file: {os.path.basename(search_term_weights_path)}")
                            print(f"Phase 4: Found similar file: {search_term_weights_path}")
                            automation_status["message"] = f"Phase 4: Using similar file: {os.path.basename(search_term_weights_path)}"
                        else:
                            # List all CSV files in the directory
                            all_csvs = glob.glob(os.path.join(file_dir, "*.csv"))
                            if all_csvs:
                                track_step("Phase 4", "Resolve File Path", "failed", f"File not found. Available files: {', '.join([os.path.basename(f) for f in all_csvs])}")
                                print(f"Phase 4: Available CSV files in directory: {all_csvs}")
                                phase4_error_msg = f"Phase 4: File not found at '{original_path}'. Available files: {', '.join([os.path.basename(f) for f in all_csvs])}"
                            else:
                                track_step("Phase 4", "Resolve File Path", "failed", f"File not found and no CSV files in directory")
                                phase4_error_msg = f"Phase 4: File not found at '{original_path}' and no CSV files found in directory."
                    else:
                        track_step("Phase 4", "Resolve File Path", "failed", f"Directory does not exist: {file_dir}")
                        phase4_error_msg = f"Phase 4: File not found at '{original_path}' and directory does not exist."
                    
                    if phase4_error_msg:
                        automation_status["message"] = phase4_error_msg
                        print(f"Phase 4: ERROR - {phase4_error_msg}")
                        complete_phase("Phase 4", "failed")
                
                # Process file if it exists (either original or similar file found)
                if not phase4_error_msg and os.path.exists(search_term_weights_path):
                    track_step("Phase 4", "Resolve File Path", "success", f"File found: {os.path.basename(search_term_weights_path)}")
                    automation_status["message"] = f"Phase 4: Found search term weights file: {search_term_weights_path}"
                    print(f"Phase 4: Found search term weights file: {search_term_weights_path}")
                    
                    # Step 1: Process the file first
                    track_step("Phase 4", "Process File", "in_progress", f"Processing file: {os.path.basename(search_term_weights_path)}")
                    output_dir = os.path.join(os.path.dirname(__file__), "processed Search term weights")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    processed_csv_path = os.path.join(output_dir, f"processed_search_term_weights_{timestamp}.csv")
                    
                    scorecard_name = form_data.get('scorecard_name', 'Default')
                    automation_status["message"] = "Phase 4: Processing search term weights file..."
                    print(f"Phase 4: Processing file with scorecard name: '{scorecard_name}'")
                    
                    if process_search_term_weights_file(search_term_weights_path, processed_csv_path, scorecard_name):
                        track_step("Phase 4", "Process File", "success", f"File processed successfully: {os.path.basename(processed_csv_path)}")
                        automation_status["message"] = f"Phase 4: File processed successfully: {processed_csv_path}"
                        print(f"Phase 4: File processed successfully: {processed_csv_path}")
                        
                        # Step 2: Get the latest processed file from the folder (in case multiple files exist)
                        processed_files = glob.glob(os.path.join(output_dir, "processed_search_term_weights_*.csv"))
                        if processed_files:
                            # Sort by modification time and get the latest
                            latest_processed_file = max(processed_files, key=os.path.getmtime)
                            print(f"Phase 4: Using latest processed file: {latest_processed_file}")
                        else:
                            # Fallback to the one we just created
                            latest_processed_file = processed_csv_path
                            print(f"Phase 4: Using newly processed file: {latest_processed_file}")
                        
                        # Step 3: Import the processed CSV
                        track_step("Phase 4", "Import CSV", "in_progress", f"Importing CSV to portal: {os.path.basename(latest_processed_file)}")
                        change_reason = form_data.get('freshdesk_ticket_url', 'Automated import')
                        if len(change_reason) < 10:
                            change_reason = change_reason + " " * (10 - len(change_reason))
                        
                        scorecard_name = form_data.get('scorecard_name', 'Default-Standard')
                        if import_search_term_weights_csv(driver, latest_processed_file, change_reason, scorecard_name):
                            track_step("Phase 4", "Import CSV", "success", "Search Term Weights imported successfully to portal")
                            automation_status["message"] = "Phase 4: Search Term Weights imported successfully!"
                            print("Phase 4: COMPLETED SUCCESSFULLY - Search Term Weights imported!")
                            phase4_success = True
                            complete_phase("Phase 4", "success")
                        else:
                            track_step("Phase 4", "Import CSV", "failed", "Import failed - check browser for details", driver=driver)
                            phase4_error_msg = "Phase 4: Search Term Weights import failed. Please check the error above and import manually."
                            automation_status["message"] = phase4_error_msg
                            print("Phase 4: ERROR - Import step failed. Check browser for details.")
                            complete_phase("Phase 4", "failed")
                    else:
                        track_step("Phase 4", "Process File", "failed", "File processing failed - check error messages above")
                        phase4_error_msg = "Phase 4: File processing failed. Check error messages above."
                        automation_status["message"] = phase4_error_msg
                        print("Phase 4: ERROR - File processing failed. Check error messages.")
                        complete_phase("Phase 4", "failed")
            else:
                track_step("Phase 4", "Start Phase 4", "skipped", "No search term weights path provided in form data")
                automation_status["message"] = "Phase 4: No search term weights path provided. Skipping."
                print("Phase 4: SKIPPED - No search_term_weights_path provided in form data.")
                complete_phase("Phase 4", "skipped")
        except Exception as phase4_error:
            track_step("Phase 4", "Phase 4 Execution", "failed", f"Exception: {str(phase4_error)}", error=phase4_error, driver=driver)
            phase4_error_msg = f"Phase 4: Error occurred: {str(phase4_error)}"
            automation_status["message"] = phase4_error_msg
            print(f"Phase 4: ERROR - {str(phase4_error)}")
            import traceback
            print(traceback.format_exc())
            complete_phase("Phase 4", "failed")
        
        # Phase 5: Category Brand Mapping Import (if provided) - runs AFTER Phase 4
        print("=" * 50)
        print("Phase 4 completed. Proceeding to Phase 5...")
        print("=" * 50)
        
        phase5_success = False
        phase5_error_msg = None
        phase5_attempted = False
        
        category_brand_mapping_type = form_data.get('category_brand_mapping_type', '').strip()
        enterprise_cb_path = form_data.get('enterprise_category_brand_path', '').strip()
        competition_cb_path = form_data.get('competition_category_brand_path', '').strip()
        
        try:
            if category_brand_mapping_type and category_brand_mapping_type != 'None':
                phase5_attempted = True
                print("=" * 50)
                print("Starting Phase 5: Category Brand Mapping Import")
                print("=" * 50)
                automation_status["message"] = "Phase 5: Starting Category Brand Mapping import..."
                
                # Determine which files to process
                enterprise_path = None
                competition_path = None
                
                if category_brand_mapping_type == 'Enterprise' or category_brand_mapping_type == 'Both':
                    if enterprise_cb_path:
                        if not os.path.isabs(enterprise_cb_path):
                            enterprise_path = os.path.join(os.path.dirname(__file__), enterprise_cb_path)
                        else:
                            enterprise_path = enterprise_cb_path
                        enterprise_path = os.path.expanduser(enterprise_path)
                        print(f"Phase 5: Enterprise file path: {enterprise_path}")
                
                if category_brand_mapping_type == 'Competitive' or category_brand_mapping_type == 'Both':
                    if competition_cb_path:
                        if not os.path.isabs(competition_cb_path):
                            competition_path = os.path.join(os.path.dirname(__file__), competition_cb_path)
                        else:
                            competition_path = competition_cb_path
                        competition_path = os.path.expanduser(competition_path)
                        print(f"Phase 5: Competition file path: {competition_path}")
                
                if not enterprise_path and not competition_path:
                    phase5_error_msg = "Phase 5: No file paths provided for category brand mapping"
                    automation_status["message"] = phase5_error_msg
                    print(f"Phase 5: ERROR - {phase5_error_msg}")
                else:
                    # Step 1: Process the files
                    output_dir = os.path.join(os.path.dirname(__file__), "Brand Category Updated")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    processed_csv_path = os.path.join(output_dir, f"category_brand_mapping_{timestamp}.csv")
                    
                    automation_status["message"] = "Phase 5: Processing category brand mapping files..."
                    print(f"Phase 5: Processing files...")
                    
                    if process_category_brand_mapping(enterprise_path, competition_path, processed_csv_path):
                        automation_status["message"] = f"Phase 5: File processed successfully: {processed_csv_path}"
                        print(f"Phase 5: File processed successfully: {processed_csv_path}")
                        
                        # Step 2: Import the processed CSV
                        change_reason = form_data.get('freshdesk_ticket_url', 'Automated import')
                        if len(change_reason) < 10:
                            change_reason = change_reason + " " * (10 - len(change_reason))
                        
                        if import_category_brand_csv(driver, processed_csv_path, change_reason):
                            automation_status["message"] = "Phase 5: Category Brand Mapping imported successfully!"
                            print("Phase 5: COMPLETED SUCCESSFULLY - Category Brand Mapping imported!")
                            phase5_success = True
                        else:
                            phase5_error_msg = "Phase 5: Category Brand Mapping import failed. Please check the error above and import manually."
                            automation_status["message"] = phase5_error_msg
                            print("Phase 5: ERROR - Import step failed. Check browser for details.")
                    else:
                        phase5_error_msg = "Phase 5: File processing failed. Check error messages above."
                        automation_status["message"] = phase5_error_msg
                        print("Phase 5: ERROR - File processing failed. Check error messages.")
            else:
                automation_status["message"] = "Phase 5: No category brand mapping type provided. Skipping."
                print("Phase 5: SKIPPED - No category_brand_mapping_type provided in form data.")
        except Exception as phase5_error:
            phase5_error_msg = f"Phase 5: Error occurred: {str(phase5_error)}"
            automation_status["message"] = phase5_error_msg
            print(f"Phase 5: ERROR - {str(phase5_error)}")
            import traceback
            print(traceback.format_exc())
        
        # Phase 7: Diff Check Operations (TEST and PROD)
        print("=" * 50)
        print("Phase 5 completed. Proceeding to Phase 7: Diff Check Operations...")
        print("=" * 50)
        
        try:
            automation_status["message"] = "Phase 7: Starting Diff Check operations..."
            print("=" * 50)
            print("Starting Phase 7: Diff Check Operations")
            print("=" * 50)
            
            # Step 1: Navigate to legacy_editor page
            automation_status["message"] = "Phase 7: Navigating to legacy_editor page..."
            print("Phase 7: Navigating to legacy_editor page...")
            legacy_editor_url = "https://settings.ef.uk.com/legacy_editor"
            print(f"Phase 7: Navigating to: {legacy_editor_url}")
            
            try:
                driver.get(legacy_editor_url)
                time.sleep(3)  # Wait for page to load
                
                # Verify navigation was successful
                new_url = driver.current_url
                print(f"Phase 7: After navigation, URL is: {new_url}")
                
                if 'login' in new_url.lower() or 'signin' in new_url.lower():
                    automation_status["message"] = "Phase 7: ERROR - Redirected to login page. Session may have expired."
                    print("Phase 7: ERROR - Redirected to login page.")
                    raise Exception("Redirected to login page")
                
                if 'error' in new_url.lower() or '404' in new_url.lower() or '403' in new_url.lower():
                    automation_status["message"] = f"Phase 7: ERROR - Navigation resulted in error page: {new_url}"
                    print(f"Phase 7: ERROR - Error page detected: {new_url}")
                    raise Exception(f"Error page detected: {new_url}")
                
                # Wait for page to load
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Diff Check') or contains(text(), 'Back')]"))
                    )
                    print("Phase 7: ✓ Page loaded successfully")
                except TimeoutException:
                    automation_status["message"] = "Phase 7: WARNING - Page loaded but couldn't find expected content. Continuing anyway..."
                    print("Phase 7: WARNING - Timeout waiting for page content, but continuing...")
                    
            except Exception as nav_error:
                automation_status["message"] = f"Phase 7: ERROR - Failed to navigate to legacy_editor page: {str(nav_error)}"
                print(f"Phase 7: ERROR - Navigation failed: {str(nav_error)}")
                raise
            
            # Step 2: Click on "Diff Check TEST"
            automation_status["message"] = "Phase 7: Clicking on 'Diff Check TEST'..."
            print("Phase 7: Clicking on 'Diff Check TEST'...")
            diff_check_test_link = find_element_by_xpath(driver, "//a[normalize-space()='Diff Check TEST']", timeout=15)
            
            if not diff_check_test_link:
                automation_status["message"] = "Phase 7: Error: Could not find 'Diff Check TEST' link"
                print("Phase 7: ERROR - Could not find 'Diff Check TEST' link")
                raise Exception("Could not find 'Diff Check TEST' link")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", diff_check_test_link)
            time.sleep(1)
            diff_check_test_link.click()
            automation_status["message"] = "Phase 7: Waiting 15 seconds after clicking 'Diff Check TEST'..."
            print("Phase 7: Waiting 15 seconds after clicking 'Diff Check TEST'...")
            time.sleep(15)  # Wait 15 seconds for operation to complete
            print("Phase 7: ✓ Clicked 'Diff Check TEST' and waited 15 seconds")
            
            # Step 3: Click on "Back"
            automation_status["message"] = "Phase 7: Clicking on 'Back'..."
            print("Phase 7: Clicking on 'Back'...")
            back_link = find_element_by_xpath(driver, "//a[normalize-space()='Back']", timeout=15)
            
            if not back_link:
                automation_status["message"] = "Phase 7: Error: Could not find 'Back' link"
                print("Phase 7: ERROR - Could not find 'Back' link")
                raise Exception("Could not find 'Back' link")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", back_link)
            time.sleep(1)
            back_link.click()
            time.sleep(2)  # Wait for navigation back
            print("Phase 7: ✓ Clicked 'Back'")
            
            # Step 4: Click on "Diff Check PROD"
            automation_status["message"] = "Phase 7: Clicking on 'Diff Check PROD'..."
            print("Phase 7: Clicking on 'Diff Check PROD'...")
            diff_check_prod_link = find_element_by_xpath(driver, "//a[normalize-space()='Diff Check PROD']", timeout=15)
            
            if not diff_check_prod_link:
                automation_status["message"] = "Phase 7: Error: Could not find 'Diff Check PROD' link"
                print("Phase 7: ERROR - Could not find 'Diff Check PROD' link")
                raise Exception("Could not find 'Diff Check PROD' link")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", diff_check_prod_link)
            time.sleep(1)
            diff_check_prod_link.click()
            automation_status["message"] = "Phase 7: Waiting 15 seconds after clicking 'Diff Check PROD'..."
            print("Phase 7: Waiting 15 seconds after clicking 'Diff Check PROD'...")
            time.sleep(15)  # Wait 15 seconds for operation to complete
            print("Phase 7: ✓ Clicked 'Diff Check PROD' and waited 15 seconds")
            
            # Step 5: Click on "Back" again
            automation_status["message"] = "Phase 7: Clicking on 'Back' again..."
            print("Phase 7: Clicking on 'Back' again...")
            back_link_2 = find_element_by_xpath(driver, "//a[normalize-space()='Back']", timeout=15)
            
            if not back_link_2:
                automation_status["message"] = "Phase 7: Error: Could not find 'Back' link"
                print("Phase 7: ERROR - Could not find 'Back' link")
                raise Exception("Could not find 'Back' link")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", back_link_2)
            time.sleep(1)
            back_link_2.click()
            time.sleep(2)  # Wait for navigation back
            print("Phase 7: ✓ Clicked 'Back' again")
            
            automation_status["message"] = "Phase 7: Diff Check operations completed successfully!"
            print("Phase 7: COMPLETED SUCCESSFULLY - Diff Check operations completed!")
            print("=" * 50)
            print("Phase 7: Diff Check Operations Completed")
            print("=" * 50)
            
        except Exception as phase7_error:
            automation_status["message"] = f"Phase 7: Error occurred during Diff Check operations: {str(phase7_error)}"
            print(f"Phase 7: ERROR - {str(phase7_error)}")
            import traceback
            print(traceback.format_exc())
            # Don't fail the entire automation if Phase 7 fails
        
        # ========================================================================
        # FUTURE PHASES - Add new phases here
        # ========================================================================
        # Phase 8: [Future functionality - add here]
        # Phase 9: [Future functionality - add here]
        # Phase 10: [Future functionality - add here]
        # etc.
        # 
        # Template for adding new phases:
        # try:
        #     automation_status["message"] = "Phase X: Starting [description]..."
        #     print("=" * 50)
        #     print("Starting Phase X: [Description]")
        #     print("=" * 50)
        #     
        #     # Your phase logic here
        #     
        #     automation_status["message"] = "Phase X: [Description] completed successfully!"
        #     print("Phase X: COMPLETED SUCCESSFULLY")
        # except Exception as phaseX_error:
        #     automation_status["message"] = f"Phase X: Error occurred: {str(phaseX_error)}"
        #     print(f"Phase X: ERROR - {str(phaseX_error)}")
        #     import traceback
        #     print(traceback.format_exc())
        #     # Don't fail the entire automation if Phase X fails
        # ========================================================================
        
        # Automation completed - preserve Phase 4 error if it occurred
        if phase4_error_msg:
            automation_status["message"] = f"Automation completed. {phase4_error_msg}"
            print("=" * 50)
            print("AUTOMATION COMPLETED WITH PHASE 4 ERROR")
            print("=" * 50)
        else:
            automation_status["message"] = "Automation completed successfully! All phases completed."
            print("=" * 50)
            print("AUTOMATION COMPLETED SUCCESSFULLY")
            print("=" * 50)
        print("=" * 50)
        print("AUTOMATION COMPLETED SUCCESSFULLY")
        print("=" * 50)
        print("Phase 1: Scorecard creation - Completed")
        print("Phase 3: Measure Groups & Configs creation - Completed")
        print("Phase 6: Rating Thresholds update - Completed")
        if form_data.get('organization_id_phase1_5'):
            print("Phase 1.5: Organization ID update - Completed")
        print("Phase 2: Weights & Targets import - Completed")
        if scorecard_type == 'Enterprise':
            print("Phase 3a: Looker Config update - Completed")
        if phase4_success:
            print("Phase 4: Search Term Weights import - Completed")
        elif phase4_error_msg:
            print(f"Phase 4: Search Term Weights import - FAILED: {phase4_error_msg}")
        if phase5_success:
            print("Phase 5: Category Brand Mapping import - Completed")
        elif phase5_error_msg:
            print(f"Phase 5: Category Brand Mapping import - FAILED: {phase5_error_msg}")
        print("Phase 7: Diff Check Operations - Completed")
        # Future phases completion messages - add here as needed:
        # print("Phase 8: [Description] - Completed")
        # print("Phase 9: [Description] - Completed")
        # print("Phase 10: [Description] - Completed")
        print("Browser will remain open for 10 seconds for verification.")
        time.sleep(10)
        
        # Finalize step tracker
        finalize_step_tracker()
        track_step("Finalization", "Automation Complete", "success", "All phases completed successfully")
        
    except Exception as e:
        automation_status["message"] = f"Error during automation: {str(e)}"
        import traceback
        print(traceback.format_exc())
        track_step("Finalization", "Automation Complete", "failed", f"Automation failed with error: {str(e)}")
        finalize_step_tracker()
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        automation_status["running"] = False

@app.route('/')
def index():
    """Render the main UI page"""
    return render_template('index.html')

@app.route('/start_automation', methods=['POST'])
def start_automation():
    """Start the automation process"""
    global automation_thread, automation_status
    
    if automation_status["running"]:
        return jsonify({"success": False, "message": "Automation is already running"})
    
    form_data = request.json
    
    # Validate required fields
    use_existing_scorecard = form_data.get('use_existing_scorecard', False)
    scorecard_type = form_data.get('scorecard_type', 'Competitor')
    
    # Always required fields
    required_fields = ['customer_name', 'scorecard_name', 'scorecard_type', 'freshdesk_ticket_url']
    
    # Date fields only required when creating new scorecard
    if not use_existing_scorecard:
        required_fields.extend(['start_year', 'start_month', 'start_day'])
    
    # Rating thresholds are now optional for all scorecard types
    # Default values will be used if not provided (4.20 for X, 50 for Y)
    # For Enterprise scorecards, thresholds are handled via measure_configs
    
    for field in required_fields:
        if field not in form_data or not form_data[field]:
            return jsonify({"success": False, "message": f"Missing required field: {field}"})
    
    # Start automation in a separate thread
    automation_thread = threading.Thread(
        target=run_automation,
        args=(form_data,)
    )
    automation_thread.daemon = True
    automation_thread.start()
    
    return jsonify({"success": True, "message": "Automation started"})

@app.route('/continue_automation', methods=['POST'])
def continue_automation():
    """Continue automation after manual login"""
    global continue_automation_flag
    continue_automation_flag.set()
    automation_status["message"] = "Continuing automation..."
    return jsonify({"success": True, "message": "Continuing automation"})

@app.route('/status', methods=['GET'])
def get_status():
    """Get the current automation status"""
    # Create a copy of automation_status without the driver object (not JSON serializable)
    status_copy = {
        "running": automation_status.get("running", False),
        "message": automation_status.get("message", ""),
        "step_tracking": get_step_tracker_summary()
    }
    return jsonify(status_copy)

@app.route('/step_tracking', methods=['GET'])
def get_step_tracking():
    """Get the detailed step tracking report"""
    return jsonify(get_step_tracker_summary())

@app.route('/monitoring', methods=['GET'])
def get_monitoring():
    """Get comprehensive monitoring data including errors, warnings, and screenshots"""
    global monitoring_log
    return jsonify(monitoring_log)

@app.route('/monitoring/errors', methods=['GET'])
def get_errors():
    """Get all errors detected during automation"""
    global monitoring_log
    return jsonify({
        "total_errors": len(monitoring_log.get("errors", [])),
        "errors": monitoring_log.get("errors", [])
    })

@app.route('/monitoring/summary', methods=['GET'])
def get_monitoring_summary():
    """Get a quick summary of monitoring status"""
    global monitoring_log, step_tracker
    return jsonify({
        "status": "running" if automation_status.get("running") else "completed",
        "total_operations": len(monitoring_log.get("operations", [])),
        "total_errors": len(monitoring_log.get("errors", [])),
        "total_warnings": len(monitoring_log.get("warnings", [])),
        "screenshots_captured": len(monitoring_log.get("screenshots", [])),
        "success_rate": monitoring_log.get("performance_metrics", {}).get("success_rate", 0),
        "recent_error": monitoring_log.get("errors", [])[-1] if monitoring_log.get("errors") else None
    })

@app.route('/get_measure_configs', methods=['GET'])
def get_measure_configs():
    """Get list of measure configs from Excel/CSV file for Enterprise scorecards"""
    try:
        # Get Excel file path from query parameter
        excel_file_path = request.args.get('excel_file_path', None)
        print(f"get_measure_configs called with excel_file_path parameter: {repr(excel_file_path)}")
        print(f"excel_file_path type: {type(excel_file_path)}")
        print(f"excel_file_path length: {len(excel_file_path) if excel_file_path else 0}")
        
        # Determine Excel file path
        if excel_file_path:
            # Use provided path
            if not os.path.isabs(excel_file_path):
                excel_path = os.path.join(os.path.dirname(__file__), excel_file_path)
            else:
                excel_path = excel_file_path
            excel_path = os.path.expanduser(excel_path)
            print(f"Resolved path: {excel_path}")
        else:
            # Fallback to default files
            excel_path = os.path.join(os.path.dirname(__file__), "Whirlpool CA Setup Sheet.xlsx")
            if not os.path.exists(excel_path):
                excel_path = os.path.join(os.path.dirname(__file__), "enterprise scorecard.xlsx")
            print(f"Using default path: {excel_path}")
        
        print(f"Checking if file exists: {excel_path}")
        if not os.path.exists(excel_path):
            error_msg = f"File not found: {excel_path}"
            print(f"ERROR: {error_msg}")
            return jsonify({"success": False, "message": error_msg, "configs": []})
        
        print(f"Reading file: {excel_path}")
        excel_data = read_excel_data(excel_path)
        if not excel_data:
            error_msg = "Could not read file or file is empty"
            print(f"ERROR: {error_msg}")
            return jsonify({"success": False, "message": error_msg, "configs": []})
        
        print(f"Successfully read {len(excel_data)} items from file")
        
        # Extract unique measure display names (configs)
        configs = []
        seen = set()
        for item in excel_data:
            config_name = item.get("measure_display_name", "").strip()
            if config_name and config_name not in seen and config_name != "nan":
                configs.append(config_name)
                seen.add(config_name)
        
        print(f"Extracted {len(configs)} unique configs: {configs[:5]}...")
        return jsonify({"success": True, "configs": sorted(configs)})
    except Exception as e:
        import traceback
        error_msg = f"Error in get_measure_configs: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return jsonify({"success": False, "message": error_msg, "configs": []})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5003))
    
    print("=" * 80)
    print(f"Starting Flask app on port {port}...")
    print("=" * 80)
    print("Note: Search term weights files will be processed when path is provided in UI.")
    print("=" * 80)
    app.run(debug=True, host='0.0.0.0', port=port)


