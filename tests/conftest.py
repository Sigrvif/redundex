import pytest


@pytest.fixture
def make_tree(tmp_path):
    def _make(files):
        for rel, data in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return tmp_path

    return _make
