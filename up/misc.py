import functools
import secrets
import textwrap

from bottle import HTTPResponse, response, template
from bottle import abort as bottle_abort

ID_BYTES = 16


# Have no text by default, unlike the default bottle abort function
def abort(code=500, text=None):
    bottle_abort(code=code, text=text)


# TODO: Should we generate a GUID v4 (fully random) instead?
def generate_id():
    return secrets.token_urlsafe(ID_BYTES)


def indent(block, indent=2):
    """Indent a multi-line text block by a number of spaces"""
    return textwrap.indent(block.strip(), ' ' * indent)


def set_headers(r, headers):
    if isinstance(r, HTTPResponse):
        r.headers.update(headers)
    else:
        response.headers.update(headers)


class SecurityHeadersPlugin(object):
    name = 'security_headers'
    api = 2

    def __init__(self):
        self.headers = {
            'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
            'Expect-CT': 'max-age=86400, enforce',
            'Content-Security-Policy': '; '.join([
                # Fetch directives
                "default-src 'none'",
                "img-src 'self'",
                "script-src 'self'",
                "style-src 'self' https://necolas.github.io https://fonts.googleapis.com",
                "font-src https://fonts.gstatic.com",
                "manifest-src 'self'",
                # Document directives
                "base-uri 'self'",
                # Navigation directives
                "form-action 'self'",
                "frame-ancestors 'none'",
                # Other directives
                "block-all-mixed-content",
            ]),
            'Feature-Policy': '; '.join([
                "accelerometer 'none'",
                "ambient-light-sensor 'none'",
                "autoplay 'none'",
                "battery 'none'",
                "camera 'none'",
                "display-capture 'none'",
                "document-domain 'none'",
                "encrypted-media 'none'",
                "execution-while-not-rendered 'none'",
                "execution-while-out-of-viewport 'none'",
                "fullscreen 'none'",
                "geolocation 'none'",
                "gyroscope 'none'",
                "layout-animations 'none'",
                "legacy-image-formats 'none'",
                "magnetometer 'none'",
                "microphone 'none'",
                "midi 'none'",
                "navigation-override 'none'",
                "oversized-images 'none'",
                "payment 'none'",
                "picture-in-picture 'none'",
                "publickey-credentials 'none'",
                "sync-xhr 'none'",
                "usb 'none'",
                "wake-lock 'none'",
                "xr-spatial-tracking 'none'",
            ]),
            'Referrer-Policy': 'no-referrer, strict-origin-when-cross-origin',
            'X-Frame-Options': 'deny',
            'X-XSS-Protection': '1; mode=block',
            'X-Content-Type-Options': 'nosniff',
        }

    def apply(self, callback, route=None):

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            r = callback(*args, **kwargs)
            set_headers(r, self.headers)
            return r

        return wrapper

    def __call__(self, callback):
        return self.apply(callback)


security_headers = SecurityHeadersPlugin()


@security_headers
def html_default_error_hander(res):
    if res.status_code == 404:
        body = template('error_404', error=res)
    else:
        body = template('error', error=res)

    return body
