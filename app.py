from flask import Flask, render_template, request, jsonify
import pickle
import pandas as pd
import datetime
import requests
import smtplib
from email.message import EmailMessage
import wconig as config

app = Flask(__name__)

# Load your newly trained model
model = pickle.load(open("heat_risk_model.pkl", "rb"))

# Major Indian cities with coordinates
cities = {
    "Delhi": [28.6139, 77.2090],
    "Mumbai": [19.0760, 72.8777],
    "Chennai": [13.0827, 80.2707],
    "Kolkata": [22.5726, 88.3639],
    "Bangalore": [12.9716, 77.5946],
    "Hyderabad": [17.3850, 78.4867],
    "Jaipur": [26.9124, 75.7873],
    "Ahmedabad": [23.0225, 72.5714]
}

# Simple in-memory cache for rolling averages
weather_history = {}

def fetch_weather(city, lat, lon):
    """Fetch current weather and AQI from OpenWeatherMap free APIs."""
    try:
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city},IN&appid={config.OPENWEATHER_API_KEY}&units=metric"
        weather_resp = requests.get(weather_url).json()
        if weather_resp.get("cod") != 200:
            print(f"Weather API error for {city}: {weather_resp.get('message')}")
            return None

        aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={config.OPENWEATHER_API_KEY}"
        aqi_resp = requests.get(aqi_url).json()
        aqi_value = aqi_resp["list"][0]["main"]["aqi"]  # 1..5
        aqi_mapped = aqi_value * 50  # map to your model's scale

        return {
            "temp_max": weather_resp["main"]["temp_max"],
            "temp_min": weather_resp["main"]["temp_min"],
            "humidity": weather_resp["main"]["humidity"],
            "wind": weather_resp["wind"]["speed"] * 3.6,
            "pressure": weather_resp["main"]["pressure"],
            "rainfall": weather_resp.get("rain", {}).get("1h", 0),
            "cloud_cover": weather_resp["clouds"]["all"],
            "aqi": aqi_mapped
        }
    except Exception as e:
        print(f"Exception in fetch_weather for {city}: {e}")
        return None

def compute_rolling_averages(city, today_temp):
    if city not in weather_history:
        weather_history[city] = []
    weather_history[city].append(today_temp)
    weather_history[city] = weather_history[city][-7:]
    avg_3day = sum(weather_history[city][-3:]) / len(weather_history[city][-3:]) if len(weather_history[city]) >= 3 else today_temp
    avg_7day = sum(weather_history[city]) / len(weather_history[city]) if weather_history[city] else today_temp
    return avg_3day, avg_7day

def send_alert(city, score):
    if not hasattr(config, 'EMAIL_ADDRESS') or not config.EMAIL_ADDRESS:
        return
    msg = EmailMessage()
    msg.set_content(f"⚠️ Extreme heat risk detected in {city}!\nRisk score: {score:.2f}")
    msg["Subject"] = "Heat Risk Alert"
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = config.ALERT_RECIPIENT
    try:
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"Alert sent for {city}")
    except Exception as e:
        print(f"Failed to send alert: {e}")

@app.route("/")
def home():
    return render_template("index.html", cities=cities)

@app.route("/predict_all", methods=["POST"])
def predict_all():
    try:
        data = request.json
        use_manual = data.get("use_manual", False)
        target_city = data.get("target_city")
        manual_temp = float(data.get("temp", 0)) if use_manual else None
        manual_humidity = float(data.get("humidity", 0)) if use_manual else None
        manual_wind = float(data.get("wind", 0)) if use_manual else None
        manual_pressure = float(data.get("pressure", 0)) if use_manual else None

        results = []
        today = datetime.datetime.now()

        for city, coords in cities.items():
            try:
                if use_manual and target_city and city == target_city:
                    weather = {
                        "temp_max": manual_temp,
                        "temp_min": manual_temp - 5,
                        "humidity": manual_humidity,
                        "wind": manual_wind,
                        "pressure": manual_pressure,
                        "rainfall": 0,
                        "cloud_cover": 40,
                        "aqi": 100
                    }
                else:
                    weather = fetch_weather(city, coords[0], coords[1])
                    if weather is None:
                        print(f"Skipping {city} due to weather fetch failure")
                        continue

                avg_3day, avg_7day = compute_rolling_averages(city, weather["temp_max"])
                humidity_3day = weather["humidity"]

                # Prepare DataFrame – must match your model's training columns exactly!
                input_df = pd.DataFrame([{
                    "Temperature_Max (°C)": weather["temp_max"],
                    "Temperature_Min (°C)": weather["temp_min"],
                    "Rainfall (mm)": weather["rainfall"],
                    "Wind_Speed (km/h)": weather["wind"],
                    "AQI": weather["aqi"],
                    "Pressure (hPa)": weather["pressure"],
                    "Cloud_Cover (%)": weather["cloud_cover"],
                    "Day": today.day,
                    "Month": today.month,
                    "DayOfWeek": today.weekday(),
                    "Temp_Avg_3day_rolling": avg_3day,
                    "Temp_Avg_7day_rolling": avg_7day,
                    "Humidity_3day_rolling": humidity_3day
                }])

                prediction = float(model.predict(input_df)[0])
                results.append({
                    "city": city,
                    "lat": coords[0],
                    "lon": coords[1],
                    "prediction": prediction
                })

                if not (use_manual and target_city and city == target_city) and hasattr(config, 'ALERT_THRESHOLD') and prediction > config.ALERT_THRESHOLD:
                    send_alert(city, prediction)

            except Exception as e:
                print(f"Error processing {city}: {e}")
                continue

        return jsonify(results)

    except Exception as e:
        print("Global error in /predict_all:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)