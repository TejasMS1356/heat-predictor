document.addEventListener("DOMContentLoaded", function() {
    var map = L.map('map').setView([22.9734, 78.6569], 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    var markerLayer = L.layerGroup().addTo(map);

    // Load real-time data on page load
    window.addEventListener('load', function() {
        // Ensure manual mode is off
        document.getElementById('useManual').checked = false;
        predictAll();
    });

    window.predictAll = function() {
        const citySelect = document.getElementById("citySelect");
        const targetCity = citySelect.value;
        const temp = document.getElementById("temp").value;
        const humidity = document.getElementById("humidity").value;
        const wind = document.getElementById("wind").value;
        const pressure = document.getElementById("pressure").value;
        const useManual = document.getElementById("useManual").checked;

        // If manual mode is on, a city must be selected
        if (useManual && !targetCity) {
            alert("Please select a city for manual input.");
            return;
        }

        const payload = {
            use_manual: useManual,
            target_city: targetCity || null,
            temp: temp,
            humidity: humidity,
            wind: wind,
            pressure: pressure
        };

        fetch("/predict_all", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            })
            .then(res => {
                if (!res.ok) {
                    throw new Error("Server error: " + res.status);
                }
                return res.json();
            })
            .then(data => {
                markerLayer.clearLayers();
                let hottestCity = "";
                let highestValue = -1;

                data.forEach(city => {
                    let color = "green";
                    let level = "Low";
                    if (city.prediction > 0.8) {
                        color = "darkred";
                        level = "Extreme";
                    } else if (city.prediction > 0.6) {
                        color = "red";
                        level = "High";
                    } else if (city.prediction > 0.4) {
                        color = "orange";
                        level = "Moderate";
                    }

                    if (city.prediction > highestValue) {
                        highestValue = city.prediction;
                        hottestCity = city.city;
                    }

                    L.circle([city.lat, city.lon], {
                            color: color,
                            fillColor: color,
                            fillOpacity: 0.6,
                            radius: 60000
                        })
                        .addTo(markerLayer)
                        .bindPopup(
                            "<b>" + city.city + "</b><br>" +
                            "Heat Risk Level: " + level + "<br>" +
                            "Prediction Score: " + city.prediction.toFixed(2)
                        );
                });

                document.getElementById("statusBox").innerHTML =
                    "🔥 Hottest City Right Now: <span style='color:red'>" +
                    hottestCity +
                    "</span> (Risk Score: " + highestValue.toFixed(2) + ")";
            })
            .catch(err => {
                console.error(err);
                alert("Error fetching predictions: " + err.message);
            });
    };
});