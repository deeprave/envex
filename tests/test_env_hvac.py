# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest

from envex.env_hvac import SecretsManager

# Constants for testing
BASE_URL = "http://vault.example.com:8200"
TOKEN = "s.1234567890abcdef"
CERT = ("path/to/cert.pem", "path/to/key.pem")
VERIFY = True
BASE_PATH = "base/path"
ENGINE = "kv"
MOUNT_POINT = "secret"


@pytest.fixture
def mock_init_client():
    # Mock the hvac.Client class
    class MockClient:
        def __init__(self, *args, **kwargs):
            self.authenticated = True
            self.secrets = {}
            self.seal_status = {"sealed": False}

        def is_authenticated(self):
            return self.authenticated

        def read(self, path):
            return {"data": {"data": self.secrets.get(path)}}

        def write(self, path, **kwargs):
            self.secrets[path] = kwargs

        def delete(self, path):
            self.secrets.pop(path, None)

        def sys(self):
            return MagicMock(list_mounted_secrets_engines=MagicMock(return_value={"data": {}}))

    with patch("hvac.Client", new=MockClient):
        yield MockClient()


test_params = [
    # ID: Happy-Path-1
    (
        BASE_URL,
        TOKEN,
        CERT,
        VERIFY,
        BASE_PATH,
        ENGINE,
        MOUNT_POINT,
        SecretsManager.join(MOUNT_POINT, "data", BASE_PATH),
    ),
    # ID: Happy-Path-2
    (
        BASE_URL,
        TOKEN,
        None,
        VERIFY,
        None,
        None,
        None,
        SecretsManager.join("secret", "data"),
    ),
    # ID: Edge-Case-1
    (
        BASE_URL,
        TOKEN,
        CERT,
        "/path/to/ca.pem",
        BASE_PATH,
        ENGINE,
        MOUNT_POINT,
        SecretsManager.join(MOUNT_POINT, "data", BASE_PATH),
    ),
    # ID: Error-Case-1
    (
        None,
        None,
        None,
        VERIFY,
        BASE_PATH,
        ENGINE,
        MOUNT_POINT,
        SecretsManager.join(MOUNT_POINT, "data", BASE_PATH),
    ),
]


@pytest.mark.parametrize(
    "url, token, cert, verify, base_path, engine, mount_point, expected_base_path",
    test_params,
)
def test_secrets_manager_initialization(
    url,
    token,
    cert,
    verify,
    base_path,
    engine,
    mount_point,
    expected_base_path,
    mock_init_client,
):
    # Arrange
    with patch("envex.env_hvac.os.getenv", side_effect=lambda k, v=None: v):
        with patch("envex.env_hvac.expand", side_effect=lambda v: v):
            with patch("envex.env_hvac.read_pem", side_effect=lambda k, req: None):
                # Act
                manager = SecretsManager(
                    url=url,
                    token=token,
                    cert=cert,
                    verify=verify,
                    base_path=base_path,
                    engine=engine,
                    mount_point=mount_point,
                )

                # Assert
                assert manager.base_path == expected_base_path


# Fixture to create a mock client and attach it to the object under test
@pytest.fixture
def secrets_manager():
    # Mock class to simulate the client's behaviour
    class MockClient:
        seal_status = {"sealed": False}

        def read(self, path):
            mock_responses = {
                "secret/data/valid/path": {"data": {"data": {"secret_key": "secret_value"}}},
                "secret/data/valid/empty": {"data": {"data": {}}},
                "secret/data/no/data": {},
                None: None,
            }
            return mock_responses.get(path)

        def write(self, path, **kwargs):
            pass

        def write_data(self, path, **kwargs):
            pass

        def delete(self, path):
            pass

        @property
        def sys(self):
            class Sys:
                def seal(self):
                    MockClient.seal_status["sealed"] = True
                    return MockClient.seal_status

                def unseal(self, keys, root_token):
                    MockClient.seal_status["sealed"] = False
                    return MockClient.seal_status

                def submit_unseal_keys(self, keys, root_token):
                    MockClient.seal_status["sealed"] = False
                    return MockClient.seal_status

            return Sys()

    class SecretsManagerEx(SecretsManager):
        def __init__(self):
            super().__init__()
            self._client = None

        @property
        def client(self):
            if not self._client:
                self._client = MockClient()
            return self._client

    return SecretsManagerEx()


# Parametrized test cases
@pytest.mark.parametrize(
    "test_input, test_input_key, expected_output, test_id",
    [
        # Happy path tests with various realistic test values
        (
            "valid/path",
            "secret_key",
            {"secret_key": "secret_value"},
            "happy_path_valid_data",
        ),
        ("valid/empty", "secret_key", {}, "happy_path_empty_data"),
        # Edge cases
        ("", "", {}, "edge_case_no_path"),
        ("no/data", "", {}, "edge_case_no_data_in_response"),
        # Error cases
        (None, None, {}, "error_case_none_path"),
    ],
)
def test_get_secrets(secrets_manager, test_input, test_input_key, expected_output, test_id):
    # Act
    result = secrets_manager.get_secrets(test_input)

    # Assert
    assert result == expected_output, f"get_secrets({test_input}) failed for test_id: {test_id}"

    # Act
    result = secrets_manager.get_secret(test_input_key)

    # Assert
    assert result == expected_output.get(
        test_input_key, None
    ), f"get_secret({test_input_key}) failed for test_id: {test_id}"

    # Act
    secrets_manager.delete_secrets(test_input)

    assert secrets_manager.secrets == {}


@pytest.mark.parametrize(
    "test_input_key, expected_inital_output, modified_value, test_id",
    [
        # Happy path tests with various test values
        (
            "not_a_secret_key",
            None,
            "new_value",
            "happy_path_valid_data",
        ),
        ("secret_key", None, None, "happy_path_empty_data"),
        # Edge cases
        ("", None, None, "edge_case_no_path"),
        ("", None, None, "edge_case_no_data_in_response"),
        # Error cases
        (None, None, None, "error_case_none_path"),
    ],
)
def test_get_set_secret(secrets_manager, test_input_key, expected_inital_output, modified_value, test_id):
    result = secrets_manager.get_secret(test_input_key)
    assert result == expected_inital_output, f"get_secret({test_input_key}) failed for test_id: {test_id}"

    secrets_manager.set_secret(test_input_key, modified_value)
    result = secrets_manager.get_secret(test_input_key)
    assert result == modified_value, f"get_secret({test_input_key}) failed for test_id: {test_id}"

    result = list(secrets_manager.list_secrets())
    expected_result = [test_input_key] if modified_value else []
    assert result == expected_result, f"list_secrets() failed for test_id: {test_id}"

    secrets_manager.delete_secret(test_input_key)
    assert secrets_manager.secrets == {}, f"delete_secret({test_input_key}) failed for test_id: {test_id}"

    result = list(secrets_manager.list_secrets())
    assert not result


def test_seal_unseal(secrets_manager):
    secrets_manager.seal()
    assert secrets_manager.sealed
    secrets_manager.unseal(None, None)
    assert not secrets_manager.sealed
