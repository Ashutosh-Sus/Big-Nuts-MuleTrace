"""Method panel source (`GET /api/config`): the running configuration, read-only, with the hash the console shows."""
import json

from test_api import client  # noqa: F401  (fixture)
from test_console_fixes import load

from muletrace.config import DEFAULT
from muletrace.demo_data import generate


def test_config_is_the_running_configuration_and_its_hash(client):
    r = client.get("/api/config").json()
    assert r["config"] == json.loads(json.dumps(DEFAULT.as_dict()))
    assert r["hash"] == DEFAULT.hash() == client.get("/api/datasets/current").json()["dataset"]["config_hash"]
    assert r["engine"] == "flow"


def test_fallback_engine_reports_its_own_configuration(tmp_path):
    c = load(tmp_path, generate(), engine="window", name="w")
    r = c.get("/api/config").json()
    assert r["engine"] == r["config"]["engine"] == "window"
    assert r["hash"] == c.get("/api/datasets/current").json()["dataset"]["config_hash"] != DEFAULT.hash()


def test_configuration_cannot_be_changed_through_the_api(client):
    before = client.get("/api/config").json()
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/config").status_code == 405
    assert client.get("/api/config").json() == before
