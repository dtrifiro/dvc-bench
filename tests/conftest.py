import os
from contextlib import suppress

import pytest

from dvc.testing.fixtures import *  # noqa, pylint: disable=wildcard-import

# Prevent updater and analytics from running their processes
os.environ["DVC_TEST"] = "true"
# Ensure progress output even when not outputting to raw sys.stderr console
os.environ["DVC_IGNORE_ISATTY"] = "true"
# Disable system git config
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

REMOTES = {
    # remote: enabled_by_default?
    "azure": False,
    "gdrive": False,
    "gs": False,
    "hdfs": False,
    "http": True,
    "oss": False,
    "s3": False,
    "ssh": True,
    "webdav": True,
}


DEFAULT_DVC_BIN = "dvc"
DEFAULT_DVC_GIT_REPO = "https://github.com/iterative/dvc"
DEFAULT_PROJECT_GIT_REPO = "https://github.com/iterative/example-get-started"


@pytest.fixture(autouse=True)
def reset_loglevel(request, caplog):
    """
    Use it to ensure log level at the start of each test
    regardless of dvc.logger.setup(), Repo configs or whatever.
    """
    ini_opt = None
    with suppress(ValueError):
        ini_opt = request.config.getini("log_level")

    level = request.config.getoption("--log-level") or ini_opt
    if level:
        with caplog.at_level(level.upper(), logger="dvc"):
            yield
    else:
        yield


@pytest.fixture(autouse=True)
def enable_ui():
    from dvc.ui import ui

    ui.enable()


def _get_opt(remote_name, action):
    return f"--{action}-{remote_name}"


def pytest_addoption(parser):
    """Adds remote-related flags to selectively disable/enable for tests
    Eg: If some remotes, eg: ssh is enabled to be tested for by default
    (see above `REMOTES`), then, `--disable-ssh` flag is added. If remotes
    like `hdfs` are disabled by default, `--enable-hdfs` is added to make them
    run.

    You can also make everything run-by-default with `--all` flag, which takes
    precedence on all previous `--enable-*`/`--disable-*` flags.
    """
    parser.addoption(
        "--all",
        action="store_true",
        default=False,
        help="Test all of the remotes, unless other flags also supplied",
    )
    for remote_name in REMOTES:
        for action in ("enable", "disable"):
            opt = _get_opt(remote_name, action)
            parser.addoption(
                opt,
                action="store_true",
                default=None,
                help=f"{action} tests for {remote_name}",
            )

    parser.addoption(
        "--size",
        choices=["tiny", "small", "large", "mnist"],
        default="small",
        help="Size of the dataset/datafile to use in tests",
    )

    parser.addoption(
        "--remote",
        choices=list(REMOTES.keys()),
        default="local",
        help="Remote type to use in tests",
    )

    parser.addoption(
        "--dvc-bin",
        type=str,
        default=DEFAULT_DVC_BIN,
        help="Path to dvc binary",
    )

    parser.addoption(
        "--dvc-revs",
        type=str,
        help=(
            "Comma-separated list of DVC revisions to test "
            "(overrides `--dvc-bin`)"
        ),
    )

    parser.addoption(
        "--dvc-git-repo",
        type=str,
        default=DEFAULT_DVC_GIT_REPO,
        help="Path or url to dvc git repo",
    )

    parser.addoption(
        "--project-rev",
        type=str,
        help="Project revision to test",
    )

    parser.addoption(
        "--project-git-repo",
        type=str,
        default=DEFAULT_PROJECT_GIT_REPO,
        help="Path or url to dvc project",
    )


class DVCTestConfig:
    def __init__(self):
        self.enabled_remotes = set()
        self.size = "small"
        self.remote = "local"
        self.dvc_bin = DEFAULT_DVC_BIN
        self.dvc_revs = None
        self.dvc_git_repo = DEFAULT_DVC_GIT_REPO
        self.project_rev = None
        self.project_git_repo = DEFAULT_PROJECT_GIT_REPO

    def requires(self, remote_name):
        if remote_name not in REMOTES or remote_name in self.enabled_remotes:
            return

        pytest.skip(f"{remote_name} tests not enabled through CLI")

    def apply_marker(self, marker):
        self.requires(marker.name)


def pytest_runtest_setup(item):
    # Apply test markers to skip tests selectively
    # NOTE: this only works on individual tests,
    # for fixture, use `test_config` fixture and
    # run `test_config.requires(remote_name)`.
    for marker in item.iter_markers():
        item.config.dvc_config.apply_marker(marker)

    if (
        "CI" in os.environ
        and item.get_closest_marker("needs_internet") is not None
    ):
        # remotes that need internet connection might be flaky,
        # so we rerun them in case it fails.
        item.add_marker(pytest.mark.flaky(max_runs=5, min_passes=1))


@pytest.fixture(scope="session")
def test_config(request):
    return request.config.dvc_config


def pytest_configure(config):
    config.dvc_config = DVCTestConfig()

    for remote_name in REMOTES:
        config.addinivalue_line(
            "markers", f"{remote_name}: mark test as requiring {remote_name}"
        )

    enabled_remotes = config.dvc_config.enabled_remotes
    if config.getoption("--all"):
        enabled_remotes.update(REMOTES)
    else:
        default_enabled = {k for k, v in REMOTES.items() if v}
        enabled_remotes.update(default_enabled)

    for remote_name in REMOTES:
        enabled_opt = _get_opt(remote_name, "enable")
        disabled_opt = _get_opt(remote_name, "disable")

        enabled = config.getoption(enabled_opt)
        disabled = config.getoption(disabled_opt)
        if disabled and enabled:
            continue  # default behavior if both flags are supplied

        if disabled:
            enabled_remotes.discard(remote_name)
        if enabled:
            enabled_remotes.add(remote_name)

    config.dvc_config.size = config.getoption("--size")
    config.dvc_config.remote = config.getoption("--remote")
    config.dvc_config.dvc_bin = config.getoption("--dvc-bin")
    config.dvc_config.dvc_revs = config.getoption("--dvc-revs")
    config.dvc_config.dvc_git_repo = config.getoption("--dvc-git-repo")
    config.dvc_config.project_rev = config.getoption("--project-rev")
    config.dvc_config.project_git_repo = config.getoption("--project-git-repo")
