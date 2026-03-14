import fitz  # PyMuPDF
import os
import json
import re
# import google.generativeai as genai
import base64
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from PIL import Image
import io
from pydantic import BaseModel, Field
from typing import List, Dict, Any 
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda
# ==========================================
# CONFIGURATION & SETUP
# ==========================================
# Replace with your actual Gemini API key or set it as an environment variable
# genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY"))

# We use Gemini 1.5 Flash because it is fast and excellent for vision tasks
VISION_MODEL = ChatOllama(model = "qwen3.5:397b-cloud" )
text_llm = ChatOllama(model="qwen3.5:397b-cloud", temperature=0.0)
IMAGE_OUTPUT_DIR = "extracted_images"
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
# class ChecklistItem(BaseModel):
#     category: str = Field(description="The checklist name, e.g., 'WC' or 'External Wall'")
#     item: str = Field(description="The specific item checked")
#     status: str = Field(description="The status or condition noted")

# class SummaryMapping(BaseModel):
#     impacted_area: str = Field(description="The negative side or affected room")
#     source_area: str = Field(description="The positive side or source of the problem")

# class GlobalContext(BaseModel):
#     # Metadata pulled to the absolute top level (No nesting)
#     inspection_date_and_time: str = Field(default="Not Available")
#     inspected_by: str = Field(default="Not Available")
#     property_age_years: str = Field(default="Not Available")
#     property_type: str = Field(default="Not Available")
#     floors: str = Field(default="Not Available")
    
#     # Flat lists are the most reliable format for local LLMs
#     checklists: List[ChecklistItem] = Field(default_factory=list)
#     summary_table_mapping: List[SummaryMapping] = Field(default_factory=list)
class GlobalContext(BaseModel):
    header_metadata: str = Field(description="A single string containing Inspection Date, Inspected By, Property Age, Type, and Floors. (e.g., 'Date: 27.09.2022 | Inspector: Krushna | Type: Flat | Floors: 11')")
    
    flagged_issues_summary: str = Field(description="A 2-3 sentence summary of the checklists. Mention what major items failed (e.g., 'Concealed plumbing leaks in WC, moderate cracks on external wall').")
    
    root_cause_mapping: str = Field(description="A detailed summary paragraph explaining the cause-and-effect mappings found in the report (e.g., 'The dampness in the Hall skirting is caused by gaps in the Common Bathroom tile joints. The Master Bedroom wall dampness is linked to external wall cracks.')")


# def extract_full_text_context(pdf_path):
#     print(f"Extracting Global Text Context from {pdf_path}...")
#     doc = fitz.open(pdf_path)
    
#     # Gather all text from the document
#     full_text = ""
#     for page in doc:
#         full_text += page.get_text("text") + "\n"
        
#     prompt = ChatPromptTemplate.from_messages([
#         ("system", "You are a data extraction assistant. Extract the required building inspection metadata and summarize the key textual observations, flagged items, and checklists from the raw PDF text. Do not invent facts. If a value is missing, write 'Not Available'."),
#         ("user", "Raw PDF Text:\n{full_text}\n\nExtract the requested fields.")
#     ])
    
#     structured_llm = text_llm.with_structured_output(GlobalContext)
#     chain = prompt | structured_llm
    
