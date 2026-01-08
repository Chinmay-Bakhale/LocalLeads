# google_maps_client.py
import googlemaps
import time
import os
import pandas as pd
from datetime import datetime

# --- Client Initialization ---
def get_gmaps_client(api_key):
    """Initializes the Google Maps client."""
    if not api_key:
        raise ValueError("Google Maps API Key is required.")
    return googlemaps.Client(key=api_key)

# --- Geocoding Function ---
def geocode_address(client, address):
    """Geocodes an address string to latitude and longitude."""
    try:
        geocode_result = client.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            return None
    except Exception as e:
        print(f"Error during geocoding for '{address}': {e}")
        return None

# --- Nearby Search Function ---
def find_nearby_places(client, latitude, longitude, radius_meters, keyword=None, place_type=None):
    """
    Finds places near a specific location using Nearby Search.
    Handles pagination to retrieve more than the initial 20 results (up to 60).
    """
    all_results = []
    params = {
        'location': (latitude, longitude),
        'radius': radius_meters,
    }
    if keyword:
        params['keyword'] = keyword
    elif place_type:
         # Use 'type' if keyword is not provided. Note 'type' is more restrictive.
        params['type'] = place_type

    try:
        page_token = None
        # Google limits Nearby Search to 3 pages (max 60 results)
        for _ in range(3): # Limit requests to avoid excessive cost/long waits
            if page_token:
                params['page_token'] = page_token
                # IMPORTANT: Pause is required by Google TOS between page requests
                time.sleep(2)

            response = client.places_nearby(**params)
            all_results.extend(response.get('results', []))

            page_token = response.get('next_page_token')
            if not page_token:
                break # No more pages

        return all_results

    except Exception as e:
        print(f"Error during Nearby Search: {e}")
        return [] # Return empty list on error

# --- Place Details Function ---
def get_place_details(client, place_id):
    """Retrieves detailed information for a specific place ID."""
    # Define the fields you need to minimize costs
    fields = [
        'name', 'formatted_address', 'formatted_phone_number', 'website',
        'rating', 'user_ratings_total', 'place_id', 'geometry/location',
        'types', 'business_status', 'url' # Added URL for Google Maps link
    ]
    try:
        details = client.place(place_id=place_id, fields=fields)
        return details.get('result')
    except Exception as e:
        print(f"Error fetching details for place_id '{place_id}': {e}")
        return None

# --- Main Orchestration Function ---
def fetch_leads(api_key, location_query, radius_km, business_type=None, min_rating=0.0, min_reviews=0, limit=8): # Added limit parameter
    """
    Orchestrates the process: Geocode -> Nearby Search -> Get Details -> Filter -> Format -> Limit.
    Returns a list of up to 'limit' dictionaries, or an error string.
    """
    gmaps = get_gmaps_client(api_key)

    # 1. Geocode the location query
    print(f"Geocoding '{location_query}'...")
    coords = geocode_address(gmaps, location_query)
    if not coords:
        return f"Error: Could not geocode location '{location_query}'. Please try a more specific address."
    lat, lng = coords
    print(f"Geocoded to: Lat={lat}, Lng={lng}")

    # 2. Perform Nearby Search
    radius_meters = radius_km * 1000
    print(f"Searching nearby (Radius: {radius_meters}m, Keyword: '{business_type or 'Any'}')...")
    # Use business_type as keyword for broader matching potential
    nearby_results = find_nearby_places(gmaps, lat, lng, radius_meters, keyword=business_type)
    print(f"Found {len(nearby_results)} potential places nearby.")

    if not nearby_results:
        return [] # Return empty list if nothing found nearby

    # 3. Get Details for each place and filter
    potential_leads = []
    print("Fetching details and filtering...")
    total_nearby = len(nearby_results)
    for i, place in enumerate(nearby_results):
        place_id = place.get('place_id')
        if not place_id:
            continue

        # Simple progress indication (optional)
        if (i + 1) % 10 == 0:
             print(f"  Fetching detail {i+1}/{total_nearby}...")


        details = get_place_details(gmaps, place_id)
        if not details:
            continue # Skip if details couldn't be fetched

        # Apply primary filters
        rating = details.get('rating', 0.0)
        reviews = details.get('user_ratings_total', 0)

        if rating >= min_rating and reviews >= min_reviews and details.get('business_status') == 'OPERATIONAL':
            # Format the lead data
            lead_data = {
                "name": details.get('name', 'N/A'),
                "type": ', '.join(details.get('types', [])), # Join list of types
                "address": details.get('formatted_address', 'N/A'),
                "phone": details.get('formatted_phone_number', 'N/A'),
                "website": details.get('website', 'N/A'),
                "rating": rating,
                "reviews": reviews,
                "lat": details.get('geometry', {}).get('location', {}).get('lat', lat), # Fallback to search lat/lng if needed
                "lng": details.get('geometry', {}).get('location', {}).get('lng', lng),
                "place_id": place_id,
                "google_maps_url": details.get('url', 'N/A'), # Added Google Maps URL
                "status": details.get('business_status', 'N/A'),
                # Basic Lead Score Placeholder (replace with real scoring logic later)
                "lead_score": int(min(rating * 15 + min(reviews / 10, 35), 100)) # Weighted more towards rating
            }
            potential_leads.append(lead_data)
            # Small delay to be nice to the API
            time.sleep(0.05)

    print(f"Finished fetching details. Found {len(potential_leads)} leads matching initial criteria.")

    # 4. Sort and Limit Results
    # Sort by lead_score (descending) to get the "top" leads
    sorted_leads = sorted(potential_leads, key=lambda x: x['lead_score'], reverse=True)

    # Limit to the top 'limit' results
    final_leads = sorted_leads[:limit]
    print(f"Returning top {len(final_leads)} leads.")

    return final_leads

# --- Example Usage (for testing the script directly) ---
if __name__ == '__main__':
    TEST_GMAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY") # Make sure to set this environment variable
    if not TEST_GMAPS_API_KEY:
        print("Error: GOOGLE_MAPS_API_KEY environment variable not set.")
    else:
        print("Running test fetch...")
        test_location = "Museum of Modern Art, New York"
        test_radius = 1 # km
        test_type = "cafe"
        test_min_rating = 4.0
        test_min_reviews = 10
        test_limit = 5

        results = fetch_leads(
            TEST_GMAPS_API_KEY,
            test_location,
            test_radius,
            test_type,
            test_min_rating,
            test_min_reviews,
            limit=test_limit
        )

        if isinstance(results, str):
            print(results) # Print error message
        elif results:
            df = pd.DataFrame(results)
            print(f"\n--- Found {len(df)} Leads ---")
            # Print DF without truncation for testing
            with pd.option_context('display.max_rows', None, 'display.max_columns', None, 'display.width', 1000):
                print(df)
        else:
            print("No leads found matching the criteria.")