import hashlib

from huhac_media.media.hashing import sha256_file


def test_sha256_file(tmp_path) -> None:
    path = tmp_path / "český soubor.jpg"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()

