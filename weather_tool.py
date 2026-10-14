
import requests


def get_weather(city):
    """
    Get current weather for a city using Open-Meteo.
    """

    try:
        # Step 1: Find the city's coordinates.
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"

        geo_response = requests.get(
            geo_url,
            params={
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=15,
        )
        geo_response.raise_for_status()

        geo_data = geo_response.json()
        locations = geo_data.get("results", [])

        if not locations:
            return f"City not found: {city}"

        location = locations[0]
        latitude = location["latitude"]
        longitude = location["longitude"]
        city_name = location["name"]
        country = location.get("country", "Unknown")

        # Step 2: Get the current weather.
        weather_url = "https://api.open-meteo.com/v1/forecast"

        weather_response = requests.get(
            weather_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,relative_humidity_2m,"
                    "apparent_temperature,is_day,precipitation,"
                    "weather_code,wind_speed_10m"
                ),
                "timezone": "auto",
            },
            timeout=15,
        )
        weather_response.raise_for_status()

        weather_data = weather_response.json()
        current = weather_data.get("current")

        if not current:
            return "Current weather information is unavailable."

        # Translate WMO weather codes into descriptions.
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
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
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }

        code = current.get("weather_code")
        description = weather_codes.get(
            code,
            f"Weather code {code}",
        )

        return {
            "city": city_name,
            "country": country,
            "temperature_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "condition": description,
            "local_time": current.get("time"),
            "timezone": weather_data.get("timezone"),
            "source": "Open-Meteo",
        }

    except requests.RequestException as error:
        return f"Weather API request failed: {error}"

    except (ValueError, KeyError, TypeError) as error:
        return f"Could not process weather data: {error}"


if __name__ == "__main__":
    city = input("Enter city name: ").strip()
    print(get_weather(city))