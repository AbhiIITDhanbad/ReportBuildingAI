import json
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import Any
from langchain_core.output_parsers import JsonOutputParser

llm = ChatOllama(
    model="qwen3.5:397b-cloud", 
    temperature=0.0 
)

class MatchResult(BaseModel):
    step_by_step_reasoning: Any = Field(description="Compare the structural elements of the inspection photo with the thermal candidates. Explain exactly why they logically match or why none match.")
    matched_thermal_id: Any = Field(description="The exact thermal_id (e.g., RB02380X.JPG) that matches, or 'NONE' if no match is found.")
    confidence_score: int = Field(description="Score from 0 to 100 on how confident you are in this match based on visual overlap.")

class EngineeringAnalysis(BaseModel):
    probable_root_cause: str = Field(description="A technical explanation of why these issues are occurring (e.g., Capillary action, external plumbing leaks, RCC cracks).")
    severity_assessment: str = Field(description="Rate as Low, Medium, or High, followed by a 1-sentence engineering justification.")
    recommended_actions: str = Field(description="recommended action to be taken")

def find_matching_thermal_image(inspection_item, available_thermal_pool):
    """Uses LLM to logically pair a site photo with a thermal image from the remaining pool."""

    if not available_thermal_pool:
        return "NONE", "Thermal candidate pool is empty. No more images to match."


    thermal_candidates_text = ""
    for t in available_thermal_pool:
        thermal_candidates_text += f"- ID: {t['thermal_id']} | Background Features: {t['vlm_visual_description']}\n"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert forensic building inspector. Your task is to match a standard site photograph to its corresponding thermal scan based strictly on geometric and structural text descriptions. Think step-by-step."),
        ("user", """
        Target Inspection Photo:
        - Location: {area}
        - Defect Noted in Report: {pdf_description}
        - Visual Features (from VLM): {vlm_description}
        
        Remaining Unmatched Thermal Candidates:
        {thermal_candidates_text}
        
        Instructions:
        1. Compare the 'Visual Features' of the target with the 'Background Features' of the remaining candidates.
        2. Look for matching geometric cues (e.g., 'skirting board', 'ceiling corner', 'bathroom tiles').
        3. If a candidate is a logical structural match, output its ID. If nothing matches logically, output 'NONE'.
        Respond in JSON format with step_by_step_reasoning ("Compare the structural elements of the inspection photo with the thermal candidates. Explain exactly why they logically match or why none match.") , matched_thermal_id("The exact thermal_id (e.g., RB02380X.JPG) that matches, or 'NONE' if no match is found."), confidence_score as integer 
        """)
    ])
    

    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "area": inspection_item['area'],
            "pdf_description": inspection_item['pdf_description'],
            "vlm_description": inspection_item['vlm_visual_description'],
            "thermal_candidates_text": thermal_candidates_text
        })
        if(type(result)!=str):
        # Guardrail
            if result.get("matched_thermal_id","NONE") != "NONE" and result.get("confidence_score","30") < 70:
                return "NONE", f"Rejected: Low confidence score ({result.get("confidence_score","30")}%). AI Reasoning: {result.get("step_by_step_reasoning")}"
            else:
                return result.get("matched_thermal_id","NONE"), result.get("step_by_step_reasoning")
        else :
            print("*"*50)
            print(type(result.content))
            print(result)
            print("*"*50)
            return None,None
        
    except Exception as e:
        print(f"LLM Matching Error for {inspection_item['id']}: {e}")
        return "NONE", "Error during LLM inference."

