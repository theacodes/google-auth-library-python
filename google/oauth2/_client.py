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

"""OAuth 2.0 client.

This is a client for interacting with an OAuth 2.0 authorization servers's
token endpoint.

For more information about the token endpoint, see
`Section 3.1 of rfc6749 <https://tools.ietf.org/html/rfc6749#section-3.2>`_
"""

import datetime
import json

from six.moves import http_client
from six.moves import urllib

from google.auth import _helpers
from google.auth import exceptions

_JWT_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:jwt-bearer'
_REFRESH_GRANT_TYPE = 'refresh_token'


def _handle_error_response(response_data):
    # Try to decode the response and extract details.
    try:
        error_data = json.loads(response_data)
        error_details = ': '.join([
            error_data['error'],
            error_data.get('error_description')])
    # If not details could be extracted, use the response data.
    except (KeyError, ValueError):
        error_details = response_data

    raise exceptions.RefreshError(error_details)


def _parse_expiry(response_data):
    expires_in = response_data.get('expires_in', None)
    if expires_in:
        return _helpers.now() + datetime.timedelta(
            seconds=expires_in)
    else:
        return None


def _token_endpoint_request(request, token_uri, body):
    body = urllib.parse.urlencode(body)
    headers = {
        'content-type': 'application/x-www-form-urlencoded',
    }

    response = request(
        method='POST', url=token_uri, headers=headers, body=body)

    response_body = response.data.decode('utf-8')

    if response.status != http_client.OK:
        _handle_error_response(response_body)

    response_data = json.loads(response_body)

    return response_data


def jwt_grant(request, token_uri, assertion):
    """Implements the JWT Profile for OAuth 2.0 Authorization Grants.

    For more details, see https://tools.ietf.org/html/rfc7523#section-4.
    """
    body = {
        'assertion': assertion,
        'grant_type': _JWT_GRANT_TYPE,
    }

    response_data = _token_endpoint_request(request, token_uri, body)

    access_token = response_data['access_token']
    expiry = _parse_expiry(response_data)

    return access_token, expiry, response_data


def refresh_grant(request, token_uri, refresh_token, client_id, client_secret):
    """Implements the OAuth 2.0 refresh token grant.

    For more details, see https://tools.ietf.org/html/rfc6749#section-6
    """
    body = {
        'grant_type': _REFRESH_GRANT_TYPE,
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
    }

    response_data = _token_endpoint_request(request, token_uri, body)

    access_token = response_data['access_token']
    refresh_token = response_data.get('refresh_token', refresh_token)
    expiry = _parse_expiry(response_data)

    return access_token, refresh_token, expiry, response_data
