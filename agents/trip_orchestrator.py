from langchain.agents import AgentType, initialize_agent
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage
import google.generativeai as genai

from agents.route_agent import RouteAgent
from agents.poi_agent import POIAgent

class TripOrchestrator:
    def __init__(self, google_api_key, gemini_api_key):
        self.google_api_key = google_api_key
        self.gemini_api_key = gemini_api_key
        
        # Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=gemini_api_key,
            temperature=0.7
        )
        
        # Initialize specialized agents
        self.route_agent = RouteAgent(google_api_key)
        self.poi_agent = POIAgent(google_api_key, gemini_api_key)
    
    def create_itinerary(self, from_location, to_location, preferences, travel_style, budget):
        """Create optimized itinerary using agentic workflow"""
        
        # Get route information
        route_info = self.route_agent.get_optimal_route(from_location, to_location)
        
        # Get points of interest along the route
        pois = self.poi_agent.find_points_of_interest(
            from_location, to_location, preferences, budget
        )
        
        # Optimize itinerary with LLM
        itinerary_prompt = f"""
        Create an optimized travel itinerary from {from_location} to {to_location}.
        
        Route Information: {route_info}
        Preferred Stops: {preferences}
        Travel Style: {travel_style}
        Budget: {budget}
        
        Points of Interest Found:
        {pois}
        
        Please create a logical itinerary that includes:
        1. Optimal stop order considering travel time
        2. Time allocation for each stop
        3. Meal break suggestions
        4. Key activities at each stop
        
        Format the response as a structured itinerary with time estimates.
        """
        
        response = self.llm.invoke(itinerary_prompt)
        
        itinerary = {
            'from': from_location,
            'to': to_location,
            'route_info': route_info,
            'points_of_interest': pois,
            'optimized_itinerary': response.content,
            'travel_style': travel_style,
            'budget': budget
        }
        
        return itinerary
    
    def generate_video_script(self, itinerary, user_preferences):
        """Generate cinematic video script based on itinerary and user preferences"""
        
        script_prompt = f"""
        Create a cinematic video script for a travel story based on this itinerary:
        
        Itinerary: {itinerary['optimized_itinerary']}
        Points of Interest: {itinerary['points_of_interest']}
        Travel Style: {itinerary['travel_style']}
        
        User Preferences:
        {user_preferences}
        
        Create an engaging 45-60 second video script with:
        1. Warm introduction
        2. Scene-by-scene descriptions with visual cues
        3. Emotional and engaging narration
        4. Smooth transitions between locations
        5. Memorable conclusion
        
        Format each scene with:
        [SCENE X]
        VISUAL: [Detailed description of visuals]
        NARRATION: "[Engaging narration text]"
        
        Make it feel personal and exciting!
        """
        
        response = self.llm.invoke(script_prompt)
        return response.content
