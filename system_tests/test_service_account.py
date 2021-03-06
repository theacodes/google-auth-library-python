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

from google.auth import exceptions
from google.oauth2 import service_account
import pytest


@pytest.fixture
def credentials(service_account_file):
    yield service_account.Credentials.from_service_account_file(
        service_account_file)


def test_refresh_no_scopes(request, credentials):
    with pytest.raises(exceptions.RefreshError):
        credentials.refresh(request)


def test_refresh_success(request, credentials, token_info):
    credentials = credentials.with_scopes(['email', 'profile'])

    credentials.refresh(request)

    assert credentials.token

    info = token_info(credentials.token)

    assert info['email'] == credentials._service_account_email
    assert info['scope'] == (
        'https://www.googleapis.com/auth/userinfo.email '
        'https://www.googleapis.com/auth/userinfo.profile')
