from pathlib import Path

import pytest

from gettext_hooks import makemessages, tools


def test_group_catalogs(capsys):
    groups = makemessages.group_catalogs(
        [
            Path("locale/cs/LC_MESSAGES/django.po"),
            Path("locale/en/LC_MESSAGES/django.po"),
            Path("src/pkg/app/locale/cs/LC_MESSAGES/django.po"),
            Path("src/pkg/app/locale/cs/LC_MESSAGES/djangojs.po"),
            Path("i18n/cs/LC_MESSAGES/django.po"),
            Path("conf/locale/cs/LC_MESSAGES/django.po"),
        ]
    )

    assert {key: [po.parts[-3] for po in catalogs] for key, catalogs in groups.items()} == {
        (Path("."), "django"): ["cs", "en"],
        (Path("src/pkg/app"), "django"): ["cs"],
        (Path("src/pkg/app"), "djangojs"): ["cs"],
    }
    err = capsys.readouterr().err
    assert "skipping i18n/cs/LC_MESSAGES/django.po, it is not in a `locale` directory" in err
    assert "skipping conf/locale/cs/LC_MESSAGES/django.po, `conf/locale` is not supported" in err


def test_ignore_args_only_inside_app_relative():
    excluded = {Path("."), Path("app"), Path("app/nested"), Path("other"), Path("node_modules")}

    assert makemessages.ignore_args(Path("app"), excluded) == ["--ignore=nested"]
    assert makemessages.ignore_args(Path("."), excluded) == [
        "--ignore=app",
        "--ignore=app/nested",
        "--ignore=node_modules",
        "--ignore=other",
    ]


def test_normalize(tmp_path):
    po = tmp_path / "django.po"
    po.write_bytes(
        b'"POT-Creation-Date: 2024-05-06 07:08+0000\\n"\n'
        b"#. Translators: shown on the button\n"
        b'msgid "Buy"\n'
        b'msgstr ""\n'
    )

    makemessages.normalize(po)

    assert po.read_bytes() == (
        b'"POT-Creation-Date: 2000-01-01 00:00+0200\\n"\n#. shown on the button\nmsgid "Buy"\nmsgstr ""\n'
    )


def test_normalize_keeps_unchanged_file(tmp_path):
    po = tmp_path / "django.po"
    po.write_bytes(b'"POT-Creation-Date: 2000-01-01 00:00+0200\\n"\n')
    po.touch()
    mtime = po.stat().st_mtime_ns

    makemessages.normalize(po)

    assert po.stat().st_mtime_ns == mtime


def test_no_catalogs_downloads_nothing(repo, monkeypatch):
    def download():
        raise AssertionError("gettext must not be downloaded without catalogs")

    monkeypatch.setattr(tools, "bin_dir", download)
    repo.write("app.py", '_("Hello")\n')
    repo.commit()

    assert makemessages.main([]) == 0


@pytest.mark.usefixtures("gettext")
def test_updates_existing_catalogs_only(repo):
    repo.catalog("locale/cs/LC_MESSAGES/django.po")
    repo.write("locale/en/.gitkeep")
    repo.write("views.py", 'from django.utils.translation import gettext as _\n_("Hello")\n')
    repo.commit()

    makemessages.main([])

    assert repo.msgids("locale/cs/LC_MESSAGES/django.po") == ["Hello"]
    assert repo.untracked() == []


@pytest.mark.usefixtures("gettext")
def test_nested_locale_keeps_catalogs_apart(repo):
    repo.catalog("locale/cs/LC_MESSAGES/django.po")
    repo.catalog("locale/en/LC_MESSAGES/django.po")
    repo.catalog("app/locale/cs/LC_MESSAGES/django.po")
    repo.write("views.py", 'from django.utils.translation import gettext as _\n_("Root string")\n')
    repo.write("app/models.py", 'from django.utils.translation import gettext as _\n_("App string")\n')
    repo.commit()

    makemessages.main([])

    assert repo.msgids("locale/cs/LC_MESSAGES/django.po") == ["Root string"]
    assert repo.msgids("locale/en/LC_MESSAGES/django.po") == ["Root string"]
    assert repo.msgids("app/locale/cs/LC_MESSAGES/django.po") == ["App string"]
    # the root run must not create `app/locale/en`
    assert repo.untracked() == []


@pytest.mark.usefixtures("gettext")
def test_unversioned_sources_are_ignored(repo):
    repo.catalog("locale/cs/LC_MESSAGES/django.po")
    repo.write(".gitignore", "node_modules/\n")
    repo.write("views.py", 'from django.utils.translation import gettext as _\n_("Versioned")\n')
    repo.commit()
    repo.write("scratch.py", 'from django.utils.translation import gettext as _\n_("Untracked")\n')
    repo.write("node_modules/pkg/x.py", 'from django.utils.translation import gettext as _\n_("Ignored")\n')

    makemessages.main([])

    assert repo.msgids("locale/cs/LC_MESSAGES/django.po") == ["Versioned"]


@pytest.mark.usefixtures("gettext")
def test_javascript_domain(repo):
    repo.catalog("app/locale/cs/LC_MESSAGES/djangojs.po")
    repo.write("app/static/app.js", 'gettext("JS string");\n')
    repo.commit()

    makemessages.main([])

    assert repo.msgids("app/locale/cs/LC_MESSAGES/djangojs.po") == ["JS string"]


@pytest.mark.usefixtures("gettext")
def test_second_run_changes_nothing(repo):
    po = repo.catalog("locale/cs/LC_MESSAGES/django.po")
    repo.write(
        "views.py",
        'from django.utils.translation import gettext as _\n# Translators: shown on the button\n_("Buy")\n',
    )
    repo.commit()

    makemessages.main([])
    first = po.read_bytes()
    makemessages.main([])

    assert po.read_bytes() == first
    assert b"#. shown on the button\n" in first
    assert b"Translators:" not in first
    assert b'"POT-Creation-Date: 2000-01-01 00:00+0200\\n"' in first
