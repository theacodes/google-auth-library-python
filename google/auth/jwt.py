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

"""JSON Web Tokens

Provides support for creating (encoding) and verifying (decoding) JWTs,
especially JWTs generated and consumed by Google infrastructure.

Also provides a :class:`Credentials` class that uses JWTs as authentication
bearer tokens.

See https://tools.ietf.org/html/rfc7519 for more details on JWTs.

TODO: Usage samples
"""

import base64
import collections
import datetime
import json

from six.moves import urllib

from google.auth import crypt
from google.auth import _helpers
from google.auth import credentials


_DEFAULT_TOKEN_LIFETIME_SECS = 3600  # 1 hour in sections
CLOCK_SKEW_SECS = 300  # 5 minutes in seconds


def encode(signer, payload, header=None, key_id=None):
    """Make a signed JWT.

    Args:
        signer (google.auth.crypt.Signer): The signer used to sign the JWT.
        payload (Mapping): The JWT payload.
        header (Mapping): Additional JWT header payload.
        key_id (str): The key id to add to the JWT header. If the
            signer has a key id it will be used as the default. If this is
            specified, it'll override the signer's key id.

    Returns:
        bytes: The encoded JWT.
    """
    if not header:
        header = {}

    if key_id is None:
        key_id = signer.key_id

    header.update({'typ': 'JWT', 'alg': 'RS256'})

    if key_id is not None and key_id is not False:
        header['kid'] = key_id

    segments = [
        base64.urlsafe_b64encode(json.dumps(header).encode('utf-8')),
        base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8')),
    ]

    signing_input = b'.'.join(segments)
    signature = signer.sign(signing_input)
    segments.append(base64.urlsafe_b64encode(signature))

    return b'.'.join(segments)


def _decode_jwt_segment(encoded_section):
    """Decodes a single JWT segment."""
    section_bytes = base64.urlsafe_b64decode(encoded_section)
    try:
        return json.loads(section_bytes.decode('utf-8'))
    except:
        raise ValueError('Can\'t parse segment: {0}'.format(section_bytes))


def _unverified_decode(token):
    """Decodes a token and does no verification.

    Args:
        token (Union[str, bytes]): The encoded JWT.

    Returns:
        Tuple(str, str, str, str): header, payload, signed_setion, and
            signature.

    Raises:
        ValueError: if there are an incorrect amount of segments in the token.
    """
    token = _helpers.to_bytes(token)

    if token.count(b'.') != 2:
        raise ValueError(
            'Wrong number of segments in token: {0}'.format(token))

    encoded_header, encoded_payload, signature = token.split(b'.')
    signed_section = encoded_header + b'.' + encoded_payload
    signature = base64.urlsafe_b64decode(signature)

    # Parse segments
    header = _decode_jwt_segment(encoded_header)
    payload = _decode_jwt_segment(encoded_payload)

    return header, payload, signed_section, signature


def decode_header(token):
    """Return the decoded header of a token.

    No verification is done. This is useful to extract the key id from
    the header in order to acquire the appropriate certificate to verify
    the token.

    Args:
        token (Union[str, bytes]): the encoded JWT.

    Returns:
        Mapping: The decoded JWT header.
    """
    header, _, _, _ = _unverified_decode(token)
    return header


def _verify_iat_and_exp(payload):
    """Verifies the iat (Issued At) and exp (Expires) claims in a token
    payload.

    Args:
        payload (mapping): The JWT payload.

    Raises:
        ValueError: if any checks failed.
    """
    now = _helpers.datetime_to_secs(_helpers.now())

    # Make sure the iat and exp claims are present
    for key in ('iat', 'exp'):
        if key not in payload:
            raise ValueError(
                'Token does not contain required claim {}'.format(key))

    # Make sure the token wasn't issued in the future
    iat = payload['iat']
    earliest = iat - CLOCK_SKEW_SECS
    if now < earliest:
        raise ValueError('Token used too early, {} < {}'.format(now, iat))

    # Make sure the token wasn't issue in the past
    exp = payload['exp']
    latest = exp + CLOCK_SKEW_SECS
    if latest < now:
        raise ValueError('Token expired, {} < {}'.format(latest, now))


