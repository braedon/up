import re
import rfc3339
from bottle import HTTPError


class ParamParseError(HTTPError):
    pass


class InvalidParamError(ParamParseError):
    default_status = 400

    def __init__(self, param, value, message=None, **options):
        self.param = param
        self.value = value
        body = 'Invalid {}'.format(param.replace('_', ' '))
        if message:
            body += ': {}'.format(message)
        if body[-1] != '.':
            body += '.'
        super(InvalidParamError, self).__init__(body=body, **options)


class RequiredParamError(ParamParseError):
    default_status = 400

    def __init__(self, param, message=None, **options):
        self.param = param
        body = 'Missing {}'.format(param.replace('_', ' '))
        if message:
            body += ': {}'.format(message)
        if body[-1] != '.':
            body += '.'
        super(RequiredParamError, self).__init__(body=body, **options)


class UnsetType(object):
    __instance = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
        return cls.__instance


Unset = UnsetType()


def param_parser(key, *other_keys,
                 default=Unset, empty=Unset, required=False, strip=False, multi=False):
    """
    Decorator that coverts a parsing function into a full param parser.

    The parsing functions take two strings - the param key and value - and return the parsed
    (and validated, if applicable) value. InvalidParamError should be raised if parsing(/validation)
    fails.

    The returned param parser function takes a dict of params, and attempts to find and parse a
    value for one of the keys listed. Each key is tried in turn, with the first key present in the
    params dict used (regardless of its value).

    If a key is found but the value is empty, `empty` is used. `empty` is `Unset` by default.

    If none of the keys are found or the value is found to be `Unset`, `default` is used.
    `default` is `Unset` by default.

    If the value is still found to be `Unset` and the param is `required`, RequiredParamError is
    raised. If none of the keys were found, the first key is used as the required param.

    If `strip` is set, whitespace is stripped from the start and end of values before parsing.

    If `multi` is set, an array of sub values is parsed. If `multi` is a string, the value is split
    by that string, e.g. ','. If it is any other truthy value, `.getall()` is used to get the value
    of all instances of the key in the params. Empty string sub values are removed, as are sub
    values that parse to `Unset`. `strip` applies to sub values. `default` and `empty` apply to the
    param as a whole, so should be arrays. `required` also applies to the param as a whole.
    """

    def decorator(parse_func):

        def parse_key(params, k):
            v = params[k]

            if multi:
                if isinstance(multi, str):
                    v = params[k].split(multi)
                else:
                    v = params.getall(k)

                if strip:
                    v = [sv.strip() for sv in v]

                v = [sv for sv in v if sv != '']

                v = [parse_func(k, sv) for sv in v]
                v = [sv for sv in v if sv is not Unset]

                if not v:
                    return empty

                return v

            else:
                v = params[k]

                if strip:
                    v = v.strip()

                if v == '':
                    return empty

                return parse_func(k, v)

        def parse_keys(params, keys):
            for k in keys:
                if k in params:
                    v = parse_key(params, k)

                    if v is Unset:
                        v = default

                    if required and v is Unset:
                        raise RequiredParamError(k)

                    return v

            return default

        def wrapper(params):
            v = parse_keys(params, [key, *other_keys])

            if required and v is Unset:
                raise RequiredParamError(key)

            return v

        return wrapper

    return decorator


def string_param(*keys, default=Unset, empty=Unset, required=False, strip=False, multi=False,
                 enum=None, min_length=None, max_length=None):

    @param_parser(*keys, default=default, empty=empty, required=required, strip=strip, multi=multi)
    def parse(k, v):
        if enum is not None and v not in enum:
            raise InvalidParamError(k, v, 'Must be a value from {}'.format(','.join(enum)))
        if min_length is not None and len(v) < min_length:
            raise InvalidParamError(k, v, 'Must be at least {} characters'.format(min_length))
        if max_length is not None and len(v) > max_length:
            raise InvalidParamError(k, v, 'Must be no more than {} characters'.format(max_length))

        return v

    return parse


def boolean_param(*keys, default=Unset, empty=Unset, required=False, strip=True, multi=False,
                  enum=None):

    @param_parser(*keys, default=default, empty=empty, required=required, strip=strip, multi=multi)
    def parse(k, v):
        if v.lower() in ('true', 't', 'yes', 'y'):
            return True

        if v.lower() in ('false', 'f', 'no', 'n'):
            return False

        # Allows "boolean" params to also have extra options beyond True and False.
        if enum is not None:
            if v.lower() not in enum:
                raise InvalidParamError(k, v, 'Must be true, false, or a value from {}'.format(','.join(enum)))

            return v

        raise InvalidParamError(k, v, 'Must be "true" or "false"')

    return parse


def integer_param(*keys, default=Unset, empty=Unset, required=False, strip=True, multi=False,
                  positive=False, enum=None):

    @param_parser(*keys, default=default, empty=empty, required=required, strip=strip, multi=multi)
    def parse(k, v):
        if not v.isdecimal():
            raise InvalidParamError(k, v, 'Must be an integer')
        v = int(v)
        if positive and v < 0:
            raise InvalidParamError(k, v, 'Must be positive')
        if enum is not None and v not in enum:
            raise InvalidParamError(k, v, 'Must be a value from {}'.format(','.join(enum)))

        return v

    return parse


def float_param(*keys, default=Unset, empty=Unset, required=False, strip=True, multi=False,
                positive=False, enum=None):

    @param_parser(*keys, default=default, empty=empty, required=required, strip=strip, multi=multi)
    def parse(k, v):
        def is_float(val):
            return re.match(r'^\d+(\.\d+)?$', val) is not None

        if not is_float(v):
            raise InvalidParamError(k, v, 'Must be a decimal')
        v = float(v)
        if positive and v < 0:
            raise InvalidParamError(k, v, 'Must be positive')
        if enum is not None and v not in enum:
            raise InvalidParamError(k, v, 'Must be a value from {}'.format(','.join(enum)))

        return v

    return parse


def datetime_param(*keys, default=Unset, empty=Unset, required=False, strip=True, multi=False,
                   range_end=False):

    @param_parser(*keys, default=default, empty=empty, required=required, strip=strip, multi=multi)
    def parse(k, v):
        try:
            # If value string is a date, attempt to convert to datetime
            rfc3339.parse_date(v)
            if range_end:
                v = v + 'T23:59:59Z'
            else:
                v = v + 'T00:00:00Z'
        except ValueError:
            pass

        try:
            dt = rfc3339.parse_datetime(v)
            return dt
        except ValueError:
            raise InvalidParamError(k, v, 'Must be a valid datetime')

    return parse


def parse_params(params, **parsers):
    """
    Parse a number of params out of a params dict, returning the parsed params as dict.

    The `params` string -> string dict usually holds HTTP query params, or form params.

    Each of the `parsers` keyword parameters maps a key in the returned dict to a param parser
    function. Each parser is run on the `params` in turn, and the produced value (if not `Unset`)
    added to the returned dict under the parser's keyword. Note that the parser keywords may be
    unrelated to the param keys their parser targets.
    """
    parsed_params = {}

    for out_key, parser in parsers.items():
        v = parser(params)
        if v is not Unset:
            parsed_params[out_key] = v

    return parsed_params


def parse_param(params, parser):
    """
    Parse a single param out of a params dict.

    The `params` string -> string dictionary usually holds HTTP query params, or form params.

    The `parser` is a param parser function that is run on the `params`, and the produced value
    returned (or `None` if `Unset` is produced).
    """
    v = parser(params)
    if v is not Unset:
        return v
    else:
        return None
