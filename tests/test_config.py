"""Tests for config parsing."""

import hashlib
import typing as t
import itertools
import pathlib
import sys

import pytest

from pypiserver.backend import SimpleFileBackend, BackendProxy
from pypiserver.config import DEFAULTS, Config, RunConfig, UpdateConfig

FILE_DIR = pathlib.Path(__file__).parent.resolve()

# Username and password stored in the htpasswd.a.a test file.
HTPASS_TEST_FILE = str(FILE_DIR / "../fixtures/htpasswd.a.a")
HTPASS_TEST_USER = "a"
HTPASS_TEST_PASS = "a"

TEST_WELCOME_FILE = str(pathlib.Path(__file__).parent / "sample_msg.html")
TEST_IGNORELIST_FILE = str(pathlib.Path(__file__).parent / "test-ignorelist")


class ConfigTestCase(t.NamedTuple):
    # A description of the test case
    case: str
    # Arguments to pass to the Config constructor
    args: t.List[str]
    # Legacy arguments that should yield an equivalent config class
    legacy_args: t.List[str]
    # The config class the arguments should resolve to
    exp_config_type: t.Type
    # Expected values in the config. These don't necessarily need to be
    # exclusive. Instead, they should just look at the attributes relevant
    # to the test case at hand. A special "_test" key, if present, should
    # map to a function that takes the config as an argument. If this
    # returns a falsey value, the test will be failed.
    exp_config_values: t.Dict[str, t.Any]


# The iterables generated by this function are designed to be unpacked
# into the _CONFIG_TEST_PARAMS constant.
def generate_subcommand_test_cases(
    case: str,
    extra_args: t.List[str] = None,
    exp_config_values: t.Dict[str, t.Any] = None,
) -> t.Iterable[ConfigTestCase]:
    """Generate `run` and `update` test cases automatically.

    Use to avoid having to specify individual cases for situations like
    global arguments, where the resultant configs should have the same values.

    These tests also help to ensure parity between legacy and modern orderings,
    since generally the only difference between the two should be the presence
    or absence of the subcommand.

    :param case: the test case name. will be combined with the subcommand
        to generate a case name for the resultant case.
    :param extra_args: arguments to pass after the subcommand positional
        arguments
    :param extra_legacy_args: legacy arguments to pass in addition to the
        subcommand arguments, if any
    :param exp_config_values: the values that should be present on both
        run and update test cases.
    """
    extra_args = extra_args or []
    extra_legacy_args = extra_args
    exp_config_values = exp_config_values or {}
    # The legacy "update" subcommand was specified with an optional `-U`
    # argument. This allows us to map the subcommand to that argument, so
    # we can include it in the resulting legacy args.
    legacy_base_arg_map = {"update": ["-U"]}
    # A mapping of subcommands to their expected Config types.
    config_type_map = {
        "run": RunConfig,
        "update": UpdateConfig,
    }
    return (
        ConfigTestCase(
            case="{subcmd}: {case}",
            args=[subcmd, *extra_args],
            legacy_args=[
                *legacy_base_arg_map.get(subcmd, []),
                *extra_legacy_args,
            ],
            exp_config_type=config_type_map[subcmd],
            exp_config_values=exp_config_values,
        )
        for subcmd in ("run", "update")
    )