def generate_engineering_analysis(master_data):
    """Analyzes the combined data to generate Root Cause and Severity."""
    
    issue_summary = ""
    for area in master_data['negative_observations']:
        issue_summary += f"- {area['inspection_data']['area']}: {area['inspection_data']['pdf_description']}. "
        if area['thermal_data']:
            issue_summary += f"Thermal diff: {area['thermal_data']['temp_differential']}°C.\n"
    
    with open('global_context.json','r') as f:
        global_context = json.load(f)
        # print("json openend")
    if(global_context is None):
        with open('global_context.txt','r') as f:
            global_context = f.read()  

    try:
        summary_mapping = json.dumps(global_context.get("summary_table_mapping", None), indent=2)
    except:
        summary_mapping = None
    try:
        checklists = json.dumps(global_context.get("checklists", None), indent=2)
    except:
        checklists = None
    # try:
    #     flagged = ", ".join(global_context.get("flagged_items", []))
    # except:
    #     flagged = None


    if(summary_mapping and checklists):
        print("summary_mapping and checklist got from json")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Senior Structural Engineer generating a professional diagnosis report. You must base your Root Cause and Recommendations strictly on the provided inspector mapping and checklists. Do not invent external causes."),
            ("user", f"""
            Visual & Thermal Defect Summary (What the AI saw):
            {{issue_summary}}
            
            Inspector's Source Mapping (The actual causes):
            {{summary_mapping}}
            
            Failed Checklists & Flagged Items:
            {{checklists}}
            
            Instructions:
            1. Probable Root Cause: Correlate the visual defects with the Inspector's Source Mapping (e.g., if Hall has dampness, explicitly state it is caused by the Common Bathroom tile gaps as noted by the inspector).
            2. Severity Assessment: Use the checklist data (e.g., "Moderate cracks", "Concealed plumbing leakage") to justify a High, Medium, or Low severity.
            3. Recommended Actions: Provide direct repair steps for the failed checklist items (e.g., "Regrout tile gaps in WC", "Seal moderate cracks on external RCC").
            4. issue_summary: From the given issue_summary excerpts generate a curated summary of the issues .
            Respond in JSON format with root_cause , severity , recommended_actions , issue_summary as keys
            """)
        ])

        chain = prompt | llm | JsonOutputParser()
        try:
            result = chain.invoke({"issue_summary": issue_summary, "summary_mapping":summary_mapping, "checklists":checklists})
            return result
        except Exception as e:
            print(f"Engineering Analysis Error: {e}")
            return None
    else:
        print("dodn't get summary mapping ")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Senior Structural Engineer generating a professional diagnosis report. You must base your Root Cause and Recommendations strictly on the provided inspector mapping and checklists. Do not invent external causes."),
            ("user", f"""
            Visual & Thermal Defect Summary (What the AI saw)  , Inspector's Source Mapping (The actual causes) , Failed Checklists & Flagged Items etc. details can be find from below:
            {global_context}
            
            Instructions:
            1. Probable Root Cause: Correlate the visual defects with the Inspector's Source Mapping (e.g., if Hall has dampness, explicitly state it is caused by the Common Bathroom tile gaps as noted by the inspector).
            2. Severity Assessment: Use the checklist data (e.g., "Moderate cracks", "Concealed plumbing leakage") to justify a High, Medium, or Low severity.
            3. Recommended Actions: Provide direct repair steps for the failed checklist items (e.g., "Regrout tile gaps in WC", "Seal moderate cracks on external RCC").
            Respond in JSON Format with root_cause , severity , recommended_actions as keys
            """)
        ])

        structured_llm = llm.with_structured_output(EngineeringAnalysis)
        chain = prompt | structured_llm
        
        try:
            result = chain.invoke({"global_context":global_context})
            return result
        except Exception as e:
            print(f"Engineering Analysis Error: {e}")
            return None


def run_reasoning_agent():
    print("--- STARTING PHASE 2: REASONING AGENT ---")
    
    # 1. Load Data
    try:
        with open("inspection_data.json", "r") as f:
            inspection_data = json.load(f)
        with open("thermal_data.json", "r") as f:
            thermal_data = json.load(f)
    except FileNotFoundError:
        print("Error: JSON files from Extraction Agent not found. Run Phase 1 first.")
        return
        
    master_report = {
        "negative_observations": [],
        "positive_references": [],
        "engineering_analysis": {},
        "missing_information": []
    }
    
    # Create a dynamic pool of available thermal images
    available_thermal_pool = [t for t in thermal_data]
    print(f"Initial Thermal Pool Size: {len(available_thermal_pool)}")
    
    # 2. Iterate and Classify
    for item in inspection_data:
        if item["side"] == "Positive":
            # Positive side photos are references, no thermal match needed
            master_report["positive_references"].append(item)
            print(f"Logged Positive Reference: {item['id']}")
            
        elif item["side"] == "Negative":
            print(f"\nMatching thermal image for: {item['id']} ({item['area']})...")
            matched_id, reasoning = find_matching_thermal_image(item, available_thermal_pool)
            
            thermal_payload = None
            if matched_id != "NONE":
                # Find the matched dictionary
                thermal_payload = next((t for t in thermal_data if t['thermal_id'] == matched_id), None)
                
                available_thermal_pool = [t for t in available_thermal_pool if t['thermal_id'] != matched_id]
                print(f"  -> SUCCESS: Matched with {matched_id}.")
                print(f"  -> Remaining thermal pool size: {len(available_thermal_pool)}")
            else:
                master_report["missing_information"].append(f"Thermal Evidence missing for {item['area']}: {item['pdf_description']}")
                print(f"  -> NO MATCH. Reason: {reasoning}")
            
            master_report["negative_observations"].append({
                "inspection_data": item,
                "thermal_data": thermal_payload,
                "llm_match_reasoning": reasoning
            })

    print("\nGenerating Root Cause and Severity Analysis...")
    analysis = generate_engineering_analysis(master_report)
    
    if analysis:
        master_report["root_cause"] = analysis.get("root_cause" , None)
        master_report["severity"] = analysis.get("severity_assessment",None)
        master_report["recommended_actions"] = analysis.get("recommended_actions",None)
        master_report["issue_summary"] = analysis.get("issue_summary",None)
        print("Analysis Generated Successfully.")
    
    # 4. Save Master Data
    with open("master_report_data.json", "w") as f:
        json.dump(master_report, f, indent=4)
        
    print(f"\n--- PHASE 2 COMPLETE: Saved master_report_data.json ---")

if __name__ == "__main__":
    run_reasoning_agent()


# with open('master_report_data.json','r') as f:
#     master_data = json.load(f)
# print("starting analysis")
# analysis = generate_engineering_analysis(master_data)

# if analysis:
#     print("Got analysis")
#     master_data["root_cause"] = analysis.get("root_cause" , None)
#     master_data["severity"] = analysis.get("severity_assessment",None)
#     master_data["recommended_actions"] = analysis.get("recommended_actions",None)
#     master_data["issue_summary"] = analysis.get("issue_summary",None)
# else:
#     print("didn';t get analysis")
# with open('master_report_data.json','w') as f:
#     json.dump(master_data, f , indent=4)
