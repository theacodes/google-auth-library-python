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

from google.auth import credentials


class CredentialsImpl(credentials.Credentials):
    def refresh(self, http):
        self.token = http


def test_credentials_constructor():
    credentials = CredentialsImpl()
    assert not credentials.token
    assert not credentials.expiry
    assert not credentials.expired
    assert not credentials.valid


def test_expired_and_valid():
    credentials = CredentialsImpl()
    credentials.token = 'token'

    assert credentials.valid
    assert not credentials.expired

    credentials.expiry = (
        datetime.datetime.utcnow() - datetime.timedelta(seconds=60))

    assert not credentials.valid
    assert credentials.expired


def test_before_request():
    credentials = CredentialsImpl()
    http = 'token'
    headers = {}

    # First call should call refresh, setting the token.
    credentials.before_request(http, 'http://example.com', 'GET', headers)
    assert credentials.valid
    assert credentials.token == 'token'
    assert headers[b'authorization'] == 'Bearer token'

    http = 'token2'
    headers = {}

    # Second call shouldn't call refresh.
    credentials.before_request(http, 'http://example.com', 'GET', headers)
    assert credentials.valid
    assert credentials.token == 'token'
    assert headers[b'authorization'] == 'Bearer token'


class ScopedCredentialsImpl(credentials.ScopedCredentials, CredentialsImpl):
    @property
    def requires_scopes(self):
        return super(ScopedCredentialsImpl, self).requires_scopes

    def with_scopes(self, scopes):
        raise NotImplementedError


def test_scoped_credentials_constructor():
    credentials = ScopedCredentialsImpl()
    assert credentials._scopes is None


def test_scoped_credentials_scopes():
    credentials = ScopedCredentialsImpl()

    credentials._scopes = ['one', 'two']
    assert credentials.has_scopes(['one'])
    assert credentials.has_scopes(['two'])
    assert credentials.has_scopes(['one', 'two'])
    assert not credentials.has_scopes(['three'])

    credentials._scopes = 'one two'
    assert credentials.has_scopes(['one'])
    assert credentials.has_scopes(['two'])
    assert credentials.has_scopes(['one', 'two'])
    assert not credentials.has_scopes(['three'])


def test_scoped_credentials_requires_scopes():
    credentials = ScopedCredentialsImpl()
    assert not credentials.requires_scopes
