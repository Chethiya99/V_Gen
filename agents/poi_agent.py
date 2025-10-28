import googlemaps
from langchain_google_genai import ChatGoogleGenerativeAI

class POIAgent:
    def __init__(self, google_api_key, gemini_api_key):
        self.gmaps = googlemaps.Client(key=google_api_key)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=gemini_api_key,
            temperature=0.7
        )
    
    def find_points_of_interest(self, origin, destination, preferences, budget):
        """Find points of interest along the route"""
        try:
            # Get route to find waypoints
            directions = self.gmaps.directions(origin, destination)
            
            if not directions:
                return []
            
            # Extract route points for POI search
            route_bounds = self._get_route_bounds(directions[0])
            
            # Search for POIs based on preferences
            pois = []
            
            # Define search terms based on preferences
            search_terms = self._parse_preferences(preferences)
            
            for term in search_terms:
                places_result = self.gmaps.places_nearby(
                    location=route_bounds['center'],
                    radius=20000,  # 20km radius
                    type=term['type'] if 'type' in term else None,
                    keyword=term['keyword']
                )
                
                for place in places_result.get('results', [])[:5]:  # Top 5 results
                    place_details = self._get_place_details(place['place_id'])
                    if place_details and self._filter_by_budget(place_details, budget):
                        pois.append(place_details)
            
            # Rank and sort POIs
            ranked_pois = self._rank_pois(pois, preferences)
            
            return ranked_pois[:8]  # Return top 8 POIs
            
        except Exception as e:
            return [{"error": f"POI search failed: {str(e)}"}]
    
    def _parse_preferences(self, preferences):
        """Parse user preferences into search terms"""
        search_terms = []
        preference_lower = preferences.lower()
        
        if 'beach' in preference_lower:
            search_terms.append({'type': 'beach', 'keyword': 'beach'})
        if 'temple' in preference_lower or 'worship' in preference_lower:
            search_terms.append({'type': 'hindu_temple', 'keyword': 'temple'})
            search_terms.append({'type': 'church', 'keyword': 'church'})
            search_terms.append({'type': 'mosque', 'keyword': 'mosque'})
        if 'hotel' in preference_lower or 'stay' in preference_lower:
            search_terms.append({'type': 'lodging', 'keyword': 'hotel'})
        if 'food' in preference_lower or 'restaurant' in preference_lower:
            search_terms.append({'type': 'restaurant', 'keyword': 'local food'})
        if 'historical' in preference_lower:
            search_terms.append({'type': 'tourist_attraction', 'keyword': 'historical site'})
        
        return search_terms if search_terms else [{'type': 'tourist_attraction', 'keyword': 'attraction'}]
    
    def _get_route_bounds(self, route):
        """Extract route bounds for POI search"""
        # Simplified center point calculation
        start_lat = route['legs'][0]['start_location']['lat']
        start_lng = route['legs'][0]['start_location']['lng']
        end_lat = route['legs'][0]['end_location']['lat']
        end_lng = route['legs'][0]['end_location']['lng']
        
        return {
            'center': {
                'lat': (start_lat + end_lat) / 2,
                'lng': (start_lng + end_lng) / 2
            },
            'northeast': {'lat': max(start_lat, end_lat), 'lng': max(start_lng, end_lng)},
            'southwest': {'lat': min(start_lat, end_lat), 'lng': min(start_lng, end_lng)}
        }
    
    def _get_place_details(self, place_id):
        """Get detailed information about a place"""
        try:
            place_details = self.gmaps.place(place_id=place_id)
            return place_details.get('result', {})
        except:
            return {}
    
    def _filter_by_budget(self, place_details, budget):
        """Filter places based on budget"""
        price_level = place_details.get('price_level', 2)
        
        budget_map = {
            'Budget': [0, 1],
            'Moderate': [1, 2],
            'Luxury': [3, 4]
        }
        
        expected_range = budget_map.get(budget, [0, 4])
        return expected_range[0] <= price_level <= expected_range[1]
    
    def _rank_pois(self, pois, preferences):
        """Rank POIs based on relevance and ratings"""
        ranked_pois = []
        
        for poi in pois:
            score = 0
            
            # Rating based score
            rating = poi.get('rating', 0)
            score += rating * 20
            
            # Number of reviews based score
            reviews = poi.get('user_ratings_total', 0)
            score += min(reviews / 100, 50)  # Cap at 50
            
            # Preference matching
            poi_types = poi.get('types', [])
            preference_lower = preferences.lower()
            
            if any(keyword in preference_lower for keyword in ['beach', 'sea']) and 'beach' in str(poi_types):
                score += 100
            if 'temple' in preference_lower and any(t in poi_types for t in ['hindu_temple', 'church', 'mosque']):
                score += 100
            if 'historical' in preference_lower and 'tourist_attraction' in poi_types:
                score += 80
            
            ranked_pois.append((score, poi))
        
        # Sort by score descending
        ranked_pois.sort(key=lambda x: x[0], reverse=True)
        return [poi for score, poi in ranked_pois]
