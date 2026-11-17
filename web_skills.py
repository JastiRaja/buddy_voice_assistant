import requests
import urllib.parse
import re
from config import load_user_settings
from converter import UnitConverter
from offline_encyclopedia import OfflineEncyclopedia

class WebSkills:
    def __init__(self, tts):
        self.tts = tts
        self.encyclopedia = OfflineEncyclopedia()

    def _is_offline(self) -> bool:
        settings = load_user_settings()
        return settings.get("strict_offline_mode", False)

    def get_weather(self, location_query: str = ""):
        """
        Fetches current weather. In strict offline mode, avoids network calls.
        """
        if self._is_offline():
            self.tts.speak("Air-gapped offline privacy mode is active. Outgoing network requests are blocked, sir.")
            return
        try:
            lat, lon, city_name = None, None, None

            if location_query and location_query.strip():
                # Geocode location query
                clean_loc = location_query.strip().title()
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_loc)}&count=1&language=en&format=json"
                resp = requests.get(geo_url, timeout=4).json()
                if resp.get("results"):
                    first = resp["results"][0]
                    lat = first["latitude"]
                    lon = first["longitude"]
                    city_name = first.get("name", clean_loc)
            
            # Fallback to IP geolocation if no city specified or geocoding failed
            if not lat or not lon:
                try:
                    ip_info = requests.get("https://ipapi.co/json/", timeout=4).json()
                    lat = ip_info.get("latitude")
                    lon = ip_info.get("longitude")
                    city_name = ip_info.get("city", "your area")
                except Exception:
                    lat, lon, city_name = 28.6139, 77.2090, "your current location"

            # Fetch live weather
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&temperature_unit=celsius&wind_speed_unit=kmh"
            w_resp = requests.get(weather_url, timeout=4).json()
            current = w_resp.get("current", {})

            temp = round(current.get("temperature_2m", 25))
            feels_like = round(current.get("apparent_temperature", temp))
            wind = round(current.get("wind_speed_10m", 10))
            code = current.get("weather_code", 0)

            # Weather code interpretation
            weather_conditions = {
                0: "Clear skies",
                1: "Mainly clear",
                2: "Partly cloudy",
                3: "Overcast",
                45: "Foggy",
                48: "Depositing rime fog",
                51: "Light drizzle",
                53: "Moderate drizzle",
                55: "Dense drizzle",
                61: "Slight rain",
                63: "Moderate rain",
                65: "Heavy rain",
                71: "Slight snow",
                73: "Moderate snow",
                75: "Heavy snow",
                80: "Slight rain showers",
                81: "Moderate rain showers",
                82: "Violent rain showers",
                95: "Thunderstorms",
            }
            condition = weather_conditions.get(code, "Clear")

            report = f"In {city_name}, it is currently {temp}°C with {condition}. Feels like {feels_like}°C with winds around {wind} km/h."
            self.tts.speak(report)
        except Exception as e:
            print(f"[Weather Error] {e}")
            self.tts.speak("I was unable to retrieve the weather report right now.")

    def search_wikipedia(self, query: str):
        """
        Fetches summary of a topic from offline encyclopedia, or online Wikipedia REST API fallback.
        """
        clean = query.strip()
        clean_topic = re.sub(r'^(who is|who was|what is|what was|tell me about|explain|search wikipedia for|lookup on wikipedia|wikipedia for|wikipedia)\s+', '', clean, flags=re.IGNORECASE).strip()
        clean_topic = re.sub(r'^[,\.\?!:\s]+|[,\.\?!:\s]+$', '', clean_topic).strip()

        if not clean_topic:
            self.tts.speak("What topic would you like me to look up, sir?")
            return

        # 1. Check Offline Knowledge Base & Kiwix
        offline_answer = self.encyclopedia.lookup(clean_topic)
        if offline_answer:
            self.tts.speak(offline_answer)
            return

        if self._is_offline():
            self.tts.speak(f"Offline encyclopedia has no cached entry for {clean_topic}, sir.")
            return

        try:
            headers = {'User-Agent': 'JarvisVoiceAssistant/2.0 (Windows)'}
            # 1. Try direct page summary
            slug = urllib.parse.quote(clean_topic.replace(' ', '_'))
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
            resp = requests.get(url, headers=headers, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "")
                if extract:
                    sentences = re.split(r'(?<=[.!?]) +', extract)
                    summary = " ".join(sentences[:2])
                    self.tts.speak(summary)
                    return

            # 2. If direct lookup failed, use opensearch to find closest matching article
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_topic)}&limit=1&format=json"
            s_resp = requests.get(search_url, headers=headers, timeout=5)
            if s_resp.status_code == 200:
                s_data = s_resp.json()
                if len(s_data) >= 2 and s_data[1]:
                    best_title = s_data[1][0]
                    best_slug = urllib.parse.quote(best_title.replace(' ', '_'))
                    best_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{best_slug}"
                    b_resp = requests.get(best_url, headers=headers, timeout=5)
                    if b_resp.status_code == 200:
                        b_data = b_resp.json()
                        extract = b_data.get("extract", "")
                        if extract:
                            sentences = re.split(r'(?<=[.!?]) +', extract)
                            summary = " ".join(sentences[:2])
                            self.tts.speak(summary)
                            return

            self.tts.speak(f"I couldn't find a direct summary for {clean_topic}, sir.")
        except Exception as e:
            print(f"[Wikipedia Error] {e}")
            self.tts.speak(f"Could not reach Wikipedia for {clean_topic}, sir.")

    def answer_question(self, query: str):
        """
        Answers general informational and conversational questions using local offline encyclopedia,
        or Gemini AI / Wikipedia when online.
        """
        clean = query.strip()
        if not clean:
            return

        # 1. Offline Knowledge Base & Encyclopedia First
        offline_answer = self.encyclopedia.lookup(clean)
        if offline_answer:
            self.tts.speak(offline_answer)
            return

        if self._is_offline():
            self.tts.speak(f"Air-gapped offline privacy mode is active. No local record found for that question, sir.")
            return

        settings = load_user_settings()
        api_key = settings.get("gemini_api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()

        # 1. If Gemini API key is configured, use Gemini Flash for intelligent natural voice response
        if api_key:
            for model_name in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-1.5-flash"]:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{
                            "parts": [{
                                "text": (
                                    "You are J.A.R.V.I.S., a witty and intelligent Windows voice assistant. "
                                    "Answer the following question clearly, politely, and concisely in 1 to 2 sentences suitable for text-to-speech read aloud: "
                                    f"{clean}"
                                )
                            }]
                        }],
                        "generationConfig": {
                            "temperature": 0.4,
                            "maxOutputTokens": 100
                        }
                    }
                    resp = requests.post(url, json=payload, timeout=8)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                reply = parts[0].get("text", "").strip()
                                clean_reply = re.sub(r'[*_#`]', '', reply).strip()
                                if clean_reply:
                                    self.tts.speak(clean_reply)
                                    return
                    elif resp.status_code in [404, 503, 429]:
                        continue
                    else:
                        break
                except Exception as e:
                    print(f"[Gemini API Notice] {e}")
                    continue

        # 2. If no Gemini API key or request failed, check if it's an informational topic for Wikipedia
        if any(clean.lower().startswith(q) for q in ["who is", "who was", "what is", "what was", "tell me about", "explain", "where is"]):
            self.search_wikipedia(clean)
            return

        # 3. Conversational fallback
        self.tts.speak(f"I am not entirely sure about that, sir. Would you like me to search Google for '{clean}'?")

    def get_news_headlines(self):
        """
        Fetches top world news headlines via RSS feed.
        """
        if self._is_offline():
            self.tts.speak("Air-gapped offline privacy mode is active. External news feed is blocked, sir.")
            return
        try:
            url = "https://feeds.bbci.co.uk/news/world/rss.xml"
            resp = requests.get(url, timeout=5)
            # Simple fast XML title extraction without heavy dependencies
            titles = re.findall(r'<item>[\s\S]*?<title><!\[CDATA\[(.*?)\]\]></title>', resp.text)
            if not titles:
                titles = re.findall(r'<item>[\s\S]*?<title>(.*?)</title>', resp.text)

            if titles:
                top_headlines = titles[:3]
                self.tts.speak("Here are the top world news headlines right now:")
                for i, title in enumerate(top_headlines, 1):
                    # Clean XML entities
                    clean_title = title.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
                    self.tts.speak(f"Headline {i}: {clean_title}")
            else:
                self.tts.speak("Unable to parse news headlines at the moment.")
        except Exception as e:
            print(f"[News Error] {e}")
            self.tts.speak("Could not fetch the latest news.")

    def calculate(self, math_expression: str):
        """
        Safely evaluates mathematical voice expressions and offline unit/currency conversions.
        """
        # 1. Offline Unit / Currency Conversion Check
        conv = UnitConverter.parse_and_convert(math_expression)
        if conv:
            self.tts.speak(conv)
            return

        try:
            import math
            expr = math_expression.lower().strip()
            # Handle roots
            expr = re.sub(r'\b(?:square\s+root\s+of|sqrt\s+of|root\s+of)\s*(\d+(?:\.\d+)?)', r'math.sqrt(\1)', expr)
            expr = re.sub(r'\b(?:cube\s+root\s+of)\s*(\d+(?:\.\d+)?)', r'(\1**(1/3))', expr)

            expr = expr.replace("times", "*").replace("multiplied by", "*").replace(" x ", " * ")
            expr = expr.replace("divided by", "/").replace("over", "/")
            expr = expr.replace("plus", "+").replace("add", "+")
            expr = expr.replace("minus", "-").replace("subtract", "-")
            expr = expr.replace("percent of", "* 0.01 *")
            expr = expr.replace("squared", "** 2").replace("cubed", "** 3")
            expr = expr.replace("to the power of", "**").replace("power", "**")

            # Extract valid math characters only
            clean_expr = re.sub(r'[^0-9+\-*/().a-z_]', '', expr)
            if not clean_expr or len(clean_expr) > 60:
                self.tts.speak("I couldn't understand the calculation.")
                return

            # Prevent astronomical power computation DOS
            if "**" in clean_expr:
                powers = re.findall(r'\*\*\s*(\d+)', clean_expr)
                for p in powers:
                    if int(p) > 100:
                        self.tts.speak("Exponent is too large to compute safely.")
                        return

            # Safe eval with restricted globals
            allowed_globals = {"__builtins__": None, "math": math}
            result = eval(clean_expr, allowed_globals, {})
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            elif isinstance(result, float):
                result = round(result, 4)

            self.tts.speak(f"The answer is {result}")
        except Exception:
            self.tts.speak("Sorry, I could not compute that calculation.")
