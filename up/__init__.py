import logging
import requests
import rfc3339
import time

from bottle import Bottle, request, response, static_file, template, redirect
from datetime import timedelta
from jwt.exceptions import InvalidTokenError
from urllib.parse import urlparse, urljoin, urlencode

from utils.param_parse import parse_params, boolean_param, string_param

from .dao import Job
from .misc import abort, html_default_error_hander, generate_id, hash_urlsafe, security_headers
from .session import SessionHandler


log = logging.getLogger(__name__)


DEFAULT_CONTINUE_URL = '/'

TD_PERIODS = [
    ('year', 60 * 60 * 24 * 365),
    ('month', 60 * 60 * 24 * 30),
    ('day', 60 * 60 * 24),
    ('hour', 60 * 60),
    ('minute', 60),
    ('second', 1)
]

NOTIFICATION_CHANNEL = 'link_notifications'

SERVER_READY = True


def td_format(td_object):
    remaining_secs = int(td_object.total_seconds())

    strings = []
    for period_name, period_seconds in TD_PERIODS:
        if remaining_secs > period_seconds:
            period_value, remaining_secs = divmod(remaining_secs, period_seconds)
            maybe_and = 'and ' if not remaining_secs and strings else ''
            maybe_s = 's' if period_value > 1 else ''
            strings.append(f"{maybe_and}{period_value} {period_name}{maybe_s}")

    if len(strings) == 2:
        return ' '.join(strings)
    else:
        return ', '.join(strings)


