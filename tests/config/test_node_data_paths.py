import os

from config import build_data_paths


def test_node_data_paths_are_scoped_under_node_data_dir():
    paths = build_data_paths("data/node-a")

    assert paths == {
        "data_dir": "data/node-a",
        "blockchain_file": os.path.join("data/node-a", "blockchain.json"),
        "peers_file": os.path.join("data/node-a", "peers.json"),
        "temp_dir": os.path.join("data/node-a", "temp"),
        "submissions_dir": os.path.join("data/node-a", "temp", "submissions"),
    }


def test_empty_node_data_dir_defaults_to_current_directory():
    paths = build_data_paths("")

    assert paths["data_dir"] == "."
    assert paths["blockchain_file"] == os.path.join(".", "blockchain.json")
