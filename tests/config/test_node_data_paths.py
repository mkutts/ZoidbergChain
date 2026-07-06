import os

from config import build_data_paths


def test_node_data_paths_are_scoped_under_node_data_dir():
    paths = build_data_paths("data/node-a")

    assert paths == {
        "data_dir": "data/node-a",
        "blockchain_file": os.path.join("data/node-a", "blockchain.json"),
        "peers_file": os.path.join("data/node-a", "peers.json"),
        "sqlite_db_path": os.path.join("data/node-a", "zoidbergchain.db"),
        "temp_dir": os.path.join("data/node-a", "temp"),
        "submissions_dir": os.path.join("data/node-a", "temp", "submissions"),
    }


def test_empty_node_data_dir_defaults_to_current_directory():
    paths = build_data_paths("")

    assert paths["data_dir"] == "."
    assert paths["blockchain_file"] == os.path.join(".", "blockchain.json")
    assert paths["sqlite_db_path"] == os.path.join(".", "zoidbergchain.db")


def test_two_node_data_paths_do_not_collide():
    node_a_paths = build_data_paths("data/node-a")
    node_b_paths = build_data_paths("data/node-b")

    assert node_a_paths["data_dir"] != node_b_paths["data_dir"]
    assert node_a_paths["blockchain_file"] != node_b_paths["blockchain_file"]
    assert node_a_paths["peers_file"] != node_b_paths["peers_file"]
