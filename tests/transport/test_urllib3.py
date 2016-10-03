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

import flask
import mock
import pytest
from pytest_localserver.http import WSGIServer
from six.moves import http_client
import urllib3

from google.auth import exceptions
import google.auth.transport.urllib3


# .invalid will never resolve, see https://tools.ietf.org/html/rfc2606
NXDOMAIN = 'test.invalid'


@pytest.fixture
def server():
    """Provides a test HTTP server that is automatically created before
    a test and destroyed at the end. The server is serving a test application
    that can be used to verify requests."""
    # pylint: disable=unused-variable
    # (pylint thinks the flask routes are unusued.)
    app = flask.Flask(__name__)

    @app.route('/basic')
    def index():
        return 'Basic Content', http_client.OK, {'X-Test-Header': 'value'}

    @app.route('/server_error')
    def server_error():
        return 'Error', http_client.INTERNAL_SERVER_ERROR

    server = WSGIServer(application=app.wsgi_app)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def request():
    """Returns a google.auth.transport.urllib3 request object."""
    http = urllib3.PoolManager()
    yield google.auth.transport.urllib3.Request(http)


def test_request_basic(server, request):
    response = request(url=server.url + '/basic', method='GET')

    assert response.status == http_client.OK
    assert response.headers['x-test-header'] == 'value'
    assert response.data == b'Basic Content'


def test_request_error(server, request):
    response = request(url=server.url + '/server_error', method='GET')

    assert response.status == http_client.INTERNAL_SERVER_ERROR
    assert response.data == b'Error'


def test_connection_error(request):
    with pytest.raises(exceptions.TransportError):
        request(url='http://{}'.format(NXDOMAIN), method='GET')


def test_timeout():
    http = mock.Mock()
    request = google.auth.transport.urllib3.Request(http)
    request(url='http://example.com', method='GET', timeout=5)

    assert http.request.call_args[1]['timeout'] == 5
