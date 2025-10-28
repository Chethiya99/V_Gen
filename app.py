import streamlit as st
import os
from datetime import datetime
import tempfile
from dotenv import load_dotenv

from agents.trip_orchestrator import TripOrchestrator
from services.video_service import VideoGenerator
from utils.helpers import create_engagement_quiz, display_itinerary

# Load environment variables
load_dotenv()

def initialize_session_state():
    """Initialize session state variables"""
    if 'itinerary' not in st.session_state:
        st.session_state.itinerary = None
    if 'user_preferences' not in st.session_state:
        st.session_state.user_preferences = {}
    if 'video_script' not in st.session_state:
        st.session_state.video_script = None
    if 'video_generated' not in st.session_state:
        st.session_state.video_generated = False

def main():
    st.set_page_config(
        page_title="Travel Story Generator",
        page_icon="✈️",
        layout="wide"
    )
    
    st.title("🎬 AI Travel Story Generator")
    st.markdown("Transform your journey into a cinematic experience!")
    
    initialize_session_state()
    
    # Sidebar for API configuration
    with st.sidebar:
        st.header("Configuration")
        google_api_key = st.text_input("Google API Key", type="password", 
                                      help="Get it from https://console.cloud.google.com/")
        gemini_api_key = st.text_input("Gemini Pro API Key", type="password",
                                      help="Get it from https://aistudio.google.com/")
        
        if google_api_key:
            os.environ['GOOGLE_API_KEY'] = google_api_key
        if gemini_api_key:
            os.environ['GEMINI_API_KEY'] = gemini_api_key
    
    # Main app interface
    tab1, tab2, tab3 = st.tabs(["Plan Journey", "Personalize", "Generate Video"])
    
    with tab1:
        st.header("Plan Your Journey")
        
        col1, col2 = st.columns(2)
        
        with col1:
            from_location = st.text_input("From Location", "Matara")
            to_location = st.text_input("To Location", "Kataragama")
            preferred_stops = st.text_area("Preferred Stops or Interests", 
                                         "beach, temple, historical sites")
        
        with col2:
            travel_date = st.date_input("Travel Date", datetime.now())
            travel_style = st.selectbox("Travel Style", 
                                      ["Relaxed", "Adventure", "Cultural", "Family", "Romantic"])
            budget = st.select_slider("Budget Range", 
                                    ["Budget", "Moderate", "Luxury"])
        
        if st.button("Generate Itinerary", type="primary"):
            if not google_api_key or not gemini_api_key:
                st.error("Please enter both API keys in the sidebar")
                return
                
            with st.spinner("Creating your perfect itinerary..."):
                try:
                    orchestrator = TripOrchestrator(google_api_key, gemini_api_key)
                    
                    itinerary = orchestrator.create_itinerary(
                        from_location=from_location,
                        to_location=to_location,
                        preferences=preferred_stops,
                        travel_style=travel_style,
                        budget=budget
                    )
                    
                    st.session_state.itinerary = itinerary
                    st.success("Itinerary generated successfully!")
                    
                    # Display itinerary
                    display_itinerary(itinerary)
                    
                except Exception as e:
                    st.error(f"Error generating itinerary: {str(e)}")
    
    with tab2:
        st.header("Personalize Your Experience")
        
        if st.session_state.itinerary:
            st.success("Itinerary ready! Let's personalize your video.")
            
            # Engagement quiz
            user_prefs = create_engagement_quiz()
            st.session_state.user_preferences = user_prefs
            
            if st.button("Generate Video Script"):
                with st.spinner("Creating your cinematic script..."):
                    try:
                        orchestrator = TripOrchestrator(google_api_key, gemini_api_key)
                        script = orchestrator.generate_video_script(
                            st.session_state.itinerary, 
                            user_prefs
                        )
                        st.session_state.video_script = script
                        
                        st.subheader("Your Video Script")
                        st.write(script)
                        
                    except Exception as e:
                        st.error(f"Error generating script: {str(e)}")
        else:
            st.info("Please generate an itinerary first in the 'Plan Journey' tab.")
    
    with tab3:
        st.header("Generate Your Travel Story Video")
        
        if st.session_state.video_script:
            st.success("Script ready! Generate your video.")
            
            col1, col2 = st.columns(2)
            
            with col1:
                video_style = st.selectbox("Video Style", 
                                         ["Cinematic", "Documentary", "Vlog Style", "Professional"])
                voice_preference = st.selectbox("Voice Style", 
                                              ["Friendly", "Professional", "Enthusiastic", "Calm"])
            
            with col2:
                background_music = st.selectbox("Background Music", 
                                              ["Upbeat", "Relaxing", "Epic", "None"])
                video_duration = st.slider("Video Duration (seconds)", 30, 120, 60)
            
            if st.button("Generate Video", type="primary"):
                if not st.session_state.video_script:
                    st.error("Please generate a script first.")
                    return
                
                # Create progress bar and status
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                try:
                    status_text.text("Initializing video generation...")
                    progress_bar.progress(10)
                    
                    # Initialize video generator
                    video_gen = VideoGenerator(gemini_api_key)
                    
                    status_text.text("Generating video scenes...")
                    progress_bar.progress(30)
                    
                    # Generate video
                    video_path = video_gen.generate_travel_video(
                        script=st.session_state.video_script,
                        itinerary=st.session_state.itinerary,
                        style=video_style,
                        duration=video_duration
                    )
                    
                    progress_bar.progress(80)
                    status_text.text("Finalizing video...")
                    
                    # Display video
                    if video_path and os.path.exists(video_path):
                        st.session_state.video_generated = True
                        
                        # Display video
                        st.subheader("Your Travel Story Video")
                        with open(video_path, "rb") as video_file:
                            video_bytes = video_file.read()
                        
                        st.video(video_bytes)
                        
                        # Download button
                        st.download_button(
                            label="Download Video",
                            data=video_bytes,
                            file_name=f"travel_story_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
                            mime="video/mp4"
                        )
                        
                        progress_bar.progress(100)
                        status_text.text("Video generated successfully!")
                        
                    else:
                        st.error("Video generation failed. Please try again.")
                        
                except Exception as e:
                    st.error(f"Error generating video: {str(e)}")
                    progress_bar.progress(0)
                    status_text.text("")
        
        else:
            st.info("Please generate a video script in the 'Personalize' tab first.")

if __name__ == "__main__":
    main()
