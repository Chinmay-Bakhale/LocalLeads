import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from google_maps_client import get_business_leads
from gemini_client import enrich_leads

# Set page configuration
st.set_page_config(
    page_title="LocalLeads - AI-Enhanced Lead Generation",
    page_icon="🎯",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #4285F4;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #5F6368;
        margin-bottom: 2rem;
    }
    .stButton>button {
        background-color: #4285F4;
        color: white;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    .info-box {
        background-color: #E8F0FE;
        padding: 1rem;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# App header
st.markdown('<div class="main-header">LocalLeads</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI-Enhanced Lead Generation Tool</div>', unsafe_allow_html=True)

#sidebar for inputs
with st.sidebar:
    st.header("Search Parameters")
    
    # Location input (required)
    location = st.text_input("Location (required)", 
                            placeholder="e.g., New York, NY")
    
    # Radius input (required)
    radius = st.slider("Radius (km)", 
                      min_value=1, 
                      max_value=50, 
                      value=5,
                      help="Search radius in kilometers")
    
    # Business type input (optional)
    business_type = st.text_input("Business Type (optional)", 
                                placeholder="e.g., dentists, restaurants")
    
    # Advanced filters (collapsible)
    with st.expander("Advanced Filters"):
        min_rating = st.slider("Minimum Rating", 1.0, 5.0, 3.0, 0.5)
        min_reviews = st.number_input("Minimum Reviews", 0, 1000, 10)
    
    # Search button
    search_button = st.button("Generate Leads", use_container_width=True)

# Initialize session state to maintain data between reruns
if 'enriched_leads' not in st.session_state:
    st.session_state.enriched_leads = []
if 'location_data' not in st.session_state:
    st.session_state.location_data = None
if 'search_completed' not in st.session_state:
    st.session_state.search_completed = False

# Main content
if not search_button and not st.session_state.search_completed:

    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("""
    ### Welcome to LocalLeads!
    
    This tool helps you find and analyze business leads in your target area:
    
    1. Enter a location and search radius (required)
    2. Optionally specify a business type to narrow results
    3. Click "Generate Leads" to start the search
    4. View results on the map and in the data table
    5. Export leads to CSV for your CRM
    
    Get started by filling out the search parameters in the sidebar.
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display a sample map centered on a default location
    default_map = folium.Map(location=[40.7128, -74.0060], zoom_start=12)
    folium.Marker(
        [40.7128, -74.0060],
        popup="Default Location (New York)",
        tooltip="Default Location"
    ).add_to(default_map)
    folium_static(default_map)

elif search_button:
    # Validate required inputs
    if not location:
        st.error("Location is required. Please enter a location to search.")
    else:
        # Reset session state for new search
        st.session_state.enriched_leads = []
        st.session_state.location_data = None
        st.session_state.search_completed = False
        
        # Show progress for Step 1
        main_progress = st.progress(0)
        main_status = st.empty()
        main_status.text("Step 1/2: Searching for businesses in the specified area...")
        
        try:
            #Google Maps API client to get business leads
            leads, location_data = get_business_leads(
                location=location,
                radius=radius,
                business_type=business_type,
                max_results=8
            )
            
            # Store location data for map display
            st.session_state.location_data = location_data
            
            # Filter results
            if leads:
                leads = [lead for lead in leads if 
                        lead.get("rating", 0) >= min_rating and 
                        lead.get("reviews", 0) >= min_reviews]
            
            if not leads:
                main_progress.empty()
                main_status.empty()
                st.warning("No businesses found matching your criteria. Try expanding your search parameters.")
            else:
                # Update progress
                main_progress.progress(50)
                main_status.text("Step 2/2: Enriching lead data with AI insights...")
                
                #Gemini client to enrich leads
                enriched_leads = enrich_leads(leads)
                
                # Store enriched leads in session state
                st.session_state.enriched_leads = enriched_leads
                st.session_state.search_completed = True
                
                # Update progress
                main_progress.progress(100)
                main_status.empty()
                
                # Force page refresh
                st.rerun()
                
        except Exception as e:
            main_progress.empty()
            main_status.empty()
            st.error(f"An error occurred: {str(e)}")

#results if search has been completed
if st.session_state.search_completed and st.session_state.enriched_leads:
    enriched_leads = st.session_state.enriched_leads
    location_data = st.session_state.location_data
    
    # Success message
    st.success(f"Found and enriched {len(enriched_leads)} businesses within {radius}km" + 
              (f" for '{business_type}'" if business_type else ""))
    
    #DataFrame from leads
    df = pd.DataFrame(enriched_leads)
    
    #tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["Map View", "List View", "Detailed Profiles", "Analytics"])
    
    # Tab 1: Map View
    with tab1:
        st.subheader("Business Locations")
        
        # Create map centered on the search location
        m = folium.Map(location=[location_data["lat"], location_data["lng"]], zoom_start=12)
        
        # Add circle to represent search radius
        folium.Circle(
            location=[location_data["lat"], location_data["lng"]],
            radius=radius * 1000,  # Convert km to meters
            color="#4285F4",
            fill=True,
            fill_opacity=0.2
        ).add_to(m)
        
        # Add markers for each business
        for _, row in df.iterrows():
            # Create popup HTML with enriched data
            popup_html = f"""
            <div style="width: 200px">
                <h4>{row['name']}</h4>
                <p><b>Rating:</b> {row.get('rating', 'N/A')} ⭐ ({row.get('reviews', 'N/A')} reviews)</p>
                <p><b>Address:</b> {row.get('full_address', row.get('address', 'N/A'))}</p>
                <p><b>Phone:</b> {row.get('phone', 'N/A')}</p>
                <p><b>Lead Score:</b> {row.get('lead_score', 'N/A')}/100</p>
                <p><b>Company Size:</b> {row.get('company_size', 'N/A')}</p>
            </div>
            """
            
            # Add marker
            folium.Marker(
                location=[row['lat'], row['lng']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=row['name'],
                icon=folium.Icon(color="blue" if row.get('lead_score', 0) >= 80 else "green")
            ).add_to(m)
        
        #map
        folium_static(m)
    
    # Tab 2: List View - Enhanced with AI data
    with tab2:
        st.subheader("Business Listings")
        
        # Add filters
        col1, col2 = st.columns(2)
        with col1:
            sort_by = st.selectbox("Sort by", ["Lead Score", "Rating", "Reviews", "Name"])
        with col2:
            ascending = st.checkbox("Ascending order", False)
        
        # Sort the dataframe
        if sort_by == "Lead Score":
            df_sorted = df.sort_values(by="lead_score", ascending=ascending)
        elif sort_by == "Rating":
            df_sorted = df.sort_values(by="rating", ascending=ascending)
        elif sort_by == "Reviews":
            df_sorted = df.sort_values(by="reviews", ascending=ascending)
        else:
            df_sorted = df.sort_values(by="name", ascending=ascending)
        
        #data with enriched fields
        columns_to_display = ["name", "address", "phone", "rating", "reviews", "lead_score", "company_size"]

        existing_columns = [col for col in columns_to_display if col in df_sorted.columns]
        
        st.dataframe(
            df_sorted[existing_columns],
            use_container_width=True,
            hide_index=True
        )
        
        # Export options
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Export to CSV", use_container_width=True):
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"leads_{location.replace(' ', '_')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    # Tab 3: Detailed Profiles
    with tab3:
        st.subheader("Detailed Lead Profiles")
        
        #lead to view in detail
        selected_lead_name = st.selectbox(
            "Select a business to view detailed profile:",
            options=[lead["name"] for lead in enriched_leads]
        )
        
        selected_lead = next((lead for lead in enriched_leads if lead["name"] == selected_lead_name), None)
        
        if selected_lead:

            cols = st.columns([2, 1])
            
            with cols[0]:
                # Basic info
                st.markdown("### Basic Information")
                st.markdown(f"**Company:** {selected_lead['name']}")
                st.markdown(f"**Address:** {selected_lead.get('full_address', selected_lead.get('address', 'N/A'))}")
                st.markdown(f"**Phone:** {selected_lead.get('phone', 'N/A')}")
                st.markdown(f"**Website:** {selected_lead.get('website', 'N/A')}")
                st.markdown(f"**Rating:** {selected_lead.get('rating', 'N/A')} ⭐ ({selected_lead.get('reviews', 'N/A')} reviews)")
                
                # Company description from Gemini
                st.markdown("### Company Description")
                st.markdown(selected_lead.get('description', 'No description available.'))
                
                # Decision makers & pain points from Gemini
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("### Potential Decision Makers")
                    st.markdown(selected_lead.get('decision_makers', 'Not identified'))
                
                with col2:
                    st.markdown("### Business Pain Points")
                    st.markdown(selected_lead.get('pain_points', 'Not identified'))
                
                # Sales approach from Gemini
                st.markdown("### Recommended Approach")
                st.markdown(selected_lead.get('recommended_approach', 'No recommendations available.'))
                
                # Outreach template from Gemini
                st.markdown("### Personalized Outreach Template")
                st.text_area("Copy this template for your outreach", 
                             selected_lead.get('outreach_template', 'No template available.'),
                             height=150)
            
            with cols[1]:
                # Lead score
                st.markdown("### Lead Score")
                score = selected_lead.get('lead_score', 0)
                st.progress(score/100)
                st.markdown(f"**{score}/100** - " + 
                           ("High Value Lead" if score >= 80 else 
                            "Medium Value Lead" if score >= 60 else 
                            "Low Value Lead"))
                
                # Company size from Gemini
                st.markdown("### Company Size")
                st.markdown(f"**{selected_lead.get('company_size', 'Unknown')}**")
                
                # Business types
                st.markdown("### Business Types")
                types = selected_lead.get('types', [])
                if isinstance(types, list) and types:
                    for t in types:
                        st.markdown(f"- {t}")
                else:
                    st.markdown("No business type information available.")
    
    # Tab 4: Analytics
    with tab4:
        st.subheader("Lead Analytics")
        
        #simple analytics with enriched data
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Leads Found", len(df))
            if 'rating' in df.columns and len(df) > 0:
                st.metric("Average Rating", f"{df['rating'].mean():.1f} ⭐")
            
            # Company size distr.
            st.subheader("Company Size Distribution")
            if 'company_size' in df.columns:
                company_sizes = df['company_size'].value_counts().reset_index()
                company_sizes.columns = ['Size', 'Count']
                st.bar_chart(company_sizes.set_index('Size'))
                
        with col2:
            if 'lead_score' in df.columns:
                high_quality_leads = len(df[df['lead_score'] > 80])
                st.metric("High-Quality Leads (Score > 80)", high_quality_leads)
                st.metric("Average Lead Score", f"{df['lead_score'].mean():.1f}")
            
            # Rating distr.
            if 'rating' in df.columns and len(df) > 0:
                st.subheader("Rating Distribution")
                rating_counts = df['rating'].value_counts().sort_index().reset_index()
                rating_counts.columns = ['Rating', 'Count']
                st.bar_chart(rating_counts.set_index('Rating'))

st.markdown("---")
st.markdown("LocalLeads - AI-Enhanced Lead Generation Tool")
