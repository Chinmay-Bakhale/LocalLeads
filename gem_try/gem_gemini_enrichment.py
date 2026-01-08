# gemini_enrichment.py
import google.generativeai as genai
import os
import json
import time
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google import genai

# --- Configuration & Initialization ---
def get_gemini_client(api_key):
    """Configures and returns the Gemini client."""
    if not api_key:
        raise ValueError("Gemini API Key is required.")
    genai.configure(api_key=api_key)
    # Using Gemini 1.5 Flash - good balance of speed, capability, and cost for this task
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        # Optional Configurations:
        # generation_config={"temperature": 0.5},
        # safety_settings={ # Adjust safety settings if needed
        #     HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        #     HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        #     HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        #     HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        # }
    )
    return model

# --- Define the Search Tool ---
search_tool = genai.Tool(
    google_search_retrieval=genai.types.GoogleSearchRetrieval(disable_attribution=False)
)

# --- Enrichment Function ---
def enrich_lead_data_with_gemini(gemini_model, lead_data):
    """
    Uses Gemini and Google Search tool to enrich lead data.

    Args:
        gemini_model: The initialized Gemini GenerativeModel client.
        lead_data (dict): Basic lead info (must include 'name' and 'address').

    Returns:
        dict: Enriched fields ('linkedin_url', 'key_contacts', 'description', 'enriched_website').
              Values are 'N/A' or empty if not found. Returns dict with error messages on failure.
    """
    if not lead_data.get('name') or not lead_data.get('address'):
        print("Warning: Lead name or address missing for enrichment.")
        return {'linkedin_url': 'N/A', 'key_contacts': [], 'description': 'Missing Input', 'enriched_website': 'N/A'}

    business_name = lead_data['name']
    business_address = lead_data['address']

    prompt = f"""
    You are a business data enrichment assistant.
    Your goal is to find publicly available information about the following business using the Google Search tool.
    Do not invent information. If you cannot find specific information, state that clearly.

    Business Name: "{business_name}"
    Location Context (Address): "{business_address}"

    Using the search tool, please find the following specific details:
    1.  **Official Website:** Find the most likely official website URL for this specific business. If the provided website ('{lead_data.get('website', 'None provided')}') seems correct, confirm it. If not, provide the better one you found. If none found state "Not Found".
    2.  **LinkedIn Profile URL:** Find the URL of the official company LinkedIn page for "{business_name}" potentially near "{business_address}". If none is found, state "Not Found".
    3.  **Key Contacts:** Identify the names and titles (if available) of 1-3 key personnel (e.g., Owner, CEO, President, Manager) associated with "{business_name}". Prioritize publicly listed leadership roles. If none are found, state "Not Found".
    4.  **Brief Description:** Provide a concise (1-2 sentence) description of what the business does, based on information from its website, LinkedIn page, or other reliable search results. If none found, state "Not Found".

    Present the result ONLY as a valid JSON object with the exact keys: "enriched_website", "linkedin_url", "key_contacts", "description".
    For "key_contacts", provide a list of strings, like ["Name (Title)"]. If none found, use an empty list [].
    If a field cannot be found, use the string "Not Found" as its value in the JSON.

    Example Valid JSON output:
    {{
      "enriched_website": "https://www.examplebusiness.com",
      "linkedin_url": "https://www.linkedin.com/company/examplebusiness",
      "key_contacts": ["John Doe (CEO)", "Jane Smith (Manager)"],
      "description": "Example Business provides consulting services."
    }}
    Example Valid JSON output if nothing is found:
     {{
      "enriched_website": "Not Found",
      "linkedin_url": "Not Found",
      "key_contacts": [],
      "description": "Not Found"
    }}
    """

    print(f"  Enriching '{business_name}' with Gemini...")
    enriched_info = {
        'enriched_website': 'N/A', 'linkedin_url': 'N/A', 'key_contacts': [], 'description': 'N/A'
    } # Default values

    try:
        response = gemini_model.generate_content(
            prompt,
            tools=[search_tool],
            # Optional: Force tool use if needed, but usually implicit
            # tool_config={"google_search_retrieval": genai.types.ToolConfig(...)}
        )

        # --- Parse the response ---
        if response.parts:
            response_text = response.text
            print(f"    Gemini Raw Response Part for '{business_name}': {response_text[:200]}...")

            try:
                # Find JSON block more robustly
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    parsed_json = json.loads(json_str)

                    # Validate keys and update enriched_info safely
                    enriched_info['enriched_website'] = parsed_json.get('enriched_website', 'Parse Error')
                    enriched_info['linkedin_url'] = parsed_json.get('linkedin_url', 'Parse Error')
                    # Ensure key_contacts is a list
                    contacts = parsed_json.get('key_contacts', [])
                    enriched_info['key_contacts'] = contacts if isinstance(contacts, list) else []
                    enriched_info['description'] = parsed_json.get('description', 'Parse Error')
                    print(f"    Successfully parsed enriched data for '{business_name}'.")
                else:
                     print(f"    Warning: Could not find valid JSON block in response for '{business_name}'. Text: {response_text}")
                     enriched_info['description'] = 'Response Format Error'

            except json.JSONDecodeError as json_err:
                print(f"    Warning: JSON Decode Error for '{business_name}': {json_err}")
                print(f"    Response text: {response_text}")
                enriched_info['description'] = f'JSON Parse Error' # Keep it concise for table
            except Exception as parse_err:
                 print(f"    Warning: Error parsing Gemini response for '{business_name}': {parse_err}")
                 enriched_info['description'] = f'General Parse Error'

        else:
            print(f"    Warning: No response parts received from Gemini for '{business_name}'.")
            enriched_info['description'] = 'No response'
            if response.prompt_feedback.block_reason:
                 block_reason = str(response.prompt_feedback.block_reason)
                 print(f"    Response blocked. Reason: {block_reason}")
                 enriched_info['description'] = f'Blocked: {block_reason}'
            # Consider candidate finish reason too
            # if response.candidates and response.candidates[0].finish_reason:
            #    finish_reason = str(response.candidates[0].finish_reason)
            #    print(f"    Finish Reason: {finish_reason}")
            #    if enriched_info['description'] == 'No response': enriched_info['description'] = finish_reason

    except Exception as e:
        print(f"Error during Gemini enrichment API call for '{business_name}': {e}")
        enriched_info['description'] = f"API Error" # Concise error

    # Rate limiting delay
    time.sleep(1) # Adjust if hitting rate limits
    return enriched_info


# --- Example Usage (for testing) ---
if __name__ == '__main__':
    TEST_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not TEST_GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY environment variable not set.")
    else:
        print("Initializing Gemini Client...")
        model = get_gemini_client(TEST_GEMINI_API_KEY)
        print("Testing enrichment...")
        test_lead = {
            "name": "Philz Coffee",
            "address": "399 Golden Gate Ave, San Francisco, CA 94102",
            "website": "https://www.philzcoffee.com/"
        }
        enrichment_result = enrich_lead_data_with_gemini(model, test_lead)

        print("\n--- Enrichment Result ---")
        if enrichment_result:
            print(json.dumps(enrichment_result, indent=2))
        else:
            print("Enrichment failed (returned None - should not happen with current logic).")

        print("\nTesting enrichment for a less known entity...")
        test_lead_2 = {
            "name": "Bob's Donut & Pastry Shop",
            "address": "1621 Polk St, San Francisco, CA 94109",
            "website": "http://www.bobsdonutssf.com/"
        }
        enrichment_result_2 = enrich_lead_data_with_gemini(model, test_lead_2)
        print("\n--- Enrichment Result 2 ---")
        if enrichment_result_2:
             print(json.dumps(enrichment_result_2, indent=2))