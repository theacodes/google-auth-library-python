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

"""Transport adapter for urllib3."""

from __future__ import absolute_import

import logging

import urllib3
import urllib3.exceptions
import urllib3.request

from google.auth import exceptions
from google.auth import transport

_LOGGER = logging.getLogger(__name__)


class Request(transport.Request):
    """urllib3 request adapter

    Args:
        http (urllib3.requests.RequestMethods): An instance of any urllib3
            class that implements :class:`~urllib3.requests.RequestMethods`,
            usually :class:`urllib3.PoolManager`.
    """
    def __init__(self, http):
        self.http = http

    def __call__(self, url, method='GET', body=None, headers=None,
                 timeout=None, **kwargs):
        """Make an HTTP request using urllib3.

        Args:
            url (str): The URI to be requested.
            method (str): The HTTP method to use for the request. Defaults
                to 'GET'.
            body (bytes): The payload / body in HTTP request.
            headers (Mapping): Request headers.
            timeout (Optional(int)): The number of seconds to wait for a
                response from the server. If not specified or if None, the
                urllib3 default timeout will be used.
            kwargs: Additional arguments passed throught to the underlying
                urllib3 :meth:`urlopen` method.

        Returns:
            Response: The HTTP response.

        Raises:
            google.auth.exceptions.TransportError: If any exception occurred.
        """
        # urllib3 uses a sentinel default value for timeout, so only set it if
        # specified.
        if timeout is not None:
            kwargs['timeout'] = timeout

        try:
            return self.http.request(
                method, url, body=body, headers=headers, **kwargs)
        except urllib3.exceptions.HTTPError as exc:
            raise exceptions.TransportError(exc)


class AuthorizedHttp(urllib3.request.RequestMethods):
    """An authorized urllib3 HTTP class.

    Implements :class:`urllib3.request.RequestMethods` and can be used just
    like any other :class:`urllib3.PoolManager`.

    Provides an implementation of :meth:`urlopen` that handles adding the
    credentials to the request headers and refreshing credentials as needed.

    Args:
        credentials (google.auth.credentials.Credentials): The credentials to
            add to the request.
        http (urllib3.PoolManager): The underlying HTTP object to
            use to make requests.
        refresh_status_codes (Sequence): Which HTTP status code indicate that
            credentials should be refreshed and the request should be retried.
    """
    def __init__(self, credentials, http=None,
                 refresh_status_codes=transport.DEFAULT_REFRESH_STATUS_CODES,
                 max_refresh_attempts=transport.DEFAULT_MAX_REFRESH_ATTEMPTS):
        self.http = http
        self.credentials = credentials
        self.refresh_status_codes = refresh_status_codes
        self.max_refresh_attempts = max_refresh_attempts
        self.__request = Request(self.http)

    def urlopen(self, method, url, body=None, headers=None, **kwargs):
        """Implementation of urllib3's urlopen."""

        # Use a kwarg for this instead of an attribute to maintain
        # thread-safety.
        _credential_refresh_attempt = kwargs.pop(
            '_credential_refresh_attempt', 0)

        if headers is None:
            headers = self.headers or {}

        # Make a copy of the headers. They will be modified by the credentials
        # and we want to pass the original headers if we recurse.
        request_headers = headers.copy()

        self.credentials.before_request(
            self.__request, method, url, request_headers)

        response = self.http.urlopen(
            method, url, body=body, headers=request_headers, **kwargs)

        # If the response indicated that the credentials needed to be
        # refreshed, then refresh the credentials and re-attempt the
        # request.
        # A stored token may expire between the time it is retrieved and
        # the time the request is made, so we may need to try twice.
        # The reason urllib3's retries aren't used is because they
        # don't allow you to modify the request headers. :/
        if (response.status in self.refresh_status_codes
                and _credential_refresh_attempt < self.max_refresh_attempts):

            _LOGGER.info(
                'Refreshing credentials due to a %s response. Attempt %s/%s.',
                response.status, _credential_refresh_attempt + 1,
                self.max_refresh_attempts)

            self.credentials.refresh(self.__request)

            # Recurse. Pass in the original headers, not our modified set.
            return self.urlopen(
                method, url, body=body, headers=headers,
                _credential_refresh_attempt=_credential_refresh_attempt + 1,
                **kwargs)

        return response

    # Proxy methods for compliance with the urllib3.PoolManager interface

    def __enter__(self):
        """Proxy to self.http."""
        return self.http.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Proxy to self.http."""
        return self.http.__exit__(exc_type, exc_val, exc_tb)

    @property
    def headers(self):
        """Proxy to self.http."""
        return self.http.headers

    @headers.setter
    def headers(self, value):
        """Proxy to self.http."""
        self.http.headers = value
