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
import json

import mock
import pytest
from six.moves import http_client

from google.auth import _helpers
from google.auth import exceptions
from google.auth.compute_engine import _metadata

PATH = 'instance/service-accounts/default'


@pytest.fixture
def mock_request():
    request_mock = mock.Mock()

    def set_response(data, status=http_client.OK, headers=None):
        response = mock.Mock()
        response.status = status
        response.data = _helpers.to_bytes(data)
        response.headers = headers or {}
        request_mock.return_value = response
        return request_mock

    yield set_response


def test_ping_success(mock_request):
    request_mock = mock_request('')

    assert _metadata.ping(request_mock)

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_IP_ROOT,
        headers=_metadata._METADATA_HEADERS,
        timeout=_metadata._METADATA_DEFAULT_TIMEOUT,
        retries=False)


def test_ping_failure(mock_request):
    request_mock = mock_request('')
    request_mock.side_effect = Exception()

    assert not _metadata.ping(request_mock)


def test_get_success_json(mock_request):
    data = json.dumps({'foo': 'bar'})
    request_mock = mock_request(
        data, headers={'content-type': 'application/json'})

    result = _metadata.get(request_mock, PATH)

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_ROOT + PATH,
        headers=_metadata._METADATA_HEADERS)
    assert result['foo'] == 'bar'


def test_get_success_text(mock_request):
    data = 'foobar'
    request_mock = mock_request(data, headers={'content-type': 'text/plain'})

    result = _metadata.get(request_mock, PATH)

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_ROOT + PATH,
        headers=_metadata._METADATA_HEADERS)
    assert result == data


def test_get_failure(mock_request):
    request_mock = mock_request(
        'Metadata error', status=http_client.NOT_FOUND)

    with pytest.raises(exceptions.TransportError) as excinfo:
        _metadata.get(request_mock, PATH)

    assert excinfo.match(r'Metadata error')

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_ROOT + PATH,
        headers=_metadata._METADATA_HEADERS)


@mock.patch('google.auth._helpers.now', return_value=datetime.datetime.min)
def test_get_service_account_token(now, mock_request):
    request_mock = mock_request(
        json.dumps({'access_token': 'token', 'expires_in': 500}),
        headers={'content-type': 'application/json'})

    token, expiry = _metadata.get_service_account_token(request_mock)

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_ROOT + PATH + '/token',
        headers=_metadata._METADATA_HEADERS)
    assert token == 'token'
    assert expiry == now() + datetime.timedelta(seconds=500)


def test_get_service_account_info(mock_request):
    request_mock = mock_request(
        json.dumps({'foo': 'bar'}),
        headers={'content-type': 'application/json'})

    info = _metadata.get_service_account_info(request_mock)

    request_mock.assert_called_once_with(
        'GET',
        _metadata._METADATA_ROOT + PATH + '/?recursive=True',
        headers=_metadata._METADATA_HEADERS)

    assert info['foo'] == 'bar'
