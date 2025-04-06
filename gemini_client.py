# gemini_client.py
import google.generativeai as genai
import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
import time
from typing import Dict, List

def setup_gemini():
    """Set up Gemini API with the API key from Streamlit secrets"""
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return genai.GenerativeModel('gemini-2.0-flash')

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

def enrich_business_data(business: Dict) -> Dict:
    """Enrich business data using Gemini API and web search"""
    # Extract basic business info
    business_name = business.get("name", "")
    business_address = business.get("full_address", business.get("address", ""))
    
    # Get location from address
    location = business_address.split(",")[-2].strip() if len(business_address.split(",")) > 1 else ""
    
    # Default enriched values in case of errors
    default_enrichment = {
        "description": f"A business operating as {business_name} in {location}.",
        "company_size": "Small to Medium",
        "decision_makers": "Owner, General Manager",
        "pain_points": "Customer acquisition, operational efficiency",
        "recommended_approach": "Direct outreach highlighting value proposition",
        "outreach_template": f"Hello, I recently came across {business_name} and was impressed by your services. I'd like to connect to discuss how our solution might help streamline your operations. Would you be available for a brief call next week?"
    }
    
    try:
        # Setup Gemini client
        model = setup_gemini()
        
        # Search for additional info online
        search_results = search_business_info(business_name, location)
        
        # Format the prompt for Gemini
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
        1. A brief company description (2-3 sentences)
        2. Estimated company size (small, medium, large)
        3. Potential decision makers (typical roles that would make purchasing decisions)
        4. Company pain points (what challenges might they face?)
        5. Recommended approach for sales outreach
        6. Personalized outreach template (1 paragraph)
        
        Format your response as a JSON object with these fields: description, company_size, decision_makers, pain_points, recommended_approach, outreach_template
        Only return the JSON object, nothing else.
        """
        
        # Get response from Gemini
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Clean up the response text to handle markdown code blocks
        clean_text = response_text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0]
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0]
            
        # Remove newlines to make JSON parsing easier
        clean_text = clean_text.replace('\n', ' ').replace('\r', '')
        
        # Parse JSON
        enriched_data = json.loads(clean_text)
        
        # Add enriched data to the business
        business.update(enriched_data)
    except Exception as e:
        st.warning(f"An error occurred while enriching business data: {str(e)}")
    
    except Exception as e:
        # If any error occurs, use default enrichment values
        st.warning(f"Could not enrich data for {business_name}: {str(e)}")
        business.update(default_enrichment)
    
    return business

def enrich_leads(leads: List[Dict], max_leads: int = 8) -> List[Dict]:
    """Enrich multiple leads, limited to max_leads"""
    # Limit to top leads based on lead score
    top_leads = sorted(leads, key=lambda x: x.get("lead_score", 0), reverse=True)[:max_leads]
    
    # Create a list to hold enriched leads
    enriched_leads = []
    
    # Show progress bar in Streamlit
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Process each lead
    for i, lead in enumerate(top_leads):
        status_text.text(f"Enriching data for: {lead['name']} ({i+1}/{len(top_leads)})")
        progress_bar.progress((i+1)/len(top_leads))
        
        # Add a slight delay to avoid API rate limits
        time.sleep(1)
        
        # Enrich lead data
        enriched_lead = enrich_business_data(lead)
        enriched_leads.append(enriched_lead)
    
    status_text.empty()
    progress_bar.empty()
    
    return enriched_leads
