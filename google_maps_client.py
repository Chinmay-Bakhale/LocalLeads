import requests
import streamlit as st
from typing import List, Dict, Tuple
import time

def geocode_location(location: str) -> Dict:
    """Convert a location string to latitude and longitude coordinates"""
    url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": location,
        "key": st.secrets["GOOGLE_MAPS_API_KEY"]
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise exception for non-200 responses
        
        data = response.json()
        if data["status"] == "OK" and data["results"]:
            location_data = data["results"][0]["geometry"]["location"]
            return {
                "lat": location_data["lat"],
                "lng": location_data["lng"],
                "formatted_address": data["results"][0]["formatted_address"]
            }
        elif data["status"] == "ZERO_RESULTS":
            raise ValueError(f"No location found for '{location}'")
        else:
            raise ValueError(f"Geocoding error: {data['status']}")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Error connecting to Google Maps API: {str(e)}")
    
    return {}

def search_businesses(lat: float, lng: float, radius: int, business_type: str = None, max_results: int = 8) -> List[Dict]:
    """Search for businesses near a location using Places API, limited to max_results"""
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius * 1000,  # Convert km to m
        "key": st.secrets["GOOGLE_MAPS_API_KEY"]
    }
    
    # If business type is provided, use it as a keyword
    if business_type:
        params["keyword"] = business_type 
    
    # Add ranking @ prminence
    params["rankby"] = "prominence"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if data["status"] == "OK":

            return data.get("results", [])[:max_results]
        elif data["status"] == "ZERO_RESULTS":
            return []
        else:
            raise ValueError(f"Places API error: {data['status']}")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Error connecting to Google Maps API: {str(e)}")
    
    return []

def get_place_details(place_id: str) -> Dict:
    """Get detailed information about a place using Place Details API"""
    url = f"https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,url,rating,user_ratings_total,opening_hours",
        "key": st.secrets["GOOGLE_MAPS_API_KEY"]
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if data["status"] == "OK":
            return data["result"]
        else:
            return {}
    except requests.exceptions.RequestException:
        # If we can't get details, just return empty dict
        return {}

def get_business_leads(location: str, radius: int, business_type: str = None, max_results: int = 8) -> Tuple[List[Dict], Dict]:
    """Main function to get business leads based on location and other parameters, limited to max_results"""
    #Geocode the location
    location_data = geocode_location(location)
    if not location_data:
        return [], None
    
    #Search for businesses
    businesses = search_businesses(
        location_data["lat"], 
        location_data["lng"], 
        radius, 
        business_type,
        max_results
    )
    
    #Process and enhance business data
    processed_businesses = []
    for business in businesses:
        # Extract basic info
        business_data = {
            "place_id": business.get("place_id", ""),
            "name": business.get("name", ""),
            "address": business.get("vicinity", ""),
            "lat": business.get("geometry", {}).get("location", {}).get("lat", 0),
            "lng": business.get("geometry", {}).get("location", {}).get("lng", 0),
            "rating": business.get("rating", 0),
            "reviews": business.get("user_ratings_total", 0),
            "types": business.get("types", []),
            "photos": business.get("photos", [])
        }
        
        # Get detailed information for the business
        details = get_place_details(business["place_id"])
        if details:
            business_data.update({
                "full_address": details.get("formatted_address", business_data["address"]),
                "phone": details.get("formatted_phone_number", ""),
                "website": details.get("website", ""),
                "opening_hours": details.get("opening_hours", {}).get("weekday_text", [])
            })
            
            #API rate limits
            time.sleep(0.5)
        
        # Calculate lead score (basic algorithm)
        lead_score = 50
        if business_data.get("rating", 0) >= 4.5:
            lead_score += 10
        if business_data.get("reviews", 0) >= 200:
            lead_score += 10
        if business_data.get("website"):
            lead_score += 10
        if business_data.get("phone"):
            lead_score += 10
        
        business_data["lead_score"] = lead_score
        processed_businesses.append(business_data)
    
    return processed_businesses, location_data
