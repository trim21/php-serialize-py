from __future__ import annotations

import php_serialize


def pytest_addoption(parser):
    parser.addoption("--assert-pkg-compiled", action="store", default=None)


def pytest_configure(config):
    assert_pkg_compiled: str | None = config.option.assert_pkg_compiled
    if assert_pkg_compiled is None:
        return

    if assert_pkg_compiled == "true":
        assert php_serialize.COMPILED
    elif assert_pkg_compiled == "false":
        assert not php_serialize.COMPILED
    else:
        raise ValueError(
            f"unexpected --assert-pkg-compiled option, should be true/false,"
            f" got {assert_pkg_compiled!r} instead"
        )
