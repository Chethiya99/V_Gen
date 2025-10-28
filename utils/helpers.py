import streamlit as st

def create_engagement_quiz():
    """Create an engaging quiz to collect user preferences"""
    st.subheader("Help us personalize your experience! 🎯")
    
    user_prefs = {}
    
    col1, col2 = st.columns(2)
    
    with col1:
        user_prefs['travel_companions'] = st.selectbox(
            "Who are you traveling with?",
            ["Solo", "Couple", "Family with kids", "Friends", "Business"]
        )
        
        user_prefs['interests'] = st.multiselect(
            "What are your main interests?",
            ["Adventure", "Relaxation", "Culture", "Food", "Photography", "Nature", "Shopping"]
        )
    
    with col2:
        user_prefs['pace'] = st.select_slider(
            "Preferred travel pace",
            options=["Very Relaxed", "Relaxed", "Moderate", "Busy", "Very Busy"]
        )
        
        user_prefs['special_requirements'] = st.text_area(
            "Any special requirements or preferences?",
            placeholder="e.g., wheelchair accessible, pet-friendly, vegetarian food..."
        )
    
    # Fun questions
    st.markdown("### Just for fun! 🎉")
    user_prefs['travel_personality'] = st.radio(
        "Which describes you best?",
        ["🏔️ Adventure Seeker", "🍷 Luxury Lover", "📷 Instagram Explorer", "🎨 Culture Enthusiast", "🍜 Foodie"]
    )
    
    return user_prefs

def display_itinerary(itinerary):
    """Display the generated itinerary in a beautiful format"""
    st.subheader("✨ Your Optimized Itinerary")
    
    if isinstance(itinerary, dict):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown(f"### 🗺️ Route: {itinerary['from']} → {itinerary['to']}")
            st.markdown(f"**Distance:** {itinerary['route_info'].get('distance', 'N/A')}")
            st.markdown(f"**Duration:** {itinerary['route_info'].get('duration', 'N/A')}")
            
            st.markdown("### 📝 Detailed Plan")
            if 'optimized_itinerary' in itinerary:
                st.write(itinerary['optimized_itinerary'])
        
        with col2:
            st.markdown("### 🌟 Points of Interest")
            if 'points_of_interest' in itinerary:
                for i, poi in enumerate(itinerary['points_of_interest'][:6]):
                    if isinstance(poi, dict):
                        name = poi.get('name', f'Point {i+1}')
                        rating = poi.get('rating', 'No rating')
                        st.write(f"**{i+1}. {name}**")
                        st.write(f"⭐ {rating}/5")
                        st.markdown("---")
    else:
        st.write(itinerary)

def validate_api_keys(google_api_key, gemini_api_key):
    """Validate that API keys are provided"""
    if not google_api_key or not gemini_api_key:
        st.error("🔑 Please enter both Google API Key and Gemini Pro API Key in the sidebar")
        return False
    return True