# Define Config test parameters
_CONFIG_TEST_PARAMS: t.Tuple[ConfigTestCase, ...] = (
    # ******************************************************************
    # Raw subcommands
    # ******************************************************************
    *generate_subcommand_test_cases(
        case="no arguments",
    ),
    # ******************************************************************
    # Global args
    # ******************************************************************
    # Package directories
    *generate_subcommand_test_cases(
        case="no package directory specified",
        exp_config_values={"roots": DEFAULTS.PACKAGE_DIRECTORIES},
    ),
    *generate_subcommand_test_cases(
        case="single package directory specified",
        extra_args=[str(FILE_DIR)],
        exp_config_values={"roots": [FILE_DIR]},
    ),
    *generate_subcommand_test_cases(
        case="multiple package directory specified",
        extra_args=[str(FILE_DIR), str(FILE_DIR.parent)],
        exp_config_values={
            "roots": [
                FILE_DIR,
                FILE_DIR.parent,
            ]
        },
    ),
    ConfigTestCase(
        case="update with package directory (out-of-order legacy order)",
        args=["update", str(FILE_DIR)],
        legacy_args=[str(FILE_DIR), "-U"],
        exp_config_type=UpdateConfig,
        exp_config_values={"roots": [FILE_DIR]},
    ),
    ConfigTestCase(
        case="update with multiple package directories (weird ordering)",
        args=["update", str(FILE_DIR), str(FILE_DIR.parent)],
        legacy_args=[str(FILE_DIR), "-U", str(FILE_DIR.parent)],
        exp_config_type=UpdateConfig,
        exp_config_values={
            "roots": [
                FILE_DIR,
                FILE_DIR.parent,
            ]
        },
    ),
    # verbosity
    *(
        # Generate verbosity test-cases for 0 through 5 -v arguments,
        # for all subcommands.
        itertools.chain.from_iterable(
            # This inner iterable (generate(...) for verbosity in range(5))
            # will be an iterable of 5 items, where each item is essentially
            # an n-tuple, where n is the number of subcommands. Passing this
            # iterable to chain.from_iterable() flattens it, so it is just
            # one long iterable of cases. These are then unpacked into the
            # test case tuple with the *, above.
            generate_subcommand_test_cases(
                case=f"verbosity {verbosity}",
                extra_args=["-v" for _ in range(verbosity)],
                exp_config_values={"verbosity": verbosity},
            )
            for verbosity in range(5)
        )
    ),
    # log-file
    *generate_subcommand_test_cases(
        case="log file unspecified", exp_config_values={"log_file": None}
    ),
    *generate_subcommand_test_cases(
        case="log file specified",
        extra_args=["--log-file", "foo"],
        exp_config_values={"log_file": "foo"},
    ),
    # log-stream
    *generate_subcommand_test_cases(
        case="log stream unspecified",
        exp_config_values={"log_stream": DEFAULTS.LOG_STREAM},
    ),
    *generate_subcommand_test_cases(
        case="log stream set to stdout",
        extra_args=["--log-stream", "stdout"],
        exp_config_values={"log_stream": sys.stdout},
    ),
    *generate_subcommand_test_cases(
        case="log stream set to stderr",
        extra_args=["--log-stream", "stderr"],
        exp_config_values={"log_stream": sys.stderr},
    ),
    *generate_subcommand_test_cases(
        case="log stream set to none",
        extra_args=["--log-stream", "none"],
        exp_config_values={"log_stream": None},
    ),
    *generate_subcommand_test_cases(
        case="log format unset",
        exp_config_values={"log_frmt": DEFAULTS.LOG_FRMT},
    ),
    *generate_subcommand_test_cases(
        case="log format set",
        extra_args=["--log-frmt", "foobar %(message)s"],
        exp_config_values={"log_frmt": "foobar %(message)s"},
    ),
    # ******************************************************************
    # Run subcommand args
    # ******************************************************************
    # port
    ConfigTestCase(
        case="Run: port unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"port": DEFAULTS.PORT},
    ),
    ConfigTestCase(
        case="Run: port specified",
        args=["run", "-p", "9900"],
        legacy_args=["-p", "9900"],
        exp_config_type=RunConfig,
        exp_config_values={"port": 9900},
    ),
    ConfigTestCase(
        case="Run: port specified (long form)",
        args=["run", "--port", "9900"],
        legacy_args=["--port", "9900"],
        exp_config_type=RunConfig,
        exp_config_values={"port": 9900},
    ),
    # interface
    ConfigTestCase(
        case="Run: interface unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"host": DEFAULTS.INTERFACE},
    ),
    ConfigTestCase(
        case="Run: interface specified",
        args=["run", "-i", "1.1.1.1"],
        legacy_args=["-i", "1.1.1.1"],
        exp_config_type=RunConfig,
        exp_config_values={"host": "1.1.1.1"},
    ),
    ConfigTestCase(
        case="Run: interface specified (long form)",
        args=["run", "--interface", "1.1.1.1"],
        legacy_args=["--interface", "1.1.1.1"],
        exp_config_type=RunConfig,
        exp_config_values={"host": "1.1.1.1"},
    ),
    ConfigTestCase(
        case="Run: host specified",
        args=["run", "-H", "1.1.1.1"],
        legacy_args=["-H", "1.1.1.1"],
        exp_config_type=RunConfig,
        exp_config_values={"host": "1.1.1.1"},
    ),
    ConfigTestCase(
        case="Run: host specified (long form)",
        args=["run", "--host", "1.1.1.1"],
        legacy_args=["--host", "1.1.1.1"],
        exp_config_type=RunConfig,
        exp_config_values={"host": "1.1.1.1"},
    ),
    # authenticate
    ConfigTestCase(
        case="Run: authenticate unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"authenticate": DEFAULTS.AUTHENTICATE},
    ),
    ConfigTestCase(
        case="Run: authenticate specified as non-default value",
        args=["run", "-a", "list"],
        legacy_args=["-a", "list"],
        exp_config_type=RunConfig,
        exp_config_values={"authenticate": ["list"]},
    ),
    ConfigTestCase(
        case="Run: authenticate specified with multiple values",
        args=["run", "-a", "list, update,download"],
        legacy_args=["-a", "list, update,download"],
        exp_config_type=RunConfig,
        exp_config_values={"authenticate": ["download", "list", "update"]},
    ),
    ConfigTestCase(
        case="Run: authenticate specified with dot",
        # both auth and pass must be specified as empty if one of them is empty.
        args=["run", "-a", ".", "-P", "."],
        legacy_args=["-a", ".", "-P", "."],
        exp_config_type=RunConfig,
        exp_config_values={
            "authenticate": [],
            "_test": lambda conf: bool(conf.auther("foo", "bar")) is True,
        },
    ),
    # passwords
    ConfigTestCase(
        case="Run: passwords file unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"password_file": None},
    ),
    ConfigTestCase(
        "Run: passwords file specified",
        args=["run", "-P", HTPASS_TEST_FILE],
        legacy_args=["-P", HTPASS_TEST_FILE],
        exp_config_type=RunConfig,
        exp_config_values={
            "password_file": HTPASS_TEST_FILE,
            "_test": lambda conf: (
                bool(conf.auther("foo", "bar")) is False
                and bool(conf.auther("a", "a")) is True
            ),
        },
    ),
    ConfigTestCase(
        "Run: passwords file specified (long-form)",
        args=["run", "--passwords", HTPASS_TEST_FILE],
        legacy_args=["--passwords", HTPASS_TEST_FILE],
        exp_config_type=RunConfig,
        exp_config_values={
            "password_file": HTPASS_TEST_FILE,
            "_test": (
                lambda conf: (
                    bool(conf.auther("foo", "bar")) is False
                    and conf.auther("a", "a") is True
                )
            ),
        },
    ),
    ConfigTestCase(
        "Run: passwords file empty ('.')",
        # both auth and pass must be specified as empty if one of them is empty.
        args=["run", "-P", ".", "-a", "."],
        legacy_args=["-P", ".", "-a", "."],
        exp_config_type=RunConfig,
        exp_config_values={
            "password_file": ".",
            "_test": lambda conf: bool(conf.auther("foo", "bar")) is True,
        },
    ),
    # disable-fallback
    ConfigTestCase(
        case="Run: disable-fallback unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"disable_fallback": False},
    ),
    ConfigTestCase(
        case="Run: disable-fallback set",
        args=["run", "--disable-fallback"],
        legacy_args=["--disable-fallback"],
        exp_config_type=RunConfig,
        exp_config_values={"disable_fallback": True},
    ),
    # fallback-url
    ConfigTestCase(
        case="Run: fallback-url unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"fallback_url": DEFAULTS.FALLBACK_URL},
    ),
    ConfigTestCase(
        case="Run: fallback-url specified",
        args=["run", "--fallback-url", "foobar.com"],
        legacy_args=["--fallback-url", "foobar.com"],
        exp_config_type=RunConfig,
        exp_config_values={"fallback_url": "foobar.com"},
    ),
    # server method
    ConfigTestCase(
        case="Run: server method unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"server_method": DEFAULTS.SERVER_METHOD},
    ),
    *(
        ConfigTestCase(
            case="Run: server method set to {arg}",
            args=["run", "--server", arg],
            legacy_args=["--server", arg],
            exp_config_type=RunConfig,
            exp_config_values={"server_method": arg},
        )
        for arg in (
            "auto",
            "cherrypy",
            "gevent",
            "gunicorn",
            "paste",
            "twisted",
            "wsgiref",
        )
    ),
    ConfigTestCase(
        case="Run: server method is case insensitive",
        args=["run", "--server", "CherryPy"],
        legacy_args=["--server", "CherryPy"],
        exp_config_type=RunConfig,
        exp_config_values={"server_method": "cherrypy"},
    ),
    # overwrite
    ConfigTestCase(
        "Run: overwrite unset",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"overwrite": False},
    ),
    ConfigTestCase(
        case="Run: overwrite set (long-form)",
        args=["run", "-o"],
        legacy_args=["-o"],
        exp_config_type=RunConfig,
        exp_config_values={"overwrite": True},
    ),
    ConfigTestCase(
        case="Run: overwrite set (long-form)",
        args=["run", "--overwrite"],
        legacy_args=["--overwrite"],
        exp_config_type=RunConfig,
        exp_config_values={"overwrite": True},
    ),
    # hash-algo
    ConfigTestCase(
        case="Run: hash-algo unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"hash_algo": DEFAULTS.HASH_ALGO},
    ),
    *(
        ConfigTestCase(
            case="Run: hash-algo {}",
            args=["run", "--hash-algo", algo],
            legacy_args=["--hash-algo", algo],
            exp_config_type=RunConfig,
            exp_config_values={"hash_algo": algo},
        )
        for algo in hashlib.algorithms_available
    ),
    *(
        ConfigTestCase(
            case="Run: hash-algo disabled",
            args=["run", "--hash-algo", off_value],
            legacy_args=["--hash-algo", off_value],
            exp_config_type=RunConfig,
            exp_config_values={"hash_algo": None},
        )
        for off_value in ("0", "off", "false", "no", "NO")
    ),
    # welcome file
    ConfigTestCase(
        case="Run: welcome file unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={
            "_test": lambda conf: "Welcome to pypiserver" in conf.welcome_msg
        },
    ),
    ConfigTestCase(
        case="Run: custom welcome file specified",
        args=["run", "--welcome", TEST_WELCOME_FILE],
        legacy_args=["--welcome", TEST_WELCOME_FILE],
        exp_config_type=RunConfig,
        exp_config_values={
            "_test": lambda conf: "Hello pypiserver tester!" in conf.welcome_msg
        },
    ),
    # cache-control
    ConfigTestCase(
        case="Run: cache-control unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"cache_control": None},
    ),
    ConfigTestCase(
        case="Run: cache-control specified",
        args=["run", "--cache-control", "1900"],
        legacy_args=["--cache-control", "1900"],
        exp_config_type=RunConfig,
        exp_config_values={"cache_control": 1900},
    ),
    # log-req-frmt
    ConfigTestCase(
        case="Run: log request format unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"log_req_frmt": DEFAULTS.LOG_REQ_FRMT},
    ),
    ConfigTestCase(
        case="Run: log request format specified",
        args=["run", "--log-req-frmt", "foo"],
        legacy_args=["--log-req-frmt", "foo"],
        exp_config_type=RunConfig,
        exp_config_values={"log_req_frmt": "foo"},
    ),
    # log-res-frmt
    ConfigTestCase(
        case="Run: log response format unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"log_res_frmt": DEFAULTS.LOG_RES_FRMT},
    ),
    ConfigTestCase(
        case="Run: log response format specified",
        args=["run", "--log-res-frmt", "foo"],
        legacy_args=["--log-res-frmt", "foo"],
        exp_config_type=RunConfig,
        exp_config_values={"log_res_frmt": "foo"},
    ),
    # log-err-frmt
    ConfigTestCase(
        case="Run: log error format unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={"log_err_frmt": DEFAULTS.LOG_ERR_FRMT},
    ),
    ConfigTestCase(
        case="Run: log error format specified",
        args=["run", "--log-err-frmt", "foo"],
        legacy_args=["--log-err-frmt", "foo"],
        exp_config_type=RunConfig,
        exp_config_values={"log_err_frmt": "foo"},
    ),
    # backend
    ConfigTestCase(
        "Run: backend unspecified",
        args=["run"],
        legacy_args=[],
        exp_config_type=RunConfig,
        exp_config_values={
            "backend_arg": "auto",
            "_test": (
                lambda conf: (
                    isinstance(conf.backend, BackendProxy)
                    and isinstance(conf.backend.backend, SimpleFileBackend)
                )
            ),
        },
    ),
    ConfigTestCase(
        "Run: simple backend specified",
        args=["run", "--backend", "simple-dir"],
        legacy_args=["--backend", "simple-dir"],
        exp_config_type=RunConfig,
        exp_config_values={
            "_test": (
                lambda conf: (
                    isinstance(conf.backend.backend, SimpleFileBackend)
                )
            ),
        },
    ),
    # ******************************************************************
    # Update subcommand args
    # ******************************************************************
    # execute
    ConfigTestCase(
        case="Update: execute not specified",
        args=["update"],
        legacy_args=["-U"],
        exp_config_type=UpdateConfig,
        exp_config_values={"execute": False},
    ),
    ConfigTestCase(
        case="Update: execute specified",
        args=["update", "-x"],
        legacy_args=["-U", "-x"],
        exp_config_type=UpdateConfig,
        exp_config_values={"execute": True},
    ),
    ConfigTestCase(
        case="Update: execute specified (long-form)",
        args=["update", "--execute"],
        legacy_args=["-U", "--execute"],
        exp_config_type=UpdateConfig,
        exp_config_values={"execute": True},
    ),
    # download-directory
    ConfigTestCase(
        case="Update: download-directory not specified",
        args=["update"],
        legacy_args=["-U"],
        exp_config_type=UpdateConfig,
        exp_config_values={"download_directory": None},
    ),
    ConfigTestCase(
        case="Update: download-directory specified",
        args=["update", "-d", "foo"],
        legacy_args=["-U", "-d", "foo"],
        exp_config_type=UpdateConfig,
        exp_config_values={"download_directory": "foo"},
    ),
    ConfigTestCase(
        case="Update: download-directory specified (long-form)",
        args=["update", "--download-directory", "foo"],
        legacy_args=["-U", "--download-directory", "foo"],
        exp_config_type=UpdateConfig,
        exp_config_values={"download_directory": "foo"},
    ),
    # allow-unstable
    ConfigTestCase(
        case="Update: allow-unstable not specified",
        args=["update"],
        legacy_args=["-U"],
        exp_config_type=UpdateConfig,
        exp_config_values={"allow_unstable": False},
    ),
    ConfigTestCase(
        case="Update: allow-unstable specified",
        args=["update", "-u"],
        legacy_args=["-U", "-u"],
        exp_config_type=UpdateConfig,
        exp_config_values={"allow_unstable": True},
    ),
    ConfigTestCase(
        case="Update: allow-unstable specified (long-form)",
        args=["update", "--allow-unstable"],
        legacy_args=["-U", "--allow-unstable"],
        exp_config_type=UpdateConfig,
        exp_config_values={"allow_unstable": True},
    ),
    # ignorelist-file
    ConfigTestCase(
        case="Update: ignorelist-file not specified",
        args=["update"],
        legacy_args=["-U"],
        exp_config_type=UpdateConfig,
        exp_config_values={"ignorelist": []},
    ),
    ConfigTestCase(
        case="Update: ignorelist-file specified",
        args=["update", "--ignorelist-file", TEST_IGNORELIST_FILE],
        legacy_args=["-U", "--ignorelist-file", TEST_IGNORELIST_FILE],
        exp_config_type=UpdateConfig,
        exp_config_values={"ignorelist": ["mypiserver", "something"]},
    ),
    ConfigTestCase(
        case="Update: blacklist-file specified",
        args=["update", "--blacklist-file", TEST_IGNORELIST_FILE],
        legacy_args=["-U", "--blacklist-file", TEST_IGNORELIST_FILE],
        exp_config_type=UpdateConfig,
        exp_config_values={"ignorelist": ["mypiserver", "something"]},
    ),
)

