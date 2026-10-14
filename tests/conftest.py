import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gettext_hooks import tools

PO_HEADER = """msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: 2024-05-06 07:08+0000\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: LANGUAGE <LL@li.org>\\n"
"Language: {language}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"""


class Repo:
    def __init__(self, root):
        self.root = root

    def write(self, path, content=""):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return file

    def catalog(self, path):
        language = Path(path).parents[1].name
        return self.write(path, PO_HEADER.format(language=language))

    def commit(self):
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "test"],
            cwd=self.root,
            check=True,
        )

    def untracked(self):
        out = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return out.split()

    def msgids(self, path):
        content = (self.root / path).read_text(encoding="utf-8")
        return [line[len('msgid "') : -1] for line in content.splitlines() if line.startswith('msgid "')][1:]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    return Repo(tmp_path)


@pytest.fixture
def gettext(monkeypatch):
    """GNU gettext for integration tests.

    The pinned tools when GETTEXT_HOOKS_ARCHIVE_URL is set (e.g. a `file://` archive of a
    not yet published tag), otherwise the system gettext, so tests do not download from GitHub.
    """
    if not os.environ.get("GETTEXT_HOOKS_ARCHIVE_URL"):
        monkeypatch.setattr(tools, "supported", lambda: False)
        if not shutil.which("xgettext"):
            pytest.skip("GNU gettext is not installed")
