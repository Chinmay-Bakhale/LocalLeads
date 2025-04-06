# gemini_client.py - CLEANED AND FIXED VERSION

import google.generativeai as genai
import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
import time
from typing import Dict, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random
from typing import List

def setup_gemini():
    """Set up Gemini API with the API key from Streamlit secrets"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Error setting up Gemini API: {str(e)}")
        raise

'''
def search_business_info(business_name: str, location: str):
    """Search for business info using Google Custom Search JSON API."""
    search_query = f"{business_name} {location} company information"
    api_key = st.secrets["GOOGLE_API_KEY"]  # Store your API key in Streamlit secrets
    search_engine_id = st.secrets["SEARCH_ENGINE_ID"]  # Store your Search Engine ID in Streamlit secrets
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
    """Search for business info using SerpAPI (Google Results)"""
    search_query = f"{business_name} {location} company information"
    serpapi_key = st.secrets["SERPAPI_KEY"]

    try:
        params = {
            "engine": "google",
            "q": search_query,
            "api_key": serpapi_key,
            "num": 3,
        }

        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()

        results = []
        organic_results = data.get("organic_results", [])

        for result in organic_results[:3]:
            title = result.get("title", "No Title")
            snippet = result.get("snippet", "No Description")
            link = result.get("link", "No URL")

            results.append(f"Title: {title}\nSnippet: {snippet}\nURL: {link}")

        return results if results else ["No search results found."]

    except Exception as e:
        st.warning(f"SerpAPI search failed: {str(e)}. Using fallback method.")
        return [f"Search failed for {business_name} in {location}. No additional info available."]

def enrich_business_data(business: Dict) -> Dict:
    """Enrich business data using Gemini API and web search with improved reliability"""

    # Ensure basic values are initialized before try blocks
    business_name = business.get("name", "")
    business_address = business.get("full_address", business.get("address", ""))
    location = business_address.split(",")[-2].strip() if len(business_address.split(",")) > 1 else ""

    try:
        model = setup_gemini()
        search_results = search_business_info(business_name, location)

        prompt = f"""
        I need you to analyze this business and provide enriched data for lead generation purposes.

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
        2. Estimated company size (small, medium, large)
        3. Potential decision makers
        4. Company pain points
        5. Recommended approach for sales outreach
        6. Personalized outreach template

        Format as a JSON object with these fields:
        description, company_size, decision_makers, pain_points, recommended_approach, outreach_template
        Only return the JSON object, nothing else.
        """

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Try extracting JSON from markdown-wrapped responses
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

        try:
            enriched = enrich_business_data(lead)
            enriched_leads.append(enriched)
        except Exception as e:
            st.warning(f"Failed to enrich {lead.get('name', 'Unknown')}: {str(e)}.")
            lead.update({
                "description": f"Basic business in {lead.get('address', '')}",
                "company_size": "Unknown",
                "decision_makers": "Owner/Manager",
                "pain_points": "Unknown",
                "recommended_approach": "Exploratory contact",
                "outreach_template": f"Hello, I'm reaching out regarding {lead.get('name', 'Unknown')}..."
            })
            enriched_leads.append(lead)

    status_text.empty()
    progress_bar.empty()
    return enriched_leads
