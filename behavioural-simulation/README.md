# Behavioural Simulation (Behavioural Preference Modelling module)

Synced from the `BiasBreakers-porfolio-optimization` repo. This folder is **self-contained**
and does not modify the investor-portal React app. Two parts:

## backend/  — FastAPI game engine + behavioural estimators (Python)
Run:
```
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```
Key entry points: `app.py` (REST API), `multi_block_session.py` / `allocation_engine.py`
(game engine), `estimator_v2.py` + `final_estimator.py` + `calibration.py` (parameter
recovery), `event_round.py` + `lambda_events.py` (matched-stakes λ), `dynamic_estimator.py`
(drift tracking), `utility_function.py` (reward hand-off). `experiments/` holds the
recovery/validation scripts and result CSVs; `ground_truth_pipeline/` the offline
ground-truth recovery; `scenario_build/` the CSE market data.

## frontend/  — standalone research-instrument UI (plain HTML/CSS/JS)
The original terminal-style game UI. Open `index.html` (served alongside the running
backend). This is separate from the portal's React frontend and can later be ported into it.

Note: the Python virtual environment (`venv/`) was intentionally not copied — recreate it
with the steps above.
