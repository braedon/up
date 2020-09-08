import functools
import logging
import re

from bottle import HTTPResponse, response


PP_ALLOWLIST_REGEX = re.compile(r'^\((.*)\)$')
PP_ORIGIN_REGEX = re.compile(r'^"(.*)"$')

log = logging.getLogger(__name__)


def ensure_headers(r, headers):
    """Set headers on a response if not already set"""
    r = r if isinstance(r, HTTPResponse) else response

    for k, v in headers.items():
        if k not in r.headers:
            r.set_header(k, v)


def pp_origin_to_fp(origin):
    if origin == '*':
        return '*'

    if origin == 'self':
        return "'self'"

    match = PP_ORIGIN_REGEX.match(origin)
    if match is None:
        return None

    return match.group(1)


def pp_allowlist_to_fp(allowlist):
    if allowlist == '*':
        return '*'

    if allowlist == 'self':
        return "'self'"

    match = PP_ALLOWLIST_REGEX.match(allowlist)
    if match is None:
        return None

    allowlist = match.group(1).split()

    if len(allowlist) == 0:
        return "'none'"

    allowlist = [pp_origin_to_fp(origin) for origin in allowlist]

    if any(origin is None for origin in allowlist):
        return None

    return ' '.join(allowlist)


class SecurityHeadersPlugin(object):
    name = 'security_headers'
    api = 2
    sh_defaults = {
        'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
        'Expect-CT': 'max-age=86400, enforce',
        'Referrer-Policy': 'no-referrer, strict-origin-when-cross-origin',
        'Cross-Origin-Opener-Policy': 'same-origin',
        'Cross-Origin-Embedder-Policy': 'require-corp',
        'Cross-Origin-Resource-Policy': 'same-origin',
        'X-XSS-Protection': '1; mode=block',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
    }
    csp_defaults = {
        # Fetch directives
        'default-src': "'none'",
        # Document directives
        'base-uri': "'none'",
        # Navigation directives
        'form-action': "'none'",
        'frame-ancestors': "'none'",
        # Other directives
        'block-all-mixed-content': True,
    }
    pp_defaults = {
        'accelerometer': '()',
        'ambient-light-sensor': '()',
        'autoplay': '()',
        'battery': '()',
        'camera': '()',
        'display-capture': '()',
        'document-domain': '()',
        'encrypted-media': '()',
        'execution-while-not-rendered': '()',
        'execution-while-out-of-viewport': '()',
        'fullscreen': '()',
        'geolocation': '()',
        'gyroscope': '()',
        'layout-animations': '()',
        'legacy-image-formats': '()',
        'magnetometer': '()',
        'microphone': '()',
        'midi': '()',
        'navigation-override': '()',
        'oversized-images': '()',
        'payment': '()',
        'picture-in-picture': '()',
        'publickey-credentials-get': '()',
        'screen-wake-lock': '()',
        'sync-xhr': '()',
        'usb': '()',
        'wake-lock': '()',
        'web-share': '()',
        'xr-spatial-tracking': '()',
    }

    def __init__(self, sh_updates=None, csp_updates=None, pp_updates=None):
        if sh_updates:
            self.sh_defaults = {**self.sh_defaults,
                                **sh_updates}
        if csp_updates:
            self.csp_defaults = {**self.csp_defaults,
                                 **csp_updates}
        if pp_updates:
            self.pp_defaults = {**self.pp_defaults,
                                **pp_updates}

    def get_sh(self, sh_updates=None):
        sh_dict = self.sh_defaults
        if sh_updates:
            sh_dict = {**sh_dict, **sh_updates}

        return {k: v for k, v in sh_dict.items() if v is not False}

    def get_csp(self, csp_updates=None):
        csp_dict = self.csp_defaults
        if csp_updates:
            csp_dict = {**csp_dict, **csp_updates}

        csp_entries = []
        for k, v in csp_dict.items():
            if isinstance(v, bool):
                if v:
                    csp_entries.append(k)
            else:
                csp_entries.append(f'{k} {v}')

        return '; '.join(csp_entries)

    def get_pp(self, pp_updates=None):
        pp_dict = self.pp_defaults
        if pp_updates:
            pp_dict = {**pp_dict, **pp_updates}

        pp_entries = []
        for k, v in pp_dict.items():
            if v is not False:
                pp_entries.append(f'{k}={v}')

        return ', '.join(pp_entries)

    def get_fp(self, pp_updates=None):
        pp_dict = self.pp_defaults
        if pp_updates:
            pp_dict = {**pp_dict, **pp_updates}

        fp_entries = []
        for k, v in pp_dict.items():
            if v is not False:
                v = pp_allowlist_to_fp(v)
                if v is None:
                    log.warning('Permissions-Policy directive %(directive)s allowlist is invalid. '
                                'Can\'t convert directive to Feature-Policy header.',
                                {'directive': k})
                else:
                    fp_entries.append(f'{k} {v}')

        return '; '.join(fp_entries)

    def apply(self, callback, route=None):
        sh_updates = route.config.get('sh_updates') if route else None
        csp_updates = route.config.get('sh_csp_updates') if route else None
        pp_updates = route.config.get('sh_pp_updates') if route else None
        # Bottle flattens dictionaries passed into route config for some reason,
        # so need to un-flatten the dicts.
        if route:
            if not sh_updates:
                prefix = 'sh_updates.'
                prefix_len = len(prefix)
                sh_updates = {k[prefix_len:]: v for k, v in route.config.items()
                              if k[:prefix_len] == prefix}
            if not csp_updates:
                prefix = 'sh_csp_updates.'
                prefix_len = len(prefix)
                csp_updates = {k[prefix_len:]: v for k, v in route.config.items()
                               if k[:prefix_len] == prefix}
            if not pp_updates:
                prefix = 'sh_pp_updates.'
                prefix_len = len(prefix)
                pp_updates = {k[prefix_len:]: v for k, v in route.config.items()
                              if k[:prefix_len] == prefix}

        headers = {**self.get_sh(sh_updates=sh_updates),
                   'Content-Security-Policy': self.get_csp(csp_updates=csp_updates),
                   'Permissions-Policy': self.get_pp(pp_updates=pp_updates),
                   'Feature-Policy': self.get_fp(pp_updates=pp_updates)}

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            r = callback(*args, **kwargs)
            ensure_headers(r, headers)
            return r

        return wrapper

    def __call__(self, callback):
        return self.apply(callback)
