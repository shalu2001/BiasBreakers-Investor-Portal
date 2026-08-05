import requests
r = requests.post("http://localhost:8000/predict", json={"as_of_date":"2026-07-15"})
print(r.status_code, r.json())