# Copyright 2015 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Application default credentials."""

import json
import os

from six.moves import configparser
import urllib3

from google.auth import compute_engine
from google.auth import exceptions
from google.auth import jwt
from google.auth.compute_engine import _metadata
import google.auth.transport.urllib3
import google.oauth2.credentials

# Environment variable for explicit application default credentials and project
# ID.
_CREDENTIALS_ENV = 'GOOGLE_APPLICATION_CREDENTIALS'
_PROJECT_ENV = 'GCLOUD_PROJECT'

# Valid types accepted for file-based credentials.
_AUTHORIZED_USER_TYPE = 'authorized_user'
_SERVICE_ACCOUNT_TYPE = 'service_account'
_VALID_TYPES = (_AUTHORIZED_USER_TYPE, _SERVICE_ACCOUNT_TYPE)

# The Google OAuth 2.0 token endpoint. Used for authorized user credentials.
_GOOGLE_OAUTH2_TOKEN_ENDPOINT = 'https://accounts.google.com/o/oauth2/token'

# The ~/.config subdirectory containing gcloud credentials.
_CLOUDSDK_CONFIG_DIRECTORY = 'gcloud'
# The environment variable name which can replace ~/.config if set.
_CLOUDSDK_CONFIG_ENV = 'CLOUDSDK_CONFIG'
# The name of the file in the Cloud SDK config that contains default
# credentials.
_CLOUDSDK_CREDENTIALS_FILENAME = 'application_default_credentials.json'
# The name of the file in the Cloud SDK config that contains the
# active configurations
_CLOUDSDK_ACTIVE_CONFIG_FILENAME = os.path.join(
    'configurations', 'config_default')
# The config section and key for the project ID in the cloud SDK config.
_CLOUDSDK_PROJECT_CONFIG_SECTION = 'core'
_CLOUDSDK_PROJECT_CONFIG_KEY = 'project'


# Help message when no credentials can be found.
_HELP_MESSAGE = (
    'Could not automatically determine credentials. Please set {env} or '
    'explicitly create credential and re-run the application. For more '
    'information, please see https://developers.google.com/accounts/docs'
    '/application-default-credentials.'.format(env=_CREDENTIALS_ENV))


def _load_credentials_from_file(filename):
    with open(filename) as file_obj:
        try:
            info = json.load(file_obj)
        except ValueError as exc:
            raise exceptions.DefaultCredentialsError(
                'File {} is not a valid json file.'.format(filename), exc)

    # The type key should indicate that the file is either a service account
    # credentials file or an authorized user credentials file.
    credential_type = info.get('type')

    if credential_type == _AUTHORIZED_USER_TYPE:
        credentials = google.oauth2.credentials.Credentials(
            None,
            refresh_token=info['refresh_token'],
            token_uri=_GOOGLE_OAUTH2_TOKEN_ENDPOINT,
            client_id=info['client_id'],
            client_secret=info['client_secret'])
        # Authorized user credentials do not contain the project ID.
        return credentials, None

    if credential_type == _SERVICE_ACCOUNT_TYPE:
        # TODO: This should actually be a weird polymorphic class that
        # is jwt.Credentials until create_scoped is called, then it becomes
        # service_account.Credentials.
        credentials = jwt.Credentials.from_service_account_info(info)
        return credentials, info.get('project_id')

    else:
        raise exceptions.DefaultCredentialsError(
            'The file {file} does not have a valid type. '
            'Type is {type}, expected one of {valid_types}.'.format(
                file=filename, type=credential_type, valid_types=_VALID_TYPES))


def _get_explicit_environ_credentials():
    explicit_file = os.environ.get(_CREDENTIALS_ENV)
    if explicit_file is not None:
        return _load_credentials_from_file(os.environ[_CREDENTIALS_ENV])
    else:
        return None, None


def _get_gcloud_sdk_project_id(config_path):
    config_file = os.path.join(config_path, _CLOUDSDK_ACTIVE_CONFIG_FILENAME)

    if not os.path.exists(config_file):
        return None

    config = configparser.RawConfigParser()

    try:
        config.read(config_file)
    except configparser.Error:
        return None

    if config.has_section(_CLOUDSDK_PROJECT_CONFIG_SECTION):
        return config.get(
            _CLOUDSDK_PROJECT_CONFIG_SECTION, _CLOUDSDK_PROJECT_CONFIG_KEY)


def _get_gcloud_sdk_credentials():
    # Get the Cloud SDK's configuration path.
    config_path = os.getenv(_CLOUDSDK_CONFIG_ENV)
    if config_path is None:
        if os.name == 'nt':
            if 'APPDATA' in os.environ:
                config_path = os.path.join(
                    os.environ['APPDATA'], _CLOUDSDK_CONFIG_DIRECTORY)
            else:
                # This should never happen unless someone is really
                # messing with things, but we'll cover the case anyway.
                drive = os.environ.get('SystemDrive', 'C:')
                config_path = os.path.join(
                    drive, '\\', _CLOUDSDK_CONFIG_DIRECTORY)
        else:
            config_path = os.path.join(
                os.path.expanduser('~'), '.config', _CLOUDSDK_CONFIG_DIRECTORY)

    # Check the config path for the credentials file.
    credentials_filename = os.path.join(
        config_path, _CLOUDSDK_CREDENTIALS_FILENAME)

    if not os.path.exists(credentials_filename):
        return None, None

    credentials, project_id = _load_credentials_from_file(
        credentials_filename)

    if not project_id:
        project_id = _get_gcloud_sdk_project_id(config_path)

    return credentials, project_id


def _get_gae_credentials():
    return None, None


def _get_gce_credentials():
    # TODO: Ping now requires a request argument. Figure out how to deal with
    # that. Temporarily using the urllib3 transport.
    http = urllib3.PoolManager()
    request = google.auth.transport.urllib3.Request(http)

    if _metadata.ping(request=request):
        # Get the project ID.
        try:
            project_id = _metadata.get(request, 'project/project-id')
        except exceptions.TransportError:
            project_id = None

        return compute_engine.Credentials(), project_id
    else:
        return None, None


def default():
    """Gets the default credentials for the current environment.

    Returns:
        google.auth.credentials.Credentials: the current environment's
            credentials.

    Raises:
        google.auth.exceptions.DefaultCredentialsError:
            If no credentials were found, or if the credentials found were
            invalid.
    """
    explicit_project_id = os.environ.get(_PROJECT_ENV)

    checkers = (
        _get_explicit_environ_credentials,
        _get_gcloud_sdk_credentials,
        _get_gae_credentials,
        _get_gce_credentials)

    for checker in checkers:
        credentials, project_id = checker()
        if credentials is not None:
            return credentials, explicit_project_id or project_id

    raise exceptions.DefaultCredentialsError(_HELP_MESSAGE)
