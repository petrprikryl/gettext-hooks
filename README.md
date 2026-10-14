# gettext-hooks

[pre-commit](https://pre-commit.com/) hooks keeping Django translation catalogs in sync with the code.

```yaml
- repo: https://github.com/petrprikryl/gettext-hooks
  rev: 1.0.0
  hooks:
    - id: django-makemessages
    - id: untranslated-messages
    - id: fuzzy-messages
```

* `django-makemessages` - runs `django-admin makemessages --no-location --no-obsolete --no-wrap` for every versioned
  catalog `<app>/locale/<lang>/LC_MESSAGES/<domain>.po`, in the directory owning the `locale` directory. It works for a
  project with a single `locale` as well as for a library with a catalog per app.
  * only existing language/domain pairs are updated, no new catalog is created - add a language by creating its `.po`
    (e.g. `django-admin makemessages --locale=sk` once)
  * on x86-64 Linux it uses statically linked GNU gettext 0.26 from
    [petrprikryl/gettext](https://github.com/petrprikryl/gettext), so catalogs are the same for everybody. The tools are
    downloaded on the first run into the hook's environment and checked against their SHA-256
    (`GETTEXT_HOOKS_ARCHIVE_URL` overrides the archive URL, e.g. for a mirror). Other platforms use the system gettext.
  * `POT-Creation-Date` is pinned to `2000-01-01`, otherwise every run would change it
  * only versioned sources are scanned: untracked and ignored directories, untracked `.py`/`.html`/`.txt`/`.js`
    files, submodules and nested apps with their own `locale` are passed to `--ignore`
  * the `Translators:` prefix of extracted comments is removed (what `remove-django-translators` of
    pre-commit-po-hooks does, which would otherwise fight with every `makemessages` run)
  * `conf/locale` (the layout of Django itself) is not supported
  * `args` are passed to `makemessages`, e.g. `args: [--extension=html,txt,py,jinja]`, then extend `files` as well
    (`files: \.(py|html|txt|js|jinja|po)$`), otherwise a commit changing only such files does not run the hook
* `untranslated-messages`, `fuzzy-messages` - hooks of
  [pre-commit-po-hooks](https://github.com/mondeja/pre-commit-po-hooks) (BSD-3-Clause), installed as a dependency,
  so a project needs this repository only

## Development

```shell
uv run pytest
```

Integration tests run `makemessages` with the system GNU gettext. Set `GETTEXT_HOOKS_ARCHIVE_URL` to the tag archive
(or a `file://` copy made by `git archive --prefix=gettext-0.0.3/ ... 0.0.3`) to run them with the pinned tools and
to check the pinned SHA-256 against the real binaries.
