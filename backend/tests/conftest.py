import logging
from pathlib import Path
import os

# Set test environment variables FIRST, before any imports
os.environ["CELERY_TRACK_STARTED"] = "True"
os.environ["CELERY_IGNORE_RESULT"] = "False"
os.environ["CELERY_TASK_RESULT_EXPIRES"] = "6000"

# Set required application config environment variables for tests
test_env_vars = {
    'ADMIN_LOGIN': 'test_admin',
    'ADMIN_PASSWORD': 'test_password',
    'JWT_SECRET_KEY': 'test_jwt_secret_key',
    'AMQP_USERNAME': 'test_user',
    'AMQP_PASSWORD': 'test_password',
    'AMQP_HOST': 'localhost',
    'AMQP_PORT': '6379',
    'POSTGRES_DB': 'test_db',
    'POSTGRES_USER': 'test_user', 
    'POSTGRES_PASSWORD': 'test_password',
    'POSTGRES_HOST': 'localhost',
}

for key, value in test_env_vars.items():
    if key not in os.environ:
        os.environ[key] = value

pytest_plugins = ("celery.contrib.pytest", )

import app.config
import app.db.session
import tests.config as test_config
import pytest
from app import modules_load

# Clear the cache before injecting test config
app.config.get_config.cache_clear()
app.config.get_config = test_config.get_test_config
app.db.session.get_session = test_config.get_test_session

# we have to import fixtures only after injecting test config
modules_load.asterisk(Path(__file__).parent / "fixtures", "tests.fixtures", globals())
from tests.fixtures.client import TestClientExternal  # just to remove warning

# - in fact it is already imported with `modules_load`

log = logging.getLogger()
logging.basicConfig(format="%(asctime)s - %(message)s", datefmt="%d-%b-%y %H:%M:%S", level=logging.INFO)


def pytest_addoption(parser):
    """
    py.test options
    """
    parser.addoption(
        "--host",
        type=str,
        dest="host",
        help="""External server to test. Run tests for the host. Skips tests marked as unittests.""",
    )
    parser.addoption(
        "--header",
        type=str,
        nargs="*",
        dest="headers",
        help="""HTTP headers to add to all API requests.""",
    )


def pytest_report_header(config):
    host = config.getoption("host")
    if host is not None:
        host = TestClientExternal.url("")
    return (
        f'{">" * 5} '
        f'{"unittests" if host is None else "Testing server " + host} '
        f'{"<" * 5}\n'
    )


def pytest_cmdline_main(config):
    """
    After command line is parsed
    """
    test_config._config = test_config.TestConfig(config=config)


def pytest_collection_modifyitems(config, items):
    if config.getoption("host"):
        # Skip un-relevant tests if we test external server (option `--host`)
        skip_unittests = pytest.mark.skip(
            reason="Skip tests for local code in server test mode (--host)"
        )
        skip_non_api = pytest.mark.skip(
            reason="Skip non API tests in server test mode (--host)"
        )
        for item in items:
            if "unittest" in item.keywords:
                item.add_marker(skip_unittests)
            if "client" not in item.fixturenames:
                item.add_marker(skip_non_api)

    else:  # if this is not external server test then add db fixture to prevent DB modifications by tests
        FIXTURES_TO_PROTECT_DB = ["client", "celery_app", "celery_worker"]
        for item in items:
            if (
                any(fixture in item.fixturenames for fixture in FIXTURES_TO_PROTECT_DB)
                and "does_not_change_db" not in item.keywords
            ):
                item.fixturenames.append("db")
