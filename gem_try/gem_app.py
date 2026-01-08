import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
import time
import os
import json # For formatting key contacts list potentially

# --- Import functions from client scripts ---
try:
    from gem_google_maps_client import fetch_leads, get_gmaps_client, geocode_address
except ImportError:
    st.error("Error importing 'google_maps_client.py'. Make sure the file exists.")
    st.stop()
try:
    # Use alias to avoid name clash if you have get_gemini_client elsewhere
    from gem_gemini_enrichment import get_gemini_client as get_gemini_enrich_client
    from gem_gemini_enrichment import enrich_lead_data_with_gemini
except ImportError:
    st.error("Error importing 'gemini_enrichment.py'. Make sure google-generativeai is installed.")
    st.stop()


# --- Page Configuration ---
st.set_page_config(
    page_title="LocalLeads - AI Enriched",
    page_icon="✨",
    layout="wide"
)

# --- Custom CSS (Keep your existing CSS or add new styles) ---
st.markdown("""
<style>
    /* Your CSS from previous version here */
    .main-header {font-size: 2.5rem; color: #1a73e8; margin-bottom: 0.5rem; font-weight: 600;}
    .sub-header {font-size: 1.3rem; color: #5f6368; margin-bottom: 1.5rem;}
    .stButton>button {background-color: #1a73e8; color: white; border-radius: 5px; padding: 0.5rem 1rem; font-weight: bold; border: none; transition: background-color 0.2s ease;}
    .stButton>button:hover {background-color: #1558b0;}
    .info-box {background-color: #e8f0fe; padding: 1.5rem; border-radius: 8px; border-left: 5px solid #1a73e8; margin-bottom: 1.5rem; color: #3c4043;}
    .stFoliumMap {min-height: 500px;}
    .stTabs [data-baseweb="tab-list"] {gap: 24px;}
    .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px;}
	.stTabs [aria-selected="true"] {background-color: #FFFFFF;}
    .api-key-info { font-size: 0.9rem; color: #5f6368; margin-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# --- Retrieve API Keys ---
try:
    GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    if not GOOGLE_MAPS_API_KEY or not GEMINI_API_KEY:
         st.error("⚠️ API Key(s) found in secrets, but one or both are empty. Please provide valid keys in .streamlit/secrets.toml")
         st.stop()
except KeyError as e:
    st.error(f"⚠️ API Key Missing! Add `{e.args[0]}` to `.streamlit/secrets.toml`.")
    st.stop()
except Exception as e:
    st.error(f"An error occurred reading secrets: {e}")
    st.stop()


# --- App Header ---
st.markdown('<div class="main-header">LocalLeads ✨</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Google Maps Search + Gemini AI Enrichment</div>', unsafe_allow_html=True)

# --- Sidebar for Inputs ---
with st.sidebar:
    st.header("Search Parameters")
    st.markdown(
        "<div class='api-key-info'>ℹ️ API Keys configured via secrets. API calls may incur costs.</div>",
        unsafe_allow_html=True
    )
    st.markdown("---") # Separator

    st.subheader("Search Criteria")
    location_input = st.text_input("📍 Location (required)",
                            placeholder="e.g., Palo Alto, CA",
                            help="Enter city, address, or landmark")

    radius_input = st.slider(" KRadius (km)",
                      min_value=1,
                      max_value=50, # Max radius for Nearby Search is 50km
                      value=5,
                      help="Search radius in kilometers (max 50km)")

    business_type_input = st.text_input("🏭 Business Keyword/Type (optional)",
                                placeholder="e.g., software company, coffee shop",
                                help="Use keywords or specific types. Leave blank for all.")

    # Advanced filters
    with st.expander("⚙️ Advanced Filters"):
        min_rating_input = st.slider("Minimum Rating ⭐", 0.0, 5.0, 4.0, 0.1, help="Minimum Google Maps rating (0 = any)")
        min_reviews_input = st.number_input("Minimum Reviews #️⃣", 0, 10000, 20, help="Minimum number of Google Maps reviews (0 = any)")

    st.markdown("---")
    # Toggle for AI Enrichment
    enrich_toggle = st.toggle("🤖 Enrich with Gemini AI", value=True, help="Use Gemini to find LinkedIn, contacts, descriptions etc. (Adds processing time & potential cost)")

    # Search button
    search_button = st.button("🔍 Generate Leads", use_container_width=True)

# --- Main Content Area ---

# Initialize session state for storing results
if 'final_leads_df' not in st.session_state:
    st.session_state.final_leads_df = pd.DataFrame()
if 'search_performed' not in st.session_state:
     st.session_state.search_performed = False


if not st.session_state.search_performed and not search_button:
    # Display welcome message only on first load or if search hasn't been done
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("""
    #### Welcome to LocalLeads! 👋

    Find and enrich business leads:

    1.  Ensure **API Keys** are set in `.streamlit/secrets.toml`.
    2.  Define **Location**, **Radius**, and optionally **Business Type**.
    3.  Set **Filters** for minimum rating and reviews.
    4.  Choose whether to **Enrich with Gemini AI** for extra details.
    5.  Click **Generate Leads**. Results will appear below.
    """)
    st.markdown('</div>', unsafe_allow_html=True)

    # Display a default map
    default_lat, default_lon = 37.7749, -122.4194 # San Francisco default
    st.subheader("Example Map View")
    try:
        # Try to use API key from secrets for initial geocode if location provided
        client = get_gmaps_client(GOOGLE_MAPS_API_KEY)
        coords = geocode_address(client, "San Francisco, CA") # Example default location
        if coords: default_lat, default_lon = coords
    except Exception: pass # Ignore errors here, just use hardcoded default

    default_map = folium.Map(location=[default_lat, default_lon], zoom_start=11)
    folium.Marker([default_lat, default_lon], popup="Default Location", tooltip="Default Location", icon=folium.Icon(color="gray")).add_to(default_map)
    folium_static(default_map, width=700, height=500)


# --- Execution Block (Runs when Search Button is Clicked) ---
if search_button:
    st.session_state.search_performed = True # Mark that search has been attempted
    st.session_state.final_leads_df = pd.DataFrame() # Clear previous results

    # --- Input Validation ---
    if not location_input:
        st.error("⚠️ Location is required. Please enter a location in the sidebar.")
        st.stop() # Use st.stop() to halt execution in Streamlit

    # --- Lead Generation (Google Maps) ---
    st.markdown("---")
    st.subheader(f"1. Searching Google Maps near '{location_input}'...")

    gmaps_leads_data = []
    error_message = None
    fetch_limit = 8 # Limit results for enrichment phase

    with st.spinner("🔄 Contacting Google Maps API..."):
        try:
            results = fetch_leads(
                api_key=GOOGLE_MAPS_API_KEY,
                location_query=location_input,
                radius_km=radius_input,
                business_type=business_type_input,
                min_rating=min_rating_input,
                min_reviews=min_reviews_input,
                limit=fetch_limit # Pass the limit
            )
            if isinstance(results, str): error_message = results
            else: gmaps_leads_data = results
        except Exception as e:
            st.error("An unexpected error occurred during Google Maps search:")
            st.exception(e)
            st.stop()

    if error_message:
        st.error(f"⚠️ Google Maps Search Error: {error_message}")
        st.stop()
    if not gmaps_leads_data:
         st.warning(f"ℹ️ No businesses found on Google Maps matching criteria for '{location_input}' within {radius_input}km.")
         st.stop()

    st.success(f"✅ Found {len(gmaps_leads_data)} initial leads from Google Maps (Top {fetch_limit}).")
    initial_leads_df = pd.DataFrame(gmaps_leads_data) # Store initial for fallback

    # --- AI Enrichment (Gemini) ---
    enriched_leads_data_list = [] # Holds the final list of dicts
    if enrich_toggle:
        st.subheader(f"2. Enriching Top {len(gmaps_leads_data)} Leads with Gemini AI...")
        # Place progress bar and status text within the main area
        progress_placeholder = st.empty()
        status_text = st.empty()

        try:
            gemini_client = get_gemini_enrich_client(GEMINI_API_KEY)
            status_text.text("🤖 Gemini client initialized.")
            # Display progress bar before loop
            enrich_progress = progress_placeholder.progress(0)

            total_to_enrich = len(gmaps_leads_data)
            for i, lead in enumerate(gmaps_leads_data):
                progress_value = (i + 1) / total_to_enrich
                status_text.text(f"🤖 Enriching lead {i+1}/{total_to_enrich}: {lead.get('name', 'Unknown Name')}...")

                # Call Gemini enrichment function
                enrichment_info = enrich_lead_data_with_gemini(gemini_client, lead)

                # Merge original lead data with enrichment results
                updated_lead = lead.copy() # Start with original data
                if enrichment_info:
                    # Update lead dict with enriched info, handling N/A or errors
                    updated_lead['enriched_website'] = enrichment_info.get('enriched_website', 'N/A')
                    updated_lead['linkedin_url'] = enrichment_info.get('linkedin_url', 'N/A')
                    updated_lead['key_contacts'] = enrichment_info.get('key_contacts', [])
                    updated_lead['description'] = enrichment_info.get('description', 'N/A')
                else:
                    # Assign default values if enrichment completely failed (shouldn't happen now)
                    updated_lead['enriched_website'] = 'Error'
                    updated_lead['linkedin_url'] = 'Error'
                    updated_lead['key_contacts'] = []
                    updated_lead['description'] = 'Enrichment Error'

                enriched_leads_data_list.append(updated_lead) # Append the updated lead dict
                enrich_progress.progress(progress_value)
                time.sleep(0.1) # Small UI delay

            status_text.success("✅ Gemini enrichment complete!")
            time.sleep(1) # Keep success message visible briefly
            progress_placeholder.empty() # Clear progress bar
            status_text.empty() # Clear status text

        except Exception as e:
            status_text.error(f"An error occurred during Gemini enrichment:")
            st.exception(e)
            # Continue with the data we have, enrichment might be partial
            if not enriched_leads_data_list: # If error happened before any were processed
                 st.warning("Falling back to Google Maps data due to enrichment error.")
                 enriched_leads_data_list = gmaps_leads_data # Fallback to Gmaps data list

    else:
        st.info("ℹ️ Gemini AI enrichment skipped.")
        enriched_leads_data_list = gmaps_leads_data # Use original data if enrichment is off


    # --- Store Final Results in Session State ---
    if not enriched_leads_data_list:
        st.error("Processing error: No lead data available after processing.")
        # Keep search_performed as True, but df remains empty
    else:
        st.session_state.final_leads_df = pd.DataFrame(enriched_leads_data_list)


# --- Display Results Block (Runs if search was performed and results exist) ---
if st.session_state.search_performed and not st.session_state.final_leads_df.empty:

    df_leads = st.session_state.final_leads_df # Use df from session state

    st.markdown("---")
    st.header("Results")
    tab1, tab2, tab3 = st.tabs(["🗺️ Map View", "📋 List View", "📊 Analytics"])

    # Determine map center (use first lead's coords)
    center_lat, center_lon = None, None
    # Ensure lat/lng columns exist and have valid data
    if 'lat' in df_leads.columns and 'lng' in df_leads.columns:
        first_valid_loc = df_leads[['lat', 'lng']].dropna()
        if not first_valid_loc.empty:
            center_lat = first_valid_loc.iloc[0]['lat']
            center_lon = first_valid_loc.iloc[0]['lng']

    # --- Tab 1: Map View ---
    with tab1:
        # Use the location_input from sidebar as title, even if geocoding failed slightly
        st.subheader(f"Lead Locations near '{location_input}'")
        if center_lat is not None and center_lon is not None:
            map_view = folium.Map(location=[center_lat, center_lon], zoom_start=13) # Adjust zoom dynamically?
            folium.Circle(
                location=[center_lat, center_lon],
                radius=radius_input * 1000,
                color="#1a73e8", weight=2, fill=True, fill_opacity=0.1,
                tooltip=f"{radius_input} km radius"
            ).add_to(map_view)

            # Add markers for each business
            for index, row in df_leads.iterrows():
                 score = row.get('lead_score', 50) # Default score if missing
                 icon_color = 'green' if score >= 85 else ('blue' if score >= 65 else 'lightgray')

                 # Create popup HTML including enriched data if available
                 popup_html = f"""
                 <div style="font-family: sans-serif; width: 250px; max-height: 200px; overflow-y: auto; font-size: 0.95em;">
                    <h4 style="margin-bottom: 5px; color: #1a73e8; font-size: 1.1em;">{row.get('name', 'N/A')}</h4>
                    <p style="margin: 2px 0;"><b>Rating:</b> {row.get('rating', 0):.1f}⭐ ({row.get('reviews', 0)} revs)</p>
                    <p style="margin: 2px 0;"><b>Status:</b> {row.get('status', 'N/A')}</p>
                    <p style="margin: 2px 0;"><b>Desc:</b> {row.get('description', 'N/A')}</p>
                    <p style="margin: 2px 0;"><b>Contacts:</b> {', '.join(row.get('key_contacts', [])) if row.get('key_contacts') else 'N/A'}</p>
                    <p style="margin: 2px 0;"><b>Website:</b> <a href='{row.get('website', '#')}' target='_blank'>Orig</a> | <a href='{row.get('enriched_website', '#')}' target='_blank'>Enr</a></p>
                    <p style="margin: 2px 0;"><b>LinkedIn:</b> {'<a href="' + str(row.get('linkedin_url','')) + '" target="_blank">Link</a>' if row.get('linkedin_url') and str(row.get('linkedin_url','')) not in ['N/A', 'Not Found'] else 'N/A'}</p>
                    <p style="margin: 2px 0;"><b>Address:</b> {row.get('address', 'N/A')}</p>
                 </div>
                 """
                 try:
                    # Ensure lat/lng are valid numbers before plotting
                    lat, lng = pd.to_numeric(row.get('lat'), errors='coerce'), pd.to_numeric(row.get('lng'), errors='coerce')
                    if pd.notna(lat) and pd.notna(lng):
                        folium.Marker(
                            location=[lat, lng],
                            popup=folium.Popup(popup_html, max_width=300),
                            tooltip=f"{row.get('name', 'N/A')}",
                            icon=folium.Icon(color=icon_color, icon='briefcase', prefix='fa') # FontAwesome icon
                        ).add_to(map_view)
                 except Exception as marker_err:
                    st.warning(f"Could not plot marker for {row.get('name', 'Unknown')}: {marker_err}", icon="⚠️")

            # Display the map
            folium_static(map_view, width=None, height=600) # Let Streamlit manage width
        else:
            st.warning("Could not determine center coordinates to display map.", icon="🗺️")


    # --- Tab 2: List View ---
    with tab2:
        st.subheader("Enriched Lead Listings")

        # Define sort columns based on available data in the final DataFrame
        sort_options = { k: v for k, v in {
            "Lead Score": "lead_score", "Rating": "rating", "Reviews": "reviews", "Name": "name"
            }.items() if v in df_leads.columns
        }

        df_sorted = df_leads # Default to unsorted if no valid sort columns
        if sort_options:
            col1, col2 = st.columns([0.7, 0.3])
            with col1: sort_by = st.selectbox("Sort by", options=list(sort_options.keys()), index=0, key="list_sort_by")
            with col2: ascending = st.checkbox("Ascending order", False, key="list_sort_asc")
            # Ensure the sort column exists before attempting to sort
            if sort_options[sort_by] in df_leads.columns:
                 df_sorted = df_leads.sort_values(by=sort_options[sort_by], ascending=ascending)
            else:
                 st.warning(f"Sort column '{sort_options[sort_by]}' not found.", icon="⚠️")
        else:
             st.info("No columns available for sorting.")


        # Define display columns including enriched ones
        display_columns = [
            "name", "description", "key_contacts", "linkedin_url",
            "website", "enriched_website", "phone", "address",
            "rating", "reviews", "lead_score", "status", "google_maps_url"
        ]
        # Filter to only include columns that actually exist in the DataFrame
        display_columns = [col for col in display_columns if col in df_sorted.columns]

        # Create a copy for display formatting to avoid SettingWithCopyWarning
        df_display = df_sorted.copy()

        # Format key contacts list for display (handle list or potential errors)
        def format_contacts(contacts_data):
            if isinstance(contacts_data, list) and contacts_data:
                return "; ".join(map(str, contacts_data)) # Convert elements to string just in case
            return "N/A"
        if 'key_contacts' in df_display.columns:
            df_display['key_contacts_display'] = df_display['key_contacts'].apply(format_contacts)
            # Swap display column if formatting applied
            if 'key_contacts' in display_columns:
                 idx = display_columns.index('key_contacts')
                 display_columns[idx] = 'key_contacts_display'


        st.dataframe(
            df_display[display_columns], # Use the potentially modified column list
            use_container_width=True, hide_index=True,
            column_config={
                 # Use .get on row in LinkColumn display functions if needed
                 "linkedin_url": st.column_config.LinkColumn("LinkedIn", display_text="View ↗", validate="^https?://.*linkedin.com/.*") if 'linkedin_url' in display_columns else None,
                 "website": st.column_config.LinkColumn("Website (Orig.)", display_text="Visit ↗") if 'website' in display_columns else None,
                 "enriched_website": st.column_config.LinkColumn("Website (Enr.)", display_text="Visit ↗") if 'enriched_website' in display_columns else None,
                 "google_maps_url": st.column_config.LinkColumn("Google Maps", display_text="View ↗") if 'google_maps_url' in display_columns else None,
                 "lead_score": st.column_config.ProgressColumn("Lead Score", help="Calculated potential score (0-100)", format="%d", min_value=0, max_value=100) if 'lead_score' in display_columns else None,
                 "rating": st.column_config.NumberColumn(format="%.1f ⭐") if 'rating' in display_columns else None,
                 "reviews": st.column_config.NumberColumn(format="%d revs") if 'reviews' in display_columns else None,
                 "description": st.column_config.Column("Description", width="medium", help="AI-generated description (if enabled)") if 'description' in display_columns else None,
                 "key_contacts_display": st.column_config.TextColumn("Key Contacts", help="AI-identified contacts (if enabled)") if 'key_contacts_display' in display_columns else None,
            }
        )

        # Export Option (includes enriched data)
        st.markdown("---")
        st.subheader("Export Enriched Leads")
        # Export the original df_sorted which has lists for contacts if needed
        csv_data = df_sorted.to_csv(index=False).encode('utf-8')
        safe_location_name = "".join(c if c.isalnum() else "_" for c in location_input)
        st.download_button(
            label="📥 Download Enriched Leads as CSV", data=csv_data,
            file_name=f"enriched_localleads_{safe_location_name}.csv", mime="text/csv",
            key='csv_enriched_download', help="Download the current list of leads, including AI enrichment.",
            use_container_width=True
        )

    # --- Tab 3: Analytics ---
    with tab3:
        st.subheader("Lead Insights & Analytics")
        if not df_leads.empty:
            col1, col2 = st.columns(2)

            # --- Basic Metrics (from Gmaps data) ---
            with col1:
                st.metric("Total Leads Processed", len(df_leads))
                # Check column exists and has non-NA values before calculating mean/int
                if 'rating' in df_leads.columns and df_leads['rating'].notna().any():
                    st.metric("Avg Rating", f"{df_leads['rating'].mean():.1f} ⭐")
                else: st.metric("Avg Rating", "N/A")
                if 'reviews' in df_leads.columns and df_leads['reviews'].notna().any():
                    st.metric("Avg Reviews", f"{int(df_leads['reviews'].mean())}")
                else: st.metric("Avg Reviews", "N/A")

            # --- Enriched Metrics (Check if enrichment was run/columns exist) ---
            with col2:
                 # Check if the enrichment columns exist before calculating metrics
                if 'linkedin_url' in df_leads.columns:
                    found_linkedin = df_leads['linkedin_url'].apply(lambda x: isinstance(x, str) and x.startswith('http')).sum()
                    st.metric("Leads w/ LinkedIn Found", found_linkedin)
                else: st.metric("Leads w/ LinkedIn Found", "N/A (Enrichment Off?)")

                if 'key_contacts' in df_leads.columns:
                    found_contacts = df_leads['key_contacts'].apply(lambda x: isinstance(x, list) and len(x) > 0).sum()
                    st.metric("Leads w/ Contacts Found", found_contacts)
                else: st.metric("Leads w/ Contacts Found", "N/A (Enrichment Off?)")

                if 'description' in df_leads.columns:
                    # More robust check for valid description
                    valid_desc_count = df_leads['description'].apply(
                        lambda x: isinstance(x, str) and x not in [
                            'N/A', 'Not Found', 'Parse Error', 'API Error', 'Blocked',
                             'Missing Input', 'No response', 'Response Format Error',
                            'Enrichment Error', 'General Parse Error'
                        ] and len(x.strip()) > 5 # Basic check for meaningful content
                    ).sum()
                    st.metric("Leads w/ Description Found", valid_desc_count)
                else: st.metric("Leads w/ Description Found", "N/A (Enrichment Off?)")


            # --- Charts ---
            st.markdown("---")
            # Rating distribution chart (check column exists)
            if 'rating' in df_leads.columns and df_leads['rating'].notna().any():
                st.subheader("Distribution by Rating")
                # Handle potential NaN values before cutting bins
                ratings_for_chart = df_leads['rating'].dropna()
                if not ratings_for_chart.empty:
                    bins = pd.cut(ratings_for_chart, bins=[0, 1, 2, 3, 4, 5], right=False, labels=["<1 ⭐", "1-2 ⭐", "2-3 ⭐", "3-4 ⭐", "4-5 ⭐"])
                    st.bar_chart(bins.value_counts().sort_index())
                else: st.info("No valid rating data for chart.")
            else: st.info("Rating data not available for chart.")

            # Lead Score distribution chart (check column exists)
            if 'lead_score' in df_leads.columns and df_leads['lead_score'].notna().any():
                st.subheader("Distribution by Lead Score")
                scores_for_chart = df_leads['lead_score'].dropna()
                if not scores_for_chart.empty:
                    score_bins = pd.cut(scores_for_chart, bins=[0, 50, 65, 85, 101], right=False, labels=["Low (0-49)", "Medium (50-64)", "Good (65-84)", "High (85-100)"])
                    st.bar_chart(score_bins.value_counts().sort_index())
                else: st.info("No valid lead score data for chart.")
            else: st.info("Lead score data not available for chart.")

        else:
            st.info("No data available to display analytics.")

elif st.session_state.search_performed and st.session_state.final_leads_df.empty:
     # Explicitly handle case where search was done but no results were stored
     st.warning("Search completed, but no leads were found or processed successfully based on the criteria.")


# --- Footer ---
st.markdown("---")
st.markdown("LocalLeads | AI Enriched | V0.5")