def decode(token, certs=None, verify=True, audience=None):
    """Decode and verify a JWT.

    Args:
        token (string): The encoded JWT.
        certs (Union[str, bytes, or Mapping]): The certificate used to
            validate. If bytes or string, it must the the public key
            certificate in PEM format. If a mapping, it must be a mapping of
            key IDs to public key certificates in PEM format. The mapping must
            contain the same key ID that's specified in the token's header.
        verify (bool): Whether to perform signature and claim validation.
            Verification is done by default.
        audience (str): The audience claim, 'aud', that this JWT should
            contain. If None then the JWT's 'aud' parameter is not verified.

    Returns:
        Mapping: The deserialized JSON payload in the JWT.

    Raises:
        ValueError: if any verification checks failed.
    """
    header, payload, signed_section, signature = _unverified_decode(token)

    if not verify:
        return payload

    # If certs is specified as a dictionary of key IDs to certificates, then
    # use the certificate identified by the key ID in the token header.
    if isinstance(certs, collections.Mapping):
        key_id = header.get('kid')
        if key_id:
            if key_id not in certs:
                raise ValueError(
                    'Certificate for key id {} not found.'.format(key_id))
            certs = [certs[key_id]]
        # If there's no key id in the header, check against all of the certs.
        else:
            certs = certs.values()

    # Verify that the signature matches the message.
    if not crypt.verify_signature(signed_section, signature, certs):
        raise ValueError('Could not verify token signature.')

    # Verify the issued at and created times in the payload.
    _verify_iat_and_exp(payload)

    # Check audience.
    if audience is not None:
        claim_audience = payload.get('aud')
        if audience != claim_audience:
            raise ValueError(
                'Token has wrong audience {}, expected {}'.format(
                    claim_audience, audience))

    return payload


