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

"""OAuth 2.0 Credentials
"""

from google.auth import _helpers
from google.auth import credentials
from google.oauth2 import _client


class Credentials(credentials.ScopedCredentials,
                  credentials.Credentials):
    """OAuth 2.0 Credentials
    """

    def __init__(self, token, refresh_token=None, token_uri=None,
                 client_id=None, client_secret=None, scopes=None):
        """Constructor

        Args:
            scopes (Union[str, Sequence]): Scopes to request.
            token_uri (str): The OAuth 2.0 Token URI.
        """
        super(Credentials, self).__init__()
        self.token = token
        self._refresh_token = refresh_token
        self._scopes = scopes
        self._token_uri = token_uri
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def requires_scopes(self):
        """Returns False, OAuth 2.0 credentials have their scopes set when
        the initial token is requested and can not be changed."""
        return False

    def with_scopes(self, scopes):
        """Raises NotImplementedError, OAuth 2.0 credentials have their scopes
        set when the initial token is requested and can not be changed."""
        raise NotImplementedError(
            'OAuth 2.0 Credentials can not modify their scopes.')

    @_helpers.copy_docstring(credentials.Credentials)
    def refresh(self, request):
        access_token, refresh_token, expiry, _ = _client.refresh_grant(
            request, self._token_uri, self._refresh_token, self._client_id,
            self._client_secret)

        self.token = access_token
        self.refresh_token = refresh_token
        self.expiry = expiry
