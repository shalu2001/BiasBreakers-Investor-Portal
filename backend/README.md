# Unified backend

Composes the three previously-separate backends into one process, unprefixed:

- RL engine ([../server](../server)) -- `/recommendation/*`
- Narrative engine ([../narrative_engine](../narrative_engine)) -- `/health`, `/predict`
- Behavioral simulator ([../behavioural-simulation/backend](../behavioural-simulation/backend)) -- `/session/*`, `/portal/*`

Each service's `.env` (in its own directory) is still read the same way it always was -- nothing to change there. `server/.env` is real and git-tracked with live credentials; see the root-level plan/notes for the recommended cleanup (rotate + gitignore), not done as part of this merge.

## Run

**Requires Python 3.10.x.** The RL model file (`server/model/behavioral_ppo_candidate_list_v14.zip`) embeds a pickled description of its custom policy architecture (`PersonaAwareExtractor`), not just weight values -- that pickle isn't reliably portable across Python versions. On a newer interpreter (e.g. 3.13), `PPO.load()` can silently reconstruct the wrong (default) architecture instead of raising a clear error, then fail with a confusing `state_dict` size-mismatch. Create the venv with 3.10 specifically:

```bash
py -3.10 -m venv backend/venv
```

From the **repo root** (required so `backend`, `narrative_engine`, etc. are importable):

```bash
pip install -r backend/requirements.txt
uvicorn backend.gateway:app --reload --host 0.0.0.0 --port 8000
```

The three original services still run standalone too, if you need to debug one in isolation (see each directory's own README / entrypoint).