def construct_app(dao, token_decoder,
                  tries, initial_delay_minutes, timeout_seconds,
                  service_protocol, service_hostname,
                  service_port, service_path,
                  oidc_name, oidc_iss, oidc_about_url,
                  oidc_auth_endpoint, oidc_token_endpoint,
                  oidc_client_id, oidc_client_secret,
                  testing_mode,
                  **kwargs):

    session_handler = SessionHandler(token_decoder, testing_mode=testing_mode)

    app = Bottle()
    app.default_error_handler = html_default_error_hander

    app.install(security_headers)

    # Construct more permissive Content Security Policies for use in certain endpoints.
    # Need to allow submitting forms to the OIDC provider, as some browsers consider redirects after
    # form submissions to be targets. We redirect to the OIDC provider when submitting the
    # "notify me" form to request/ensure contact permissions are set.
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/form-action
    csp_form_action = f"'self' {oidc_iss}"
    if testing_mode:
        csp_form_action += ' http://localhost:*'

    initial_delay = timedelta(minutes=initial_delay_minutes)

    service_address = f'{service_protocol}://{service_hostname}'
    if service_port:
        service_address += f':{service_port}'
    if service_path:
        service_address += service_path

    oidc_redirect_uri = urljoin(service_address, '/oidc/callback')

    def check_continue_url(continue_url):
        try:
            parsed_continue_url = urlparse(continue_url)
        except ValueError:
            log.warning('Received invalid continue url: %(continue_url)s',
                        {'continue_url': continue_url})
            abort(400)

        if parsed_continue_url.scheme or parsed_continue_url.netloc:
            # Absolute url - check it's for this service
            if not continue_url.startswith(service_address):
                log.warning('Received continue url for another service: %(continue_url)s',
                            {'continue_url': continue_url})
                abort(400)

    def construct_oidc_request(*scopes, channels=None):
        state = generate_id()
        nonce = generate_id()

        qs_dict = {
            'response_type': 'code',
            'client_id': oidc_client_id,
            'redirect_uri': oidc_redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            # Keep the original nonce a secret, to avoid auth code replay attacks.
            # If an attacker manages to steal an auth code for a user from the callback URL, they
            # may be able to construct a fake OIDC data cookie and call the callback URL themselves
            # (before the user does, consuming the auth code). This would log them in as the user.
            # However, if they only have the hash of the nonce from the OIDC request url, not the
            # original nonce value, they can't construct a correct OIDC data cookie and their
            # request will be rejected.
            'nonce': hash_urlsafe(nonce),
        }
        if channels:
            qs_dict['channels'] = ' '.join(channels)
        qs = urlencode(qs_dict)
        url = f'{oidc_auth_endpoint}?{qs}'

        return state, nonce, url

    @app.get('/-/live')
    def live():
        return 'Live'

    @app.get('/-/ready')
    def ready():
        if SERVER_READY:
            return 'Ready'
        else:
            response.status = 503
            return 'Unavailable'

    @app.get('/')
    @session_handler.maybe_session()
    def index():
        if request.session:
            user_id = request.session['user_id']
        else:
            user_id = None

        return template('index',
                        user_id=user_id,
                        oidc_name=oidc_name,
                        oidc_about_url=oidc_about_url)

    @app.get('/main.css')
    def css():
        return static_file('main.css', root='static')

    @app.get('/robots.txt')
    def robots():
        return static_file('robots.txt', root='static')

    # Favicon stuff generated at:
    # https://favicon.io/favicon-generator/?t=u%3F&ff=Roboto+Slab&fs=100&fc=%23444&b=rounded&bc=%23F9F9F9
    @app.get('/favicon.ico')
    def icon():
        return static_file('favicon.ico', root='static')

    @app.get('/site.webmanifest')
    def manifest():
        return static_file('site.webmanifest', root='static')

    @app.get('/<filename>.png')
    def root_pngs(filename):
        return static_file(f'{filename}.png', root='static')

    @app.get('/<filename>.js')
    def scripts(filename):
        return static_file(f'{filename}.js', root='static')

    @app.get('/login')
    def get_login():
        params = parse_params(request.query.decode(),
                              auto_redirect=boolean_param('auto', default=False, empty=True),
                              continue_url=string_param('continue', strip=True, max_length=2000))
        auto_redirect = params['auto_redirect']
        continue_url = params.get('continue_url')
        if continue_url:
            check_continue_url(continue_url)

        state, nonce, oidc_login_uri = construct_oidc_request('openid')

        # NOTE: The state field works as Login CSRF protection.
        session_handler.set_oidc_data(state, nonce,
                                      action='login',
                                      continue_url=continue_url or DEFAULT_CONTINUE_URL)

        if auto_redirect:
            redirect(oidc_login_uri)

        else:
            return template('login',
                            oidc_name=oidc_name,
                            oidc_about_url=oidc_about_url,
                            oidc_login_uri=oidc_login_uri)

    @app.get('/oidc/callback')
    def get_oidc_callback():

        # NOTE: Generally raise 500 for unexpected issues with the oidc flow, caused either by our
        #       oidc state management or the oidc provider response. All traffic to this endpoint
        #       should be via the oidc flow, and the provider should be working to spec. If not,
        #       something is likely wrong with the flow implementation, so 500 is appropriate.

        # Check state and error before anything else, to make sure nothing's fishy
        params = parse_params(request.query.decode(),
                              state=string_param('state', strip=True),
                              error=string_param('error', strip=True),
                              error_description=string_param('error_description', strip=True))

        # Use 500 rather than "nicer" error if state is missing.
        state = params.get('state')
        if not state:
            log.warning('Received OIDC callback with no state.')
            abort(500)

        oidc_data = session_handler.get_oidc_data(state)
        if not oidc_data:
            log.warning('Received OIDC callback with no OIDC data cookie.')
            abort(500)

        # Only part of the state is used when fetching the OIDC data, so still need to check it.
        if state != oidc_data['state']:
            log.warning('Received OIDC callback with mismatching state.')
            abort(500)

        # State seems to be OK, so this is a valid response for this request. Drop the OIDC data
        # so this state can't be used again.
        # NOTE: This won't take effect if a later error occurs.
        session_handler.clear_oidc_data(state)

        action = oidc_data['action']

        error = params.get('error')
        if error:
            if error == 'access_denied':
                # User rejected the OIDC request - where should we send them?
                if action == 'login':
                    # Login OIDC request, send them back home.
                    redirect('/')

                elif action == 'notify':
                    # Link notify OIDC request, send them back to the link check page.
                    qs_dict = {'url': oidc_data['url']}
                    qs = urlencode(qs_dict)
                    redirect(f'/link?{qs}')

                else:
                    raise NotImplementedError(f'Unsupported OIDC action {action}.')

            # Any other error...
            else:
                error_description = params.get('error_description')
                log_msg = 'Received OIDC callback with error %(error)s'
                log_params = {'error': error}
                if error_description:
                    log_msg += ': %(error_description)s'
                    log_params['error_description'] = error_description
                log.warning(log_msg, log_params)
                abort(500)

        # If there wasn't an error, there should be a code
        params = parse_params(request.query.decode(),
                              code=string_param('code', strip=True))
        code = params.get('code')
        # Once again, use 500 rather than a "nicer" error if code is missing
        if not code:
            log.warning('Received OIDC callback with no code.')
            abort(500)

        r = requests.post(oidc_token_endpoint, timeout=10,
                          auth=(oidc_client_id, oidc_client_secret),
                          data={'grant_type': 'authorization_code',
                                'client_id': oidc_client_id,
                                'redirect_uri': oidc_redirect_uri,
                                'code': code})

        # Only supported response status code.
        if r.status_code == 200:
            pass
        else:
            log.warning('OIDC token endpoint returned unexpected status code %(status_code)s.',
                        {'status_code': r.status_code})
            r.raise_for_status()
            raise NotImplementedError(f'Unsupported status code {r.status_code}.')

        try:
            r_json = r.json()
            id_token = r_json['id_token']
            id_token_jwt = token_decoder.decode_id_token(id_token)
        except (ValueError, KeyError, InvalidTokenError) as e:
            log.warning('OIDC token endpoint returned invalid response: %(error)s', {'error': e})
            abort(500)

        if 'nonce' not in id_token_jwt:
            log.warning('OIDC token endpoint didn\'t return nonce in token.')
            abort(500)

        if id_token_jwt['nonce'] != hash_urlsafe(oidc_data['nonce']):
            log.warning('OIDC token endpoint returned incorrect nonce in token.')
            abort(500)

        if action == 'login':
            # Check continue_url is valid, since the oidc cookie data isn't signed.
            continue_url = oidc_data['continue_url']
            check_continue_url(continue_url)

            session_handler.set_session(id_token)
            redirect(continue_url)

        elif action == 'notify':
            url = oidc_data['url']

            approved_scopes = r_json['scope'].split()
            if not ('offline_access' in approved_scopes and 'contact' in approved_scopes):
                qs_dict = {'url': url, 'alert': 'insufficient-scope'}
                qs = urlencode(qs_dict)
                redirect(f'/link?{qs}')

            approved_channels = r_json['channels'].split()
            if NOTIFICATION_CHANNEL not in approved_channels:
                qs_dict = {'url': url, 'alert': 'insufficient-channels'}
                qs = urlencode(qs_dict)
                redirect(f'/link?{qs}')

            now_dt = rfc3339.now()
            job = Job(job_id=generate_id(),
                      user_id=id_token_jwt['sub'],
                      status='pending',
                      run_dt=now_dt + initial_delay,
                      url=url,
                      tries=tries,
                      delay_s=initial_delay.total_seconds())
            dao.insert_job(job)
            return template('notify_result',
                            oidc_name=oidc_name,
                            url=url)

        else:
            raise NotImplementedError(f'Unsupported OIDC action {action}.')

    # NOTE: The logout endpoint doesn't require CSRF protection, as the session isn't used to
    #       authenticate the user - the session, if it exists, is cleared instead.
    # TODO: Make POST
    @app.get('/logout')
    @session_handler.maybe_session(check_csrf=False)
    def logout():
        params = parse_params(request.query.decode(),
                              continue_url=string_param('continue', strip=True, max_length=2000))
        continue_url = params.get('continue_url')
        if continue_url:
            check_continue_url(continue_url)

        if request.session is not None:
            session_handler.clear_session()

        redirect(continue_url or DEFAULT_CONTINUE_URL)

    @app.get('/link', sh_csp_updates={'form-action': csp_form_action})
    @session_handler.require_session()
    def check():
        csrf = request.session['csrf']

        # NOTE: Alerts are currently only supported for `check_down` template, as that's the only
        #       template that includes a form to submit that may have an error.
        alert = request.query.alert

        url = request.query.url
        if not url:
            abort(400, 'Please specify a url.')

        try:
            r = requests.get(url, timeout=timeout_seconds)
            s = r.status_code

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return template('check_down', alert=alert, oidc_name=oidc_name, url=url, csrf=csrf)

        if s >= 500 and s < 600:
            return template('check_down', alert=alert, oidc_name=oidc_name, url=url, csrf=csrf)

        if s >= 400 and s < 500:
            return template('check_client_error', url=url)
        elif s >= 200 and s < 300:
            return template('check_up', url=url)
        else:
            log.error('[Check] Unexpected status %(status)s received for url %(url)s.',
                      {'status': s, 'url': url})
            abort(500)

    @app.post('/link')
    @session_handler.require_session()
    def notify():
        url = request.query.url
        if not url:
            abort(400, 'Please specify a url.')

        state, nonce, oidc_login_uri = construct_oidc_request('openid', 'offline_access', 'contact',
                                                              channels=['link_notifications'])

        session_handler.set_oidc_data(state, nonce,
                                      action='notify',
                                      url=url)

        redirect(oidc_login_uri)

    return app


