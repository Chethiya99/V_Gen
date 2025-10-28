import googlemaps
from datetime import datetime

class RouteAgent:
    def __init__(self, google_api_key):
        self.gmaps = googlemaps.Client(key=google_api_key)
    
    def get_optimal_route(self, origin, destination, mode='driving'):
        """Get optimal route using Google Maps Directions API"""
        try:
            # Get directions
            directions_result = self.gmaps.directions(
                origin,
                destination,
                mode=mode,
                departure_time=datetime.now()
            )
            
            if not directions_result:
                return {"error": "No route found"}
            
            route = directions_result[0]
            leg = route['legs'][0]
            
            route_info = {
                'distance': leg['distance']['text'],
                'duration': leg['duration']['text'],
                'start_address': leg['start_address'],
                'end_address': leg['end_address'],
                'steps': []
            }
            
            # Extract key steps and waypoints
            for step in leg['steps']:
                route_info['steps'].append({
                    'instruction': step['html_instructions'],
                    'distance': step['distance']['text'],
                    'duration': step['duration']['text'],
                    'location': step.get('end_location', {})
                })
            
            return route_info
            
        except Exception as e:
            return {"error": f"Route planning failed: {str(e)}"}
