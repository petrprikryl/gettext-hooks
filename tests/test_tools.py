import hashlib
import io
import os
import sys
import tarfile

import pytest

from gettext_hooks import tools


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Fake tag archive with tiny "binaries", the pinned hashes patched to match them."""
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
    (tmp_path / "env").mkdir()
    contents = {tool: f"#!/bin/sh\necho {tool}\n".encode() for tool in tools.SHA256}
    monkeypatch.setattr(
        tools, "SHA256", {tool: hashlib.sha256(data).hexdigest() for tool, data in contents.items()}
    )

    def build(files=contents):
        path = tmp_path / "gettext.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for tool, data in files.items():
                info = tarfile.TarInfo(f"gettext-{tools.GETTEXT_RELEASE}/x86_64-linux/{tool}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        monkeypatch.setenv("GETTEXT_HOOKS_ARCHIVE_URL", path.as_uri())
        return path

    build.contents = contents
    return build


def test_download_verify_and_cache(archive):
    path = archive()

    directory = tools.bin_dir()

    assert directory == tools.Path(sys.prefix) / f"gettext-{tools.GETTEXT_RELEASE}"
    for tool, data in archive.contents.items():
        assert (directory / tool).read_bytes() == data
        assert os.access(directory / tool, os.X_OK)
    path.unlink()
    assert tools.bin_dir() == directory  # cached, no second download


def test_tampered_binary_is_rejected(archive):
    archive({**archive.contents, "msgfmt": b"evil"})

    with pytest.raises(RuntimeError, match="msgfmt .* does not match its SHA-256"):
        tools.bin_dir()
    assert not (tools.Path(sys.prefix) / f"gettext-{tools.GETTEXT_RELEASE}").exists()


def test_missing_binary_is_rejected(archive):
    archive({tool: data for tool, data in archive.contents.items() if tool != "msguniq"})

    with pytest.raises(RuntimeError, match="msguniq is missing"):
        tools.bin_dir()


def test_incomplete_copy_is_replaced(archive):
    archive()
    target = tools.Path(sys.prefix) / f"gettext-{tools.GETTEXT_RELEASE}"
    target.mkdir()
    (target / "xgettext").write_bytes(b"partial")

    assert tools.bin_dir() == target
    assert tools.complete(target)


@pytest.mark.skipif(not os.environ.get("GETTEXT_HOOKS_ARCHIVE_URL"), reason="needs the real tag archive")
@pytest.mark.skipif(not tools.supported(), reason="the pinned tools are x86-64 Linux binaries")
def test_real_archive_matches_pinned_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(tmp_path))

    directory = tools.bin_dir()

    for tool in tools.SHA256:
        assert tools.sha256(directory / tool) == tools.SHA256[tool]