class Credentials(credentials.SigningCredentials,
                  credentials.Credentials):
    """Credentials that use a JWT as the bearer token.

    The constructor arguments determine the content of the JWT token that is
    sent with requests. Usually, you'll construct these credentials with
    one of the helper constructors::

        credentials = jwt.Credentials.from_service_account_file(
            'service-account.json')

    Or if you already have the service account file loaded::

        service_account_info = json.load(open('service_account.json'))
        credentials = jwt.Credentials.from_service_account_info(
            service_account_info)

    Both helper methods pass on arguments to the constructor, so you can
    specific the claims::

        credentials = jwt.Credentials.from_service_account_file(
            'service-account.json',
            audience='https://speech.googleapis.com',
            additional_claims={'meta': 'data'})

    You can also construct the credentials directly if you have a
    :class:`~google.auth.crypt.Signer` instance::

        credentials = jwt.Credentials(
            signer, issuer='your-issuer', subject='your-subject')

    The claims are considered immutable. If you want to modify the claims,
    you can easily create another instance using :meth:`with_claims`::

        new_credentials = credentials.with_claims(
            audience='https://vision.googleapis.com')

    Note that JWT credentials will also set the audience claim on demand. If no
    audience is specified when creating the credentials, then whenever a
    request is made the credentials will automatically generate a one-time
    JWT with the request URI as the audience.
    """

    def __init__(self, signer, issuer=None, subject=None, audience=None,
                 additional_claims=None,
                 token_lifetime=_DEFAULT_TOKEN_LIFETIME_SECS):
        """Constructor

        Args:
            signer (google.auth.crypt.Signer): The signer used to sign JWTs.
            issuer (str): The `iss` claim.
            subject (str): The `sub` claim.
            audience (str): the `aud` claim. If not specified, a new
                JWT will be generated for every request and will use
                the request URI as the audience.
            additional_claims (Mapping): Any additional claims for the JWT
                payload.
            token_lifetime (int): The amount of time in seconds for
                which the token is valid. Defaults to 1 hour.
        """
        super(Credentials, self).__init__()
        self._signer = signer
        self._issuer = issuer
        self._subject = subject
        self._audience = audience
        self._additional_claims = additional_claims or {}
        self._token_lifetime = token_lifetime

    @classmethod
    def from_service_account_info(cls, info, **kwargs):
        """Creates a Credentials instance from parsed service account info.

        Args:
            info (Mapping): The service account info in Google format.
            kwargs: Additional arguments to pass to the constructor.

        Returns:
            google.auth.jwt.Credentials: The constructed credentials.
        """
        email = info['client_email']
        key_id = info['private_key_id']
        private_key = info['private_key']

        signer = crypt.Signer.from_string(private_key, key_id)

        kwargs.setdefault('subject', email)
        return cls(signer, issuer=email, **kwargs)

    @classmethod
    def from_service_account_file(cls, filename, **kwargs):
        """Creates a Credentials instance from a service account json file.

        Args:
            filename (str): The path to the service account json file.
            kwargs: Additional arguments to pass to the constructor.

        Returns:
            google.auth.jwt.Credentials: The constructed credentials.
        """
        with open(filename, 'r') as json_file:
            info = json.load(json_file)
        return cls.from_service_account_info(info, **kwargs)

    def with_claims(self, issuer=None, subject=None, audience=None,
                    additional_claims=None):
        """Returns a copy of these credentials with modified claims.

        Args:
            issuer (str): The `iss` claim.
            subject (str): The `sub` claim.
            audience (str): the `aud` claim. If not specified, a new
                JWT will be generated for every request and will use
                the request URI as the audience.
            additional_claims (Mapping): Any additional claims for the JWT
                payload.

        Returns:
            google.auth.jwt.Credentials: A new credentials instance.
        """
        return Credentials(
            self._signer,
            issuer=issuer if issuer is not None else self._issuer,
            subject=subject if subject is not None else self._subject,
            audience=audience if audience is not None else self._audience,
            additional_claims=dict(self._additional_claims).update(
                additional_claims or {}))

    def _make_jwt(self, audience=None):
        """Make a signed JWT.

        Args:
            audience (str): Overrides the instance's current audience claim.

        Returns:
            Tuple(bytes, datetime): The encoded JWT and the expiration.
        """
        now = _helpers.now()
        lifetime = datetime.timedelta(seconds=self._token_lifetime)
        expiry = now + lifetime

        payload = {
            'iss': self._issuer,
            'sub': self._subject or self._issuer,
            'iat': _helpers.datetime_to_secs(now),
            'exp': _helpers.datetime_to_secs(expiry),
            'aud': audience or self._audience
        }

        payload.update(self._additional_claims)

        jwt = encode(self._signer, payload)

        return jwt, expiry

    def _make_one_time_jwt(self, uri):
        """Makes a one-off JWT with the URI as the audience.

        Args:
            uri (str): The request URI.

        Returns:
            bytes: The encoded JWT.
        """
        parts = urllib.parse.urlsplit(uri)
        # Strip query string and fragment
        audience = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, None, None))
        token, _ = self._make_jwt(audience=audience)
        return token

    def refresh(self, request):
        """Refreshes the access token.

        Args:
            request (Any): Unused.
        """
        # pylint: disable=unused-argument
        # (pylint doens't correctly recognize overriden methods.)

        self.token, self.expiry = self._make_jwt()

    def sign_bytes(self, message):
        """Signs the given message.

        Args:
            message (bytes): The message to sign.

        Returns:
            bytes: The message signature.
        """
        return self._signer.sign(message)

    def before_request(self, request, method, url, headers):
        """Performs credential-specific before request logic.

        If an audience is specified it will refresh the credentials if
        necessary. If no audience is specified it will generate a one-time
        token for the request URI. In either case, it will set the
        authorization header in headers to the token.

        Args:
            request (Any): Unused.
            method (str): The request's HTTP method.
            url (str): The request's URI.
            headers (Mapping): The request's headers.
        """
        # pylint: disable=unused-argument
        # (pylint doens't correctly recognize overriden methods.)

        # If this set of credentials has a pre-set audience, just ensure that
        # there is a valid token and apply the auth headers.
        if self._audience:
            if not self.valid:
                self.refresh(request)
            self.apply(headers)
        # Otherwise, generate a one-time token using the URL
        # (without the query string and fragement) as the audience.
        else:
            token = self._make_one_time_jwt(url)
            self.apply(headers, token=token)
