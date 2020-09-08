import hashlib
import secrets
import textwrap

from base64 import urlsafe_b64encode
from bottle import HTTPResponse, response, template
from bottle import abort as bottle_abort
from utils.security_headers import SecurityHeadersPlugin

ID_BYTES = 16
HASH_BYTES = 16


# Have no text by default, unlike the default bottle abort function
def abort(code=500, text=None):
    bottle_abort(code=code, text=text)


def generate_id():
    return secrets.token_urlsafe(ID_BYTES)


def hash_urlsafe(value):
    if isinstance(value, str):
        value = value.encode('utf-8')

    hash_bytes = hashlib.blake2b(value, digest_size=HASH_BYTES).digest()
    return urlsafe_b64encode(hash_bytes).decode('utf-8').replace('=', '')


def indent(block, indent=2):
    """Indent a multi-line text block by a number of spaces"""
    return textwrap.indent(block.strip(), ' ' * indent)


def set_headers(r, headers):
    if isinstance(r, HTTPResponse):
        r.headers.update(headers)
    else:
        response.headers.update(headers)


csp_updates = {'img-src': "'self'",
               'script-src': "'self'",
               'style-src': "'self' https://necolas.github.io https://fonts.googleapis.com",
               'font-src': "https://fonts.gstatic.com",
               'manifest-src': "'self'",
               'form-action': "'self'"}
security_headers = SecurityHeadersPlugin(csp_updates=csp_updates)


@security_headers
def html_default_error_hander(res):
    if res.status_code == 404:
        body = template('error_404', error=res)
    else:
        body = template('error', error=res)

    return body