# Split case names out from cases to use as pytest IDs.
# pylint: disable=unsubscriptable-object
CONFIG_TEST_PARAMS = (i[1:] for i in _CONFIG_TEST_PARAMS)
# pylint: enable=unsubscriptable-object
CONFIG_TEST_IDS = (i.case for i in _CONFIG_TEST_PARAMS)


class ConfigErrorCase(t.NamedTuple):
    """Configuration arguments that should cause errors.

    The cases include a case descrpition, a list of arguments,
    and, if desired, expected text that should be part of what
    is printed out to stderr. If no text is provided, the content
    of stderr will not be checked.
    """

    case: str
    args: t.List[str]
    exp_txt: t.Optional[str]


_CONFIG_ERROR_CASES = (
    *(
        ConfigErrorCase(
            case=f"Invalid hash algo: {val}",
            args=["run", "--hash-algo", val],
            exp_txt=f"Hash algorithm '{val}' is not available",
        )
        for val in ("true", "foo", "1", "md6")
    ),
)
# pylint: disable=unsubscriptable-object
CONFIG_ERROR_PARAMS = (i[1:] for i in _CONFIG_ERROR_CASES)
# pylint: enable=unsubscriptable-object
CONFIG_ERROR_IDS = (i.case for i in _CONFIG_ERROR_CASES)


