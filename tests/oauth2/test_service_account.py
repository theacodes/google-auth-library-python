# Copyright 2016 Google Inc. All rights reserved.
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

import datetime
import json
import os

import mock
import pytest

from google.auth import _helpers
from google.auth import crypt
from google.auth import jwt
from google.oauth2 import service_account


DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

with open(os.path.join(DATA_DIR, 'privatekey.pem'), 'rb') as fh:
    PRIVATE_KEY_BYTES = fh.read()

with open(os.path.join(DATA_DIR, 'public_cert.pem'), 'rb') as fh:
    PUBLIC_CERT_BYTES = fh.read()

with open(os.path.join(DATA_DIR, 'other_cert.pem'), 'rb') as fh:
    OTHER_CERT_BYTES = fh.read()

SERVICE_ACCOUNT_JSON_FILE = os.path.join(DATA_DIR, 'service_account.json')

with open(SERVICE_ACCOUNT_JSON_FILE, 'r') as fh:
    SERVICE_ACCOUNT_INFO = json.load(fh)


@pytest.fixture
def signer():
    return crypt.Signer.from_string(PRIVATE_KEY_BYTES, '1')


class TestCredentials:
    service_account_email = 'service-account@example.com'
    token_uri = 'https://example.com/oauth2/token'

    @pytest.fixture(autouse=True)
    def credentials(self, signer):
        self.credentials = service_account.Credentials(
            signer, self.service_account_email, self.token_uri)

    def test_from_service_account_info(self):
        with open(SERVICE_ACCOUNT_JSON_FILE, 'r') as fh:
            info = json.load(fh)

        credentials = service_account.Credentials.from_service_account_info(
            info)

        assert credentials._signer.key_id == info['private_key_id']
        assert credentials._service_account_email == info['client_email']
        assert credentials._token_uri == info['token_uri']

    def test_from_service_account_info_args(self):
        info = dict(SERVICE_ACCOUNT_INFO)

        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=['email', 'profile'], subject='subject',
            additional_claims={'meta': 'data'})

        assert credentials._signer.key_id == info['private_key_id']
        assert credentials._service_account_email == info['client_email']
        assert credentials._token_uri == info['token_uri']
        assert credentials._scopes == ['email', 'profile']
        assert credentials._subject == 'subject'
        assert credentials._additional_claims['meta'] == 'data'

    def test_from_service_account_bad_key(self):
        info = dict(SERVICE_ACCOUNT_INFO)
        info['private_key'] = 'garbage'

        with pytest.raises(ValueError) as excinfo:
            service_account.Credentials.from_service_account_info(info)

        assert excinfo.match(r'No key could be detected')

    def test_from_service_account_bad_format(self):
        info = {}

        with pytest.raises(KeyError):
            service_account.Credentials.from_service_account_info(info)

    def test_from_service_account_file(self):
        info = dict(SERVICE_ACCOUNT_INFO)

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_JSON_FILE)

        assert credentials._signer.key_id == info['private_key_id']
        assert credentials._service_account_email == info['client_email']
        assert credentials._token_uri == info['token_uri']

    def test_from_service_account_file_args(self):
        info = dict(SERVICE_ACCOUNT_INFO)

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_JSON_FILE, subject='subject',
            scopes=['email', 'profile'], additional_claims={'meta': 'data'})

        assert credentials._signer.key_id == info['private_key_id']
        assert credentials._service_account_email == info['client_email']
        assert credentials._token_uri == info['token_uri']
        assert credentials._scopes == ['email', 'profile']
        assert credentials._subject == 'subject'
        assert credentials._additional_claims['meta'] == 'data'

    def test_default_state(self):
        assert not self.credentials.valid
        # Expiration hasn't been set yet
        assert not self.credentials.expired
        # Scopes haven't been specified yet
        assert self.credentials.requires_scopes

    def test_sign_bytes(self):
        to_sign = b'123'
        signature = self.credentials.sign_bytes(to_sign)
        crypt.verify_signature(to_sign, signature, PUBLIC_CERT_BYTES)

    def test_create_scoped_sequence(self):
        credentials = self.credentials.with_scopes(['email', 'profile'])
        assert credentials._scopes == ['email', 'profile']

    def test_create_scoped_string(self):
        credentials = self.credentials.with_scopes('email')
        assert credentials._scopes == ['email']

    def test__make_authorization_grant_assertion(self):
        token = self.credentials._make_authorization_grant_assertion()
        payload = jwt.decode(token, PUBLIC_CERT_BYTES)
        assert payload['iss'] == self.service_account_email
        assert payload['aud'] == self.token_uri

    def test__make_authorization_grant_assertion_scoped(self):
        credentials = self.credentials.with_scopes(['email', 'profile'])
        token = credentials._make_authorization_grant_assertion()
        payload = jwt.decode(token, PUBLIC_CERT_BYTES)
        assert payload['scope'] == 'email profile'

    def test__make_authorization_grant_assertion_subject(self):
        credentials = self.credentials.with_subject('user@example.com')
        token = credentials._make_authorization_grant_assertion()
        payload = jwt.decode(token, PUBLIC_CERT_BYTES)
        assert payload['sub'] == 'user@example.com'

    @mock.patch('google.oauth2._client.jwt_grant')
    def test_refresh_success(self, jwt_grant_mock):
        jwt_grant_mock.return_value = (
            'token', _helpers.now() + datetime.timedelta(seconds=500), None)
        request_mock = mock.Mock()

        # Refresh credentials
        self.credentials.refresh(request_mock)

        # Check jwt grant call.
        assert jwt_grant_mock.called
        request, token_uri, assertion = jwt_grant_mock.call_args[0]
        assert request == request_mock
        assert token_uri == self.credentials._token_uri
        assert jwt.decode(assertion, PUBLIC_CERT_BYTES)
        # No further assertion done on the token, as there are separate tests
        # for checking the authorization grant assertion.

        # Check that the credentials have the token.
        assert self.credentials.token == 'token'

        # Check that the credentials are valid (have a token and are not
        # expired)
        assert self.credentials.valid

    @mock.patch('google.oauth2._client.jwt_grant')
    def test_before_request_refreshes(self, jwt_grant_mock):
        jwt_grant_mock.return_value = (
            'token', _helpers.now() + datetime.timedelta(seconds=500), None)
        request_mock = mock.Mock()

        # Credentials should start as invalid
        assert not self.credentials.valid

        # before_request should cause a refresh
        self.credentials.before_request(
            request_mock, 'GET', 'http://example.com?a=1#3', {})

        # The refresh endpoint should've been called.
        assert jwt_grant_mock.called

        # Credentials should now be valid.
        assert self.credentials.valid