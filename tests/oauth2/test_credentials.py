# Copyright 2016 Google Inc.
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

import mock
import pytest

from google.auth import _helpers
from google.oauth2 import credentials


class TestCredentials:
    token_uri = 'https://example.com/oauth2/token'

    @pytest.fixture(autouse=True)
    def credentials(self):
        self.credentials = credentials.Credentials(
            token=None, refresh_token='refresh_token',
            token_uri=self.token_uri, client_id='client_id',
            client_secret='client_secret')

    def test_default_state(self):
        assert not self.credentials.valid
        # Expiration hasn't been set yet
        assert not self.credentials.expired
        # Scopes aren't required for these credentials
        assert not self.credentials.requires_scopes

    def test_create_scoped(self):
        with pytest.raises(NotImplementedError):
            assert credentials == self.credentials.with_scopes('email')

    @mock.patch('google.oauth2._client.refresh_grant')
    @mock.patch('google.auth._helpers.now', return_value=datetime.datetime.min)
    def test_refresh_success(self, now_mock, refresh_grant_mock):
        expiry = _helpers.now() + datetime.timedelta(seconds=500)
        refresh_grant_mock.return_value = (
            # Access token
            'token',
            # New refresh token
            None,
            # Expiry,
            expiry,
            # Extra data
            {})
        request_mock = mock.Mock()

        # Refresh credentials
        self.credentials.refresh(request_mock)

        # Check jwt grant call.
        refresh_grant_mock.assert_called_with(
            request_mock, self.token_uri, 'refresh_token', 'client_id',
            'client_secret')

        # Check that the credentials have the token and expiry
        assert self.credentials.token == 'token'
        assert self.credentials.expiry == expiry

        # Check that the credentials are valid (have a token and are not
        # expired)
        assert self.credentials.valid
