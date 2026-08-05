"""Central data-file locations, so modules keep finding scenario_build/ and the
CSVs after being grouped into subpackages (they used to rely on __file__)."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SCENARIO_BUILD = os.path.join(ROOT, "scenario_build")
CALIB_CSV = os.path.join(ROOT, "calib_data.csv")
ARCHETYPE_CSV = os.path.join(ROOT, "archetype_data.csv")