token_data = None


def run_worker(dao, delay_multiplier, timeout_seconds,
               oidc_token_endpoint, oidc_send_endpoint,
               oidc_client_id, oidc_client_secret,
               **kwargs):

    def get_access_token():
        global token_data

        request_dt = rfc3339.now()
        if token_data and request_dt < token_data['expire_dt']:
            return token_data['access_token']

        # Get a client credentials access token.
        r = requests.post(oidc_token_endpoint, timeout=10,
                          auth=(oidc_client_id, oidc_client_secret),
                          data={'grant_type': 'client_credentials',
                                'scope': 'client:send'})

        if r.status_code != 200:
            log.warning('OIDC token endpoint returned unexpected status code %(status_code)s.',
                        {'status_code': r.status_code})
            r.raise_for_status()
            raise NotImplementedError(f'Unsupported status code {r.status_code}.')

        r_json = r.json()

        access_token = r_json['access_token']
        expire_dt = request_dt + timedelta(seconds=r_json['expires_in'])
        token_data = {'access_token': access_token, 'expire_dt': expire_dt}

        return access_token

    def send_message(job_id, user_id, url, subject, message):

        access_token = get_access_token()

        r = requests.post(oidc_send_endpoint, timeout=10,
                          headers={'Authorization': f'Bearer {access_token}'},
                          json={'version': 'v0',
                                # Set the outbound message ID to the job ID to avoid resending a
                                # message if the job fails and is retried after a message was sent.
                                'outbound_message_id': job_id,
                                'channel': 'link_notifications',
                                'to': user_id,
                                'title': subject,
                                'body': message,
                                'link': {'uri': url, 'text': 'Try Link'}})

        if r.status_code == 202:
            return  # Success

        elif r.status_code == 400:
            try:
                r_json = r.json()
            except ValueError:
                r_json = None

            if r_json and r_json.get('code') == 'outbound-message-id-exists':
                log.warning('[%(job_id)s] Message already sent.',
                            {'job_id': job_id})
                return

            log.warning('[%(job_id)s] Message send endpoint returned unexpected 400 Bad Request.',
                        {'job_id': job_id, 'response_json': r_json})
            r.raise_for_status()
            raise Exception('Unexpected 400 Bad Request')

        elif r.status_code == 403:
            try:
                r_json = r.json()
            except ValueError:
                r_json = None

            if r_json and r_json.get('code') in ('contact-forbidden', 'contact-channel-forbidden'):
                log.warning('[%(job_id)s] Message send forbidden: %(code)s',
                            {'job_id': job_id, 'code': r_json['code']})
                return  # Nothing more we can do.

            log.warning('[%(job_id)s] Message send endpoint returned unexpected 403 Forbidden.',
                        {'job_id': job_id, 'response_json': r_json})
            r.raise_for_status()
            raise Exception('Unexpected 403 Forbidden')

        else:
            log.warning('[%(job_id)s] Message send endpoint returned unexpected status code %(status_code)s.',
                        {'job_id': job_id, 'status_code': r.status_code})
            r.raise_for_status()
            raise NotImplementedError(f'Unsupported status code {r.status_code}.')

    def maybe_requeue(job):
        if job.tries > 1:
            delay = timedelta(seconds=job.delay_s) * delay_multiplier
            new_job = Job(job_id=generate_id(),
                          user_id=job.user_id,
                          status='pending',
                          run_dt=job.run_dt + delay,
                          url=job.url,
                          tries=job.tries - 1,
                          delay_s=delay.total_seconds())
            log.info('[%(job_id)s] Couldn\'t load url %(url)s. Retrying. New job: %(new_job_id)s',
                     {'job_id': job.job_id, 'url': job.url, 'new_job_id': new_job.job_id})
            dao.finish_job(job.job_id, new_job=new_job)

        else:
            log.info('[%(job_id)s] Couldn\'t load url %(url)s and out of tries. Notifying user.',
                     {'job_id': job.job_id, 'url': job.url})
            subject = f'Link still down'
            message = f'Link {job.url} still appears to be be down and all tries have been exhausted. ' + \
                      'No futher attempts to load this link will be made.'
            send_message(job.job_id, job.user_id, job.url, subject, message)
            dao.finish_job(job.job_id)

    def try_url(job):
        log.info('[%(job_id)s] Trying url %(url)s.',
                 {'job_id': job.job_id, 'url': job.url})

        try:
            r = requests.get(job.url, timeout=timeout_seconds)
            s = r.status_code

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            maybe_requeue(job)
            return

        if 500 <= s < 600:
            maybe_requeue(job)
            return

        if 400 <= s < 500:
            log.info('[%(job_id)s] Client error %(status)s received for url %(url)s. Notifying user.',
                     {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Link responding with a client error'
            message = f'Link {job.url} is responding with status {s} which indicates a client error. ' + \
                      'No futher attempts to load this link will be made.'
        elif 200 <= s < 300:
            log.info('[%(job_id)s] Successful status %(status)s received for url %(url)s. Notifying user.',
                     {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Link responding successfully!'
            message = f'Link {job.url} is responding with status {s} which indicates success! ' + \
                      'Try it again yourself now.'
        else:
            log.error('[%(job_id)s] Unexpected status %(status)s received for url %(url)s. Notifying user.',
                      {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Link responding unexpectedly'
            message = f'Link {job.url} is responding in an unexpected way. ' + \
                      'No futher attempts to load this link will be made.'

        send_message(job.job_id, job.user_id, job.url, subject, message)
        dao.finish_job(job.job_id)

    while True:
        next_job = dao.find_next_job()

        if next_job:
            wait_s = (next_job.run_dt - rfc3339.now()).total_seconds()

            if wait_s > 0:
                time.sleep(min(wait_s, 30))
            else:
                try_url(next_job)

        else:
            time.sleep(10)