@pytest.mark.parametrize(
    "args, legacy_args, exp_config_type, exp_config_values",
    CONFIG_TEST_PARAMS,
    ids=CONFIG_TEST_IDS,
)
def test_config(
    args: t.List[str],
    legacy_args: t.List[str],
    exp_config_type: t.Type,
    exp_config_values: t.Dict[str, t.Any],
) -> None:
    """Validate config test cases."""
    conf = Config.from_args(args)
    conf_legacy = Config.from_args(legacy_args)

    assert isinstance(conf, exp_config_type)
    assert all(
        getattr(conf, k) == v
        for k, v in exp_config_values.items()
        if k != "_test"
    ), {
        k: (getattr(conf, k), v)
        for k, v in exp_config_values.items()
        if k != "_test" and getattr(conf, k) != v
    }

    if "_test" in exp_config_values:
        assert exp_config_values["_test"](conf)

    assert conf == conf_legacy


@pytest.mark.parametrize(
    "args, exp_txt",
    CONFIG_ERROR_PARAMS,
    ids=CONFIG_TEST_IDS,
)
def test_config_error(
    args: t.List[str],
    exp_txt: t.Optional[str],
    capsys,
) -> None:
    """Validate error cases."""
    with pytest.raises(SystemExit):
        Config.from_args(args)
    # Unfortunately the error text is printed before the SystemExit is
    # raised, rather than being raised _with_ the systemexit, so we
    # need to capture stderr and check it for our expected text, if
    # any was specified in the test case.
    if exp_txt is not None:
        assert exp_txt in capsys.readouterr().err


def test_argv_conf():
    """Config uses argv if no args are provided."""
    orig_args = list(sys.argv)

    sys.argv = [sys.argv[0], "run", "-v", "--disable-fallback"]

    try:
        conf = Config.from_args()
        assert isinstance(conf, RunConfig)
        assert conf.verbosity == 1
        assert conf.disable_fallback is True
    finally:
        sys.argv = orig_args
