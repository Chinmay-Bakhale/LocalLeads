import google.generativeai as genai
import streamlit as st
from bs4 import BeautifulSoup
import json, requests, time
from typing import Dict, List
from urllib.parse import urljoin

def setup_gemini():
    """Set up Gemini API with the API key from Streamlit secrets"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Error setting up Gemini API: {str(e)}")
        raise


def search_business_info(business_name: str, location: str):
    """Search for business info using Google Custom Search JSON API."""
    search_query = f"{business_name} {location} company information and owner CEO founder linkedin"
    api_key = st.secrets["GOOGLE_API_KEY"]
    search_engine_id = st.secrets["SEARCH_ENGINE_ID"]
    endpoint = "https://www.googleapis.com/customsearch/v1"

    params = {
        "q": search_query,
        "key": api_key,
        "cx": search_engine_id,
        "num": 2  # Number of search results to retrieve
    }

    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        search_results = response.json().get("items", [])

        results = []
        for result in search_results:
            results.append({
                'title': result.get('title'),
                'snippet': result.get('snippet'),
                'url': result.get('link')
            })

        formatted_results = [
            f"Title: {r['title']}\nSnippet: {r['snippet']}\nURL: {r['url']}" for r in results
        ]

        return formatted_results

    except requests.RequestException as e:
        st.warning(f"Google Custom Search failed: {str(e)}. Using fallback method.")
        return []
'''

def search_business_info(business_name: str, location: str) -> List[str]:
    """Search for business info using a simple web search approach"""
    search_query = f"{business_name} {location} company linkedin"
    url = f"https://duckduckgo.com/html/?q={search_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract search results
        results = []
        for result in soup.select('.result__body')[:3]:  # Get top 3 results
            title = result.select_one('.result__title')
            snippet = result.select_one('.result__snippet')
            link = result.select_one('.result__url')
            
            if title and snippet:
                results.append({
                    'title': title.get_text(strip=True),
                    'snippet': snippet.get_text(strip=True),
                    'url': link.get('href') if link else None
                })
        
        # Format results for Gemini
        formatted_results = []
        for r in results:
            formatted_results.append(f"Title: {r['title']}\nSnippet: {r['snippet']}\nURL: {r['url']}")
            
        return formatted_results
    
    except Exception as e:
        st.warning(f"Could not retrieve additional business information: {str(e)}")
        return []

'''

def enrich_business_data(business: Dict) -> Dict:
    """Enrich business data using Gemini API and web search with improved reliability"""

    business_name = business.get("name", "")
    business_address = business.get("full_address", business.get("address", ""))
    location = business_address.split(",")[-2].strip() if len(business_address.split(",")) > 1 else ""

    try:
        model = setup_gemini()
        search_results = search_business_info(business_name, location)

        prompt = f"""
        I need you to analyze this business and provide the owner's name and enriched data for lead generation purposes.

        Business Information:
        - Name: {business_name}
        - Address: {business_address}
        - Type: {', '.join(business.get('types', [])) if isinstance(business.get('types', []), list) else business.get('types', '')}
        - Rating: {business.get('rating', 'Not available')}
        - Reviews: {business.get('reviews', 'Not available')}
        - Website: {business.get('website', 'Not available')}
        - Phone: {business.get('phone', 'Not available')}

        Additional information found online:
        {"".join([f"--- Result {i+1} ---{result}" for i, result in enumerate(search_results)])}

        Based on this information, please provide:
        1. A brief company description
        2. Estimated company size (small, medium, large) and parent company if applicable.
        3. Most likely owner name(s), from the company website.
        4. Company pain points, and the latest news about the company
        5. Recommended approach for sales outreach
        6. Personalized outreach template

        Format as a JSON object with these fields:
        description, company_size, decision_makers, pain_points, recommended_approach, outreach_template
        Only return the JSON object, nothing else.
        """

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        #extracting JSON from responses
        try:
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_text = response_text.split("```")[1]
            else:
                json_text = response_text

            json_text = json_text.replace('\n', ' ').replace('\r', '').strip()

            try:
                enriched_data = json.loads(json_text)
            except json.JSONDecodeError:
                json_text = json_text.replace("'", "\"")
                enriched_data = json.loads(json_text)

            for key, value in enriched_data.items():
                business[key] = value

        except Exception as e:
            st.warning(f"Could not parse Gemini response: {str(e)}. Using default values.")
            business_types = ', '.join(business.get('types', [])) if isinstance(business.get('types', []), list) else business.get('types', '')
            business.update({
                "description": f"{business_name} is a {business_types} business located in {location}.",
                "company_size": "Small to Medium",
                "decision_makers": "Owner, General Manager, Operations Director",
                "pain_points": "Customer acquisition, operational efficiency, technology adoption",
                "recommended_approach": "Direct outreach highlighting specific value for their business type",
                "outreach_template": f"Hello, I recently came across {business_name} and was impressed by your services..."
            })

    except Exception as e:
        st.warning(f"Error enriching data: {str(e)}. Using basic information.")
        business.update({
            "description": f"{business_name} operates in {location}. Limited info available.",
            "company_size": "Unknown",
            "decision_makers": "Owner, General Manager",
            "pain_points": "Unknown",
            "recommended_approach": "Exploratory outreach",
            "outreach_template": f"Hello, I recently discovered {business_name}. I'd like to learn more about your business..."
        })

    return business



def enrich_leads(leads: List[Dict], max_leads: int = 8) -> List[Dict]:
    """Enrich multiple leads with improved reliability"""
    top_leads = sorted(leads, key=lambda x: x.get("lead_score", 0), reverse=True)[:max_leads]
    enriched_leads = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, lead in enumerate(top_leads):
        status_text.text(f"Enriching: {lead.get('name', 'Unknown')} ({i+1}/{len(top_leads)})")
        progress_bar.progress((i+1) / len(top_leads))

        time.sleep(1)

        enriched = enrich_business_data(lead)
        enriched_leads.append(enriched)

    status_text.empty()
    progress_bar.empty()
    return enriched_leads
