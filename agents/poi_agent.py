# agents/poi_agent.py
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import googlemaps
from langchain_google_genai import ChatGoogleGenerativeAI

# Configure logger
logger = logging.getLogger("POIAgent")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


class POIAgent:
    """
    POIAgent - Find and summarize Points of Interest (POIs) along a route,
    filter by budget/preferences, rank results, and produce LLM-based summaries.

    Usage:
        agent = POIAgent(google_api_key="...", gemini_api_key="...")
        pois = agent.find_points_of_interest("Colombo, Sri Lanka", "Galle, Sri Lanka",
                                            preferences="beach, historical", budget="Moderate")
    """

    # Allowed place types per Google Places API
    VALID_PLACE_TYPES = {
        "restaurant", "lodging", "tourist_attraction", "museum",
        "church", "mosque", "hindu_temple", "beach", "park", "cafe",
        "bar", "zoo", "aquarium"
    }

    def __init__(self, google_api_key: str, gemini_api_key: Optional[str] = None, llm_temperature: float = 0.7):
        self.gmaps = googlemaps.Client(key=google_api_key)
        self.llm = None
        if gemini_api_key:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model="gemini-pro",
                    google_api_key=gemini_api_key,
                    temperature=llm_temperature
                )
            except Exception as e:
                logger.warning("Failed to initialize Gemini LLM client: %s", e)
                self.llm = None

    # ---------------------
    # Public API
    # ---------------------
    def find_points_of_interest(
        self,
        origin: str,
        destination: str,
        preferences: str = "",
        budget: str = "Moderate",
        max_pois: int = 8,
        radius_meters: int = 20000
    ) -> List[Dict[str, Any]]:
        """
        Find POIs between origin and destination.

        Returns a list of POI dicts (with optional LLM summary under key 'summary').
        """
        try:
            logger.info("Requesting directions from %s to %s", origin, destination)
            directions = self.gmaps.directions(origin, destination)

            if not directions:
                logger.info("No directions returned for route.")
                return []

            route_bounds = self._get_route_bounds(directions[0])

            if not route_bounds:
                logger.info("Unable to determine route bounds.")
                return []

            search_terms = self._parse_preferences(preferences)
            logger.info("Search terms derived: %s", search_terms)

            # accumulate POIs
            pois: List[Dict[str, Any]] = []
            for term in search_terms:
                sanitized_type = term.get("type")
                if sanitized_type and sanitized_type not in self.VALID_PLACE_TYPES:
                    sanitized_type = None

                # first page fetch and handle pagination up to 2 extra pages (Google's next_page_token)
                page_token = None
                pages_fetched = 0
                while pages_fetched < 3:
                    try:
                        params = {
                            "location": (route_bounds["center"]["lat"], route_bounds["center"]["lng"]),
                            "radius": radius_meters,
                            "type": sanitized_type,
                            "keyword": term.get("keyword")
                        }
                        # remove None values
                        params = {k: v for k, v in params.items() if v is not None}

                        if page_token:
                            places_result = self.gmaps.places_nearby(page_token=page_token)
                        else:
                            places_result = self.gmaps.places_nearby(**params)
                    except Exception as e:
                        logger.warning("places_nearby failed for term %s: %s", term, e)
                        break

                    results = places_result.get("results", [])
                    logger.info("Found %d places (page %d) for term %s", len(results), pages_fetched + 1, term)
                    for place in results:
                        pois.append(place)

                    page_token = places_result.get("next_page_token")
                    if not page_token:
                        break
                    # next_page_token requires a short delay before it becomes valid
                    time.sleep(2)
                    pages_fetched += 1

            if not pois:
                logger.info("No POIs found for any preferences.")
                return []

            # Deduplicate by place_id
            unique = {}
            for p in pois:
                pid = p.get("place_id")
                if pid and pid not in unique:
                    unique[pid] = p
            pois_list = list(unique.values())

            # Fetch place details concurrently
            logger.info("Fetching details for %d unique places", len(pois_list))
            detailed_pois = self._fetch_place_details_concurrent([p["place_id"] for p in pois_list])

            # Filter by budget and compute ranking
            filtered = [d for d in detailed_pois if self._filter_by_budget(d, budget)]
            logger.info("%d places remain after budget filter (%s)", len(filtered), budget)

            ranked = self._rank_pois(filtered, preferences)

            # Limit results
            top_pois = ranked[:max_pois]

            # Use LLM to generate human-friendly summaries for top POIs if available
            if self.llm:
                logger.info("Generating LLM summaries for top %d POIs", len(top_pois))
                summaries = self._summarize_pois_with_llm(top_pois, preferences)
                # merge summaries into POI entries
                for poi, summary in zip(top_pois, summaries):
                    if summary:
                        poi["summary"] = summary

            return top_pois

        except Exception as e:
            logger.exception("POI search failed: %s", e)
            return [{"error": f"POI search failed: {str(e)}"}]

    # ---------------------
    # Helper methods
    # ---------------------
    def _parse_preferences(self, preferences: str) -> List[Dict[str, str]]:
        """
        Turn a user-provided preference string into a list of search term dicts.
        """
        preference_lower = (preferences or "").lower()
        search_terms = []

        if "beach" in preference_lower or "sea" in preference_lower:
            search_terms.append({"type": "beach", "keyword": "beach"})
        if "temple" in preference_lower or "worship" in preference_lower:
            # add specific types for religious sites
            search_terms.append({"type": "hindu_temple", "keyword": "temple"})
            search_terms.append({"type": "church", "keyword": "church"})
            search_terms.append({"type": "mosque", "keyword": "mosque"})
        if "hotel" in preference_lower or "stay" in preference_lower or "lodging" in preference_lower:
            search_terms.append({"type": "lodging", "keyword": "hotel"})
        if "food" in preference_lower or "restaurant" in preference_lower or "local food" in preference_lower:
            search_terms.append({"type": "restaurant", "keyword": "local food"})
        if "historical" in preference_lower or "history" in preference_lower:
            search_terms.append({"type": "tourist_attraction", "keyword": "historical site"})
        if "museum" in preference_lower:
            search_terms.append({"type": "museum", "keyword": "museum"})
        if "park" in preference_lower:
            search_terms.append({"type": "park", "keyword": "park"})

        # fallback
        if not search_terms:
            search_terms.append({"type": "tourist_attraction", "keyword": "attraction"})

        # ensure uniqueness while preserving order
        seen = set()
        unique_terms = []
        for t in search_terms:
            key = (t.get("type"), t.get("keyword"))
            if key not in seen:
                seen.add(key)
                unique_terms.append(t)
        return unique_terms

    def _get_route_bounds(self, route: Dict[str, Any]) -> Optional[Dict[str, Dict[str, float]]]:
        """
        Calculate center, northeast, and southwest bounds for the route.
        Uses all legs (robust for multi-leg directions).
        """
        legs = route.get("legs", [])
        if not legs:
            return None

        latitudes = []
        longitudes = []
        for leg in legs:
            # accumulate both start and end
            start = leg.get("start_location")
            end = leg.get("end_location")
            if start and "lat" in start and "lng" in start:
                latitudes.append(start["lat"])
                longitudes.append(start["lng"])
            if end and "lat" in end and "lng" in end:
                latitudes.append(end["lat"])
                longitudes.append(end["lng"])

        if not latitudes:
            return None

        center = {"lat": sum(latitudes) / len(latitudes), "lng": sum(longitudes) / len(longitudes)}
        northeast = {"lat": max(latitudes), "lng": max(longitudes)}
        southwest = {"lat": min(latitudes), "lng": min(longitudes)}
        return {"center": center, "northeast": northeast, "southwest": southwest}

    def _get_place_details(self, place_id: str) -> Dict[str, Any]:
        """
        Wrap googlemaps.place to retrieve full place details.
        """
        try:
            detail = self.gmaps.place(place_id=place_id)
            return detail.get("result", {}) or {}
        except Exception as e:
            logger.warning("Failed to fetch details for %s: %s", place_id, e)
            return {}

    def _fetch_place_details_concurrent(self, place_ids: List[str], max_workers: int = 8) -> List[Dict[str, Any]]:
        """
        Fetch place details concurrently to speed up network-bound calls.
        """
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(place_ids) or 1)) as exe:
            futures = {exe.submit(self._get_place_details, pid): pid for pid in place_ids}
            for fut in as_completed(futures):
                pid = futures[fut]
                try:
                    res = fut.result()
                    if res:
                        results.append(res)
                except Exception as e:
                    logger.warning("Place details worker failed for %s: %s", pid, e)
        return results

    def _filter_by_budget(self, place_details: Dict[str, Any], budget: str) -> bool:
        """
        Filter place by budget level.
        Google price_level values: 0..4 (0: free, 4: very expensive).
        Budget classification uses non-overlapping mapping.
        """
        # default price_level if missing: assume moderate (2)
        price_level = place_details.get("price_level")
        if price_level is None:
            # some POIs (parks/beaches) may not have price_level, keep them
            return True

        budget_map = {
            "Budget": [0, 1],
            "Moderate": [2],
            "Luxury": [3, 4]
        }
        expected = budget_map.get(budget, [0, 1, 2, 3, 4])
        try:
            return int(price_level) in expected
        except Exception:
            return True

    def _rank_pois(self, pois: List[Dict[str, Any]], preferences: str) -> List[Dict[str, Any]]:
        """
        Rank POIs by a composite score of rating, reviews, and preference relevance.
        Returns sorted list (best first).
        """
        scored = []
        preference_lower = (preferences or "").lower()

        for poi in pois:
            score = 0.0
            rating = poi.get("rating", 0) or 0
            reviews = poi.get("user_ratings_total", 0) or 0
            poi_types = poi.get("types", []) or []

            # Rating contribution: max ~75 (5*15)
            score += float(rating) * 15.0

            # Reviews contribution: scaled and capped at 25
            score += min(reviews / 200.0 * 25.0, 25.0)

            # Preference matching bonus
            if any(k in preference_lower for k in ["beach", "sea"]) and "beach" in poi_types:
                score += 80
            if "temple" in preference_lower and any(t in poi_types for t in ["hindu_temple", "church", "mosque"]):
                score += 80
            if "historical" in preference_lower and "tourist_attraction" in poi_types:
                score += 60
            # small bonus for lodging/restaurant if requested
            if ("hotel" in preference_lower or "stay" in preference_lower) and "lodging" in poi_types:
                score += 30
            if ("food" in preference_lower or "restaurant" in preference_lower) and "restaurant" in poi_types:
                score += 30

            scored.append((score, poi))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    # ---------------------
    # LLM-related methods
    # ---------------------
    def _call_llm(self, prompt: str, max_tokens: int = 150) -> Optional[str]:
        """
        Helper wrapper to call the Gemini LLM client using common call patterns.
        Tries several common LangChain-style interfaces and returns text or None.
        """
        if not self.llm:
            return None

        try:
            # 1) Try .generate() (LangChain LLM-like)
            if hasattr(self.llm, "generate"):
                try:
                    out = self.llm.generate([{"role": "user", "content": prompt}])
                    # out object shapes vary — attempt to extract text safely
                    if hasattr(out, "generations"):
                        # langchain -> out.generations -> list(list(Generation))
                        gens = out.generations
                        if gens and gens[0] and hasattr(gens[0][0], "text"):
                            return gens[0][0].text
                    if isinstance(out, dict) and "text" in out:
                        return out["text"]
                except Exception:
                    pass

            # 2) Try callable interface (e.g., llm(prompt))
            if callable(self.llm):
                try:
                    resp = self.llm(prompt)
                    if isinstance(resp, str):
                        return resp
                    if hasattr(resp, "content"):
                        return getattr(resp, "content")
                    if isinstance(resp, dict) and "content" in resp:
                        return resp["content"]
                except Exception:
                    pass

            # 3) Try .predict() or .invoke()
            for method_name in ("predict", "invoke"):
                method = getattr(self.llm, method_name, None)
                if callable(method):
                    try:
                        r = method(prompt)
                        if isinstance(r, str):
                            return r
                        if hasattr(r, "content"):
                            return getattr(r, "content")
                    except Exception:
                        continue

            logger.debug("LLM call succeeded no recognized response shape.")
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
        return None

    def _summarize_pois_with_llm(self, pois: List[Dict[str, Any]], preferences: str) -> List[Optional[str]]:
        """
        Ask the LLM to write short travel-friendly summaries for each POI.
        Returns list of summaries aligned with the POI list.
        """
        summaries: List[Optional[str]] = []
        for poi in pois:
            name = poi.get("name", "Unknown place")
            rating = poi.get("rating", "N/A")
            address = poi.get("formatted_address", poi.get("vicinity", ""))
            snippet = poi.get("opening_hours", {}).get("weekday_text", [])
            # Craft a compact prompt for Gemini
            prompt = (
                f"You are a friendly travel assistant. Write a single concise (1-2 sentence) "
                f"description for '{name}' (address: {address}). Rating: {rating}. "
                f"Make it appealing for a traveler who likes: {preferences}. "
                f"If there are any unique tips (e.g., best time to visit), add one short tip."
            )
            summary = self._call_llm(prompt)
            if summary:
                # Clean up whitespace
                summary = " ".join(summary.split())
            summaries.append(summary)
            # small delay to avoid hitting rate limits aggressively
            time.sleep(0.2)
        return summaries
