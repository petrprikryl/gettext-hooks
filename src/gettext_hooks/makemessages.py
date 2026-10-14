"""Keep Django translation catalogs in sync with the code.

Runs ``django-admin makemessages`` for every versioned catalog
(``<app>/locale/<lang>/LC_MESSAGES/<domain>.po``) in the directory that owns
the ``locale`` directory, so per-app catalogs of a library are updated the same
way as a single project-wide ``locale``. Only existing language/domain pairs
are updated, no new catalog is created. Only versioned sources are scanned:
untracked and ignored directories, submodules and nested apps with their own
``locale`` are passed to ``--ignore``.

Pinned, statically linked GNU gettext tools are used on x86-64 Linux (see
``tools``), so everybody (and CI) produces byte-identical catalogs. ``POT-Creation-Date`` is
pinned, otherwise every run would change it, and the ``Translators:`` prefix of extracted
comments is removed.
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from gettext_hooks import tools

DEFAULT_ARGS = ("--no-location", "--no-obsolete", "--no-wrap")
POT_CREATION_DATE = re.compile(r'^"POT-Creation-Date: .*"$', re.MULTILINE)
PINNED_POT_CREATION_DATE = '"POT-Creation-Date: 2000-01-01 00:00+0200\\n"'
# makemessages extracts comments starting with "Translators" (`xgettext --add-comments=Translators`)
TRANSLATORS_PREFIX = re.compile(r"^#\. Translators: ", re.MULTILINE)
# Django's default `--extension`s, untracked files of other types are not passed to `--ignore`
SOURCE_SUFFIXES = {".py", ".html", ".txt", ".js"}


def git_ls_files(*args):
    out = subprocess.run(["git", "ls-files", "-z", *args], capture_output=True, check=True, text=True).stdout
    return [p for p in out.split("\0") if p]


def gettext_env():
    env = {**os.environ}
    # catalogs are found by the directory layout, not by project settings
    env.pop("DJANGO_SETTINGS_MODULE", None)
    if tools.supported():
        env["PATH"] = f"{tools.bin_dir()}{os.pathsep}{env.get('PATH', '')}"
    else:
        print(
            "django-makemessages: no pinned gettext for this platform, using the system one, "
            "catalogs may differ from the ones made on x86-64 Linux",
            file=sys.stderr,
        )
    return env


def group_catalogs(catalogs):
    """{(app directory, domain): [catalog, ...]} for catalogs in `<app>/locale/<lang>/LC_MESSAGES/`."""
    groups = defaultdict(list)
    for po in catalogs:
        lc_messages, locale_dir = po.parents[0], po.parents[2]
        if lc_messages.name != "LC_MESSAGES" or locale_dir.name != "locale":
            print(f"django-makemessages: skipping {po}, it is not in a `locale` directory", file=sys.stderr)
            continue
        if locale_dir.parent.name == "conf":
            print(f"django-makemessages: skipping {po}, `conf/locale` is not supported", file=sys.stderr)
            continue
        groups[(locale_dir.parent, po.stem)].append(po)
    return groups


def unversioned_paths():
    """Paths makemessages would scan although git does not track them.

    makemessages walks the working tree, so without this an untracked scratch file or
    `node_modules` could add strings that a clean checkout (CI) does not have.
    """
    entries = git_ls_files("--others", "--exclude-standard", "--directory")
    entries += git_ls_files("--others", "--ignored", "--exclude-standard", "--directory")
    paths = set()
    for entry in entries:
        path = Path(entry)
        # Django skips `.*` by itself and `__pycache__` holds no sources
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        if entry.endswith("/") or path.suffix in SOURCE_SUFFIXES:
            paths.add(path)
    # submodules are separate repositories (`git ls-files --stage` mode 160000)
    for line in git_ls_files("--stage"):
        meta, _, path = line.partition("\t")
        if meta.startswith("160000 "):
            paths.add(Path(path))
    return paths


def ignore_args(app_dir, excluded):
    """`--ignore` for every excluded path inside `app_dir`, relative to it (Django matches the whole path)."""
    return [
        f"--ignore={path.relative_to(app_dir).as_posix()}"
        for path in sorted(excluded)
        if path != app_dir and path.is_relative_to(app_dir)
    ]


def normalize(po):
    content = po.read_text(encoding="utf-8")
    normalized = POT_CREATION_DATE.sub(lambda _: PINNED_POT_CREATION_DATE, content, count=1)
    normalized = TRANSLATORS_PREFIX.sub("#. ", normalized)
    if normalized != content:
        # gettext writes LF, keep it on Windows too
        po.write_text(normalized, encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=f"Other arguments are passed to `makemessages`, after {' '.join(DEFAULT_ARGS)}.",
    )
    # the hook runs with `pass_filenames: false`, everything left goes to `makemessages`
    _, makemessages_args = parser.parse_known_args(argv)

    groups = group_catalogs([Path(p) for p in git_ls_files("--", "*/LC_MESSAGES/*.po")])
    if not groups:
        return 0
    # nested apps with their own `locale` are handled by their own run
    excluded = unversioned_paths() | {app_dir for app_dir, _ in groups}
    env = gettext_env()
    for (app_dir, domain), catalogs in sorted(groups.items()):
        languages = sorted(po.parents[1].name for po in catalogs)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "django",
                "makemessages",
                "--domain",
                domain,
                *(f"--locale={language}" for language in languages),
                *DEFAULT_ARGS,
                "--verbosity=0",
                *ignore_args(app_dir, excluded),
                *makemessages_args,
            ],
            cwd=app_dir,
            env=env,
            check=True,
        )
        for po in catalogs:
            normalize(po)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
