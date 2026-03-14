import json
import os
from datetime import datetime

# ==========================================
# ROBUSTNESS UTILITIES
# ==========================================
def safe_extract(data_dict, primary_key, secondary_dict_key=None):
    """Safely hunts for a key, handling nulls and nested dictionaries."""
    # First check the specified nested dictionary if provided
    if secondary_dict_key and secondary_dict_key in data_dict:
        nested = data_dict[secondary_dict_key]
        if isinstance(nested, dict) and nested.get(primary_key) is not None:
            return nested[primary_key]
            
    # Fallback to checking the root level
    val = data_dict.get(primary_key)
    return val if val is not None else "DATA NOT AVAILABLE"

def format_content(content):
    """Safely formats content, converting lists to markdown bullets if necessary."""
    if content == "DATA NOT AVAILABLE" or content is None:
        return "> DATA NOT AVAILABLE\n"
        
    if isinstance(content, list):
        if not content:
            return "> DATA NOT AVAILABLE\n"
        # Convert list array into clean markdown bullet points
        return "\n".join([f"- {str(item).strip()}" for item in content]) + "\n"
        
    return str(content).strip() + "\n"

# ==========================================
# MAIN SYNTHESIS LOGIC
# ==========================================
def generate_markdown_report(master_data_path="master_report_data.json", output_file="Final_DDR_Report.md"):
    print("--- STARTING PHASE 3: SYNTHESIS AGENT ---")
    
    try:
        with open(master_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {master_data_path} not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: {master_data_path} is corrupted or not valid JSON.")
        return
    with open("global_context.json","r") as f:
    # Extract top-level containers
        global_context = json.load(f)
    negative_obs = data.get("negative_observations", [])
    positive_refs = data.get("positive_references", [])
    missing_info = data.get("missing_information", [])

    md = []
    
    # ==========================================
    # REPORT HEADER
    # ==========================================
    md.append("# Detailed Diagnosis Report (DDR)\n")
    
    insp_date = global_context.get("inspection_date_and_time", 'Not Available')
    insp_by = global_context.get('inspected_by', 'Not Available')
    prop_type = global_context.get('property_type', 'Not Available')
    floors = global_context.get('floors', 'Not Available')
    
    md.append(f"**Inspection Date:** {insp_date} | **Inspected By:** {insp_by}")
    md.append(f"**Property Type:** {prop_type} | **Floors:** {floors}")
    md.append(f"**Report Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("---\n")

    # ==========================================
    # 1. PROPERTY ISSUE SUMMARY
    # ==========================================
    md.append("## 1. Property Issue Summary")
    summary = safe_extract(data, "issue_summary")
    md.append(format_content(summary))

    # ==========================================
    # 2. AREA-WISE OBSERVATIONS
    # ==========================================
    md.append("## 2. Area-wise Observations\n")
    md.append("### A. THERMAL REFERENCES FOR NEGATIVE SIDE INPUTS")
    
    if not negative_obs:
        md.append("> DATA NOT AVAILABLE\n")
    else:
        for obs in negative_obs:
            ins_data = obs.get("inspection_data", {})
            therm_data = obs.get("thermal_data")
            
            # Default fallbacks for missing keys inside the observation
            area_name = ins_data.get('area', 'Unknown Area')
            defect_desc = ins_data.get('pdf_description', 'Description Not Available')
            ai_reasoning = obs.get('llm_match_reasoning', 'Not Available')
            
            md.append(f"#### Location: {area_name}")
            md.append(f"**Defect Noted:** {defect_desc}\n")
            
            md.append("| Visual Evidence | Thermal Evidence |")
            md.append("| :---: | :---: |")
            
            # Robust Visual Image Handling
            v_path = ins_data.get('image_path')
            visual_img = f"![Visual]({v_path})" if v_path else "**Image Not Available**"
            
            # Robust Thermal Image Handling
            if therm_data and isinstance(therm_data, dict):
                t_path = therm_data.get('image_path')
                t_diff = therm_data.get('temp_differential', 'N/A')
                therm_img = f"![Thermal]({t_path})<br>*{t_diff}°C Differential*" if t_path else "**Image Not Available**"
            else:
                therm_img = "**Thermal Evidence: Not Available**"
                
            md.append(f"| {visual_img} | {therm_img} |")
            md.append(f"**AI Match Reasoning:** *{ai_reasoning}*\n")

    md.append("### B. VISUAL REFERENCES FOR POSITIVE SIDE INPUTS")
    if not positive_refs:
        md.append("> DATA NOT AVAILABLE\n")
    else:
        for ref in positive_refs:
            md.append(f"#### Location: {ref.get('area', 'Unknown Area')}")
            img_path = ref.get("image_path")
            if img_path:
                md.append(f"![Positive Reference]({img_path})\n")
            else:
                md.append("> **Image Not Available**\n")

    # ==========================================
    # 3. PROBABLE ROOT CAUSE
    # ==========================================
    md.append("## 3. Probable Root Cause")
    # Searches 'engineering_analysis' first, then root level.
    root_cause = safe_extract(data, "root_cause")
    md.append(format_content(root_cause))

    # ==========================================
    # 4. SEVERITY ASSESSMENT
    # ==========================================
    md.append("## 4. Severity Assessment (with reasoning)")
    # The JSON shows severity was sometimes returning `null`. 
    # The `safe_extract` handles this and converts to DATA NOT AVAILABLE.
    severity = safe_extract(data, "severity")
    md.append(format_content(severity))

    # ==========================================
    # 5. RECOMMENDED ACTIONS
    # ==========================================
    md.append("## 5. Recommended Actions")
    # The JSON snippet showed recommended_actions returning as an array. 
    # format_content() will intelligently map this to bullet points.
    actions = safe_extract(data, "recommended_actions")
    md.append(format_content(actions))

    # ==========================================
    # 6. ADDITIONAL NOTES
    # ==========================================
    md.append("## 6. Additional Notes")
    has_notes = False
    
    # 1. Look for the inspector's summary table mapping in the global context
    summary_mapping = global_context.get("summary_table_mapping", [])
    
    if summary_mapping and isinstance(summary_mapping, list):
        md.append("### Inspector's Original Summary Mapping")
        md.append("| Impacted Area (-ve side) | Source Area (+ve side) |")
        md.append("| :--- | :--- |")
        
        for mapping in summary_mapping:
            # Safely handle both key variations depending on the schema output
            impacted = mapping.get("impacted_area", mapping.get("impacted", "N/A"))
            source = mapping.get("source_area", mapping.get("source", "N/A"))
            
            # Clean up the text to prevent markdown table breaking
            impacted_clean = str(impacted).replace('\n', ' ').strip()
            source_clean = str(source).replace('\n', ' ').strip()
            
            md.append(f"| {impacted_clean} | {source_clean} |")
            
        md.append("\n")
        has_notes = True
        if not has_notes:
            md.append("> DATA NOT AVAILABLE\n")
    # ==========================================
    # 7. MISSING OR UNCLEAR INFORMATION
    # ==========================================
    md.append("## 7. Missing or Unclear Information")
    if not missing_info:
        md.append("All expected structural and thermal data was successfully extracted and correlated.\n")
    else:
        md.append("The following data gaps were identified by the system:\n")
        for info in missing_info:
            md.append(f"- **Not Available:** {info}")

    # ==========================================
    # EXPORT
    # ==========================================
    markdown_content = "\n".join(md)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)
        
    print(f"--- PHASE 3 COMPLETE: Final DDR generated at {output_file} ---")

if __name__ == "__main__":
    generate_markdown_report()