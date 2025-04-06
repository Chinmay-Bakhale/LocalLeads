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

def setup_gemini():
    """Set up Gemini API with the API key from Streamlit secrets"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Error setting up Gemini API: {str(e)}")
        raise

def search_business_info(business_name: str, location: str) -> List[str]:
    """Search for business info with improved reliability and fallback mechanisms"""
    search_query = f"{business_name} {location} company information"
    
    try:
        session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        user_agents = [
            "Mozilla/5.0 ... Chrome/91.0",
            "Mozilla/5.0 ... Safari/605.1.15",
            "Mozilla/5.0 ... Firefox/90.0"
        ]
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        
        url = f"https://duckduckgo.com/html/?q={search_query}"
        response = session.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')

        results = []
        for result in soup.select('.result__body')[:3]:
            title = result.select_one('.result__title')
            snippet = result.select_one('.result__snippet')
            link = result.select_one('.result__url')
            
            if title and snippet:
                results.append({
                    'title': title.get_text(strip=True),
                    'snippet': snippet.get_text(strip=True),
                    'url': link.get('href') if link else None
                })

        formatted_results = [
            f"Title: {r['title']}\nSnippet: {r['snippet']}\nURL: {r['url']}" for r in results
        ]

        if formatted_results:
            return formatted_results

    except Exception as e:
        st.warning(f"DuckDuckGo search failed: {str(e)}. Using fallback method.")

    # Fallback logic
    try:
        business_type_string = f"{business_name.lower()} {location.lower()}"
        context = []

        if any(keyword in business_type_string for keyword in ["restaurant", "cafe", "bar", "grill"]):
            context.append("Title: Food Service Industry Overview\nSnippet: ...\nURL: example.com/restaurant-industry")
        elif any(keyword in business_type_string for keyword in ["hotel", "inn", "motel"]):
            context.append("Title: Hospitality Industry Trends\nSnippet: ...\nURL: example.com/hotel-industry")
        elif any(keyword in business_type_string for keyword in ["retail", "shop", "store"]):
            context.append("Title: Retail Business Challenges\nSnippet: ...\nURL: example.com/retail-business")
        elif any(keyword in business_type_string for keyword in ["salon", "spa", "beauty"]):
            context.append("Title: Beauty Industry Insights\nSnippet: ...\nURL: example.com/beauty-industry")
        elif any(keyword in business_type_string for keyword in ["dental", "dentist"]):
            context.append("Title: Dental Practice Management\nSnippet: ...\nURL: example.com/dental-practice")
        elif any(keyword in business_type_string for keyword in ["gym", "fitness"]):
            context.append("Title: Fitness Center Operations\nSnippet: ...\nURL: example.com/fitness-business")
        else:
            context.append(f"Title: Small Business Operations\nSnippet: ...\nURL: example.com/small-business")

        context.append(f"Title: Business Types in {location}\nSnippet: ...\nURL: example.com/local-business")
        return context

    except Exception as e:
        return [f"Title: Business Information\nSnippet: Limited info for {business_name} in {location}.\nURL: N/A"]

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