#     try:
#         # Pass the raw text to Qwen
#         result = chain.invoke({"full_text": full_text})
#         return result.dict()
#     except Exception as e:
#         print(f"Text Context Extraction Error: {e}")
#         return {}
def extract_full_text_context(pdf_path):
    print(f"Extracting Global Text Context from {pdf_path} using Ultra-Flat Schema...")
    doc = fitz.open(pdf_path)
    
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"
        
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert data extraction AI. Read the building inspection report and extract the exact fields requested.
        CRITICAL RULES:
        1. You MUST include inspection_date_and_time, inspected_by, property_age_years, property_type, and floors. Do not skip them.
        2. For 'checklists', extract every checklist item and assign it to its proper 'category'.
        3. For 'summary_table_mapping', extract the table mapping the Impacted Area to its Source Area.
        Do not invent data. Use 'Not Available' if missing. Respond in JSON format. The Keys should contain "inspection_date_and_time" , 
        "inspected_by" , "property_age_years" , "property_type" , "floors" , "checklists" , "summary_table_mapping" . Other keys may be also possible """),
        ("user", "Raw PDF Text:\n{full_text}\n\nExtract the structured context now.")
    ])
    
    # structured_llm = text_llm.with_structured_output(GlobalContext)
    chain = prompt | text_llm | JsonOutputParser()

    
    try:
        result = chain.invoke({"full_text": full_text})
        with open('global_context.json','w') as f:
            json.dump(result.content,f, indent=4)
    except Exception as e:
        print("Error Occured! but here is the response whatever generated")
        print(result.content)

        
def get_vlm_description(image_path, image_type="site"):
    """Generates a semantic description of the image to help the Reasoning Agent later."""
    try:
        # img = Image.open(image_path)

        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        
        img = encode_image(image_path)
        
        if image_type == "site":
            prompt = """
            Describe this building inspection photo in 1-2 concise sentences. 
            Focus strictly on: 1) The room/area (if identifiable), 2) The specific structural element (wall, ceiling, skirting, tiles), 3) Any visible defects (dampness, cracks, hollowness).
            If this is a logo, map, cover page, or not a photo of a building, reply with exactly: UNRELATED_IMAGE.
            """
        else: # thermal
            prompt = """
            Analyze this thermal imaging scan from a building inspection. 
            Ignore the bright heat map colors. Look closely at the underlying physical shapes, lines, geometry, and textures visible in the background.
            Describe the physical location. Is it a flat wall? A corner where a wall meets a ceiling? A floor skirting/baseboard? Bathroom tiles? 
            Provide a 1-sentence best educated guess of the structural geometry you see. Do not describe the temperature, only the physical structure.
            """
        message = HumanMessage(
                            content=[
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                                },
                            ]
                        )
        response = VISION_MODEL.invoke([message])
        desc = response.content.strip()
        
        # Check for our exclusion flag
        if "UNRELATED_IMAGE" in desc:
            return "UNRELATED", True
            
        return desc, False
        
    except Exception as e:
        print(f"VLM Error on {image_path}: {e}")
        return "Description failed", False


def extract_inspection_data(pdf_path):
    print(f"Extracting Inspection Data from {pdf_path} using Geospatial Sorting...")
    doc = fitz.open(pdf_path)
    inspection_data = []
    
    # 1. Gather all elements across the entire document with their Y-coordinates
    all_elements = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        for block in blocks:
            # Type 0 is Text
            if block["type"] == 0:
                text = "".join([span["text"] for line in block["lines"] for span in line["spans"]]).strip()
                if text:
                    all_elements.append({
                        "type": "text",
                        "content": text,
                        "page": page_num,
                        "y0": block["bbox"][1] # bbox[1] is the top Y-coordinate
                    })
            # Type 1 is Image
            elif block["type"] == 1:
                all_elements.append({
                    "type": "image",
                    "bytes": block["image"],
                    "ext": block["ext"],
                    "page": page_num,
                    "y0": block["bbox"][1] # bbox[1] is the top Y-coordinate
                })

    # 2. Sort all elements strictly by Page Number, then by top-to-bottom Y-coordinate
    all_elements.sort(key=lambda x: (x["page"], x["y0"]))
    
    # 3. Run the State Machine over the visually sorted elements
    current_area = "Unknown Area"
    current_side = "Unknown Side"
    current_description = ""
    expecting_description = False
    img_counter = 1
    
    for el in all_elements:
        if el["type"] == "text":
            text = el["content"]
            
            # Update state based on text
            if "Impacted Area" in text:
                current_area = text
            elif "Negative side Description" in text:
                current_side = "Negative"
                expecting_description = True
            elif "Positive side Description" in text:
                current_side = "Positive"
                expecting_description = True
            elif expecting_description and "photographs" not in text.lower():
                current_description = text
                expecting_description = False
                
        elif el["type"] == "image":
            # Process the image using the current visual state
            image_bytes = el["bytes"]
            image_ext = el["ext"]
            
            photo_id = f"Photo_p{el['page']+1}_{img_counter}"
            image_filename = f"{photo_id}.{image_ext}"
            image_path = os.path.join(IMAGE_OUTPUT_DIR, image_filename)
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
                
            # Get VLM Description 
            vlm_desc, is_unrelated = get_vlm_description(image_path, "site")
            
            if not is_unrelated:
                d = {
                    "id": photo_id,
                    "area": current_area,
                    "side": current_side,
                    "pdf_description": current_description,
                    "vlm_visual_description": vlm_desc,
                    "image_path": image_path
                }
                inspection_data.append({
                    "id": photo_id,
                    "area": current_area,
                    "side": current_side,
                    "pdf_description": current_description,
                    "vlm_visual_description": vlm_desc,
                    "image_path": image_path
                })
            
            img_counter += 1
            
    return inspection_data

def extract_thermal_data(pdf_path):
    print(f"Extracting Thermal Data from {pdf_path}...")
    doc = fitz.open(pdf_path)
    print("PyMuPdf opened")
    thermal_data = []
    print("Loop begins")
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        thermal_id_match = re.search(r'Thermal image\s*:\s*(RB[0-9A-Z]+\.JPG)', text, re.I)
        hotspot_match = re.search(r'Hotspot\s*:\s*([\d.]+ *°C)', text, re.I)
        coldspot_match = re.search(r'Coldspot\s*:\s*([\d.]+ *°C)', text, re.I)
        
        if thermal_id_match:
            thermal_id = thermal_id_match.group(1)
            hotspot = hotspot_match.group(1) if hotspot_match else "N/A"
            coldspot = coldspot_match.group(1) if coldspot_match else "N/A"
            
            # Calculate Temperature Differential
            temp_diff = "N/A"
            try:
                if hotspot != "N/A" and coldspot != "N/A":
                    h_val = float(hotspot.replace('°C', ''))
                    c_val = float(coldspot.replace('°C', ''))
                    temp_diff = h_val - c_val
            except ValueError:
                pass
            print("Actual thermal images")    
            image_list = page.get_images(full=True)
            if image_list:
                # Find the LARGEST image on the page to avoid extracting logos/icons
                largest_xref = None
                max_size = 0
                
                for img_meta in image_list:
                    xref = img_meta[0]
                    img_info = doc.extract_image(xref)
                    
                    # Calculate pixel area (width * height)
                    width = img_info.get("width", 0)
                    height = img_info.get("height", 0)
                    area = width * height
                    
                    if area > max_size:
                        max_size = area
                        largest_xref = xref
                
                # Now extract ONLY the largest image found
                if largest_xref:
                    base_image = doc.extract_image(largest_xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    image_filename = f"{thermal_id}.{image_ext}"
                    image_path = os.path.join(IMAGE_OUTPUT_DIR, image_filename)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                        
                    # Get VLM Description of the background
                    vlm_desc, _ = get_vlm_description(image_path, "thermal")
                    # d = {
                    #     "thermal_id": thermal_id,
                    #     "hotspot": hotspot,
                    #     "coldspot": coldspot,
                    #     "temp_differential": temp_diff,
                    #     "vlm_visual_description": vlm_desc,
                    #     "image_path": image_path
                    # }
                    # print("*"*50)
                    # print(d)
                    # print("*"*50)

                    thermal_data.append({
                        "thermal_id": thermal_id,
                        "hotspot": hotspot,
                        "coldspot": coldspot,
                        "temp_differential": temp_diff,
                        "vlm_visual_description": vlm_desc,
                        "image_path": image_path
                    })
        return thermal_data


def run_extraction_agent(sample_pdf_path, thermal_pdf_path):
    print("--- STARTING PHASE 1: EXTRACTION AGENT ---")
    inspection_data = extract_inspection_data(sample_pdf_path)
    with open("inspection_data.json", "w") as f:
        json.dump(inspection_data, f, indent=4)
    print(f"Saved {len(inspection_data)} inspection records.")
        
    thermal_data = extract_thermal_data(thermal_pdf_path)
    with open("thermal_data.json", "w") as f:
        json.dump(thermal_data, f, indent=4)
    print(f"Saved {len(thermal_data)} thermal records.")
    
    print("--- PHASE 1 COMPLETE ---")
    return inspection_data, thermal_data

if __name__ == "__main__":
    # Test the agent directly
    sample_report = r"C:\Downloads\ReportAI\Sample Report.pdf"
    Thermal_Images = r"C:\Downloads\ReportAI\Thermal Images.pdf"
    run_extraction_agent(sample_report, Thermal_Images)

# sample_report = r"C:\Downloads\ReportAI\Sample Report.pdf"
# # extract_inspection_data(sample_report)
# extract_full_text_context(sample_report)

# Thermal_Images = r"C:\Downloads\ReportAI\Thermal Images.pdf"
# thermal_data = extract_thermal_data(Thermal_Images)
# with open("thermal_data.json", "w") as f:
#     json.dump(thermal_data, f, indent=4)