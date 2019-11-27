#!/usr/bin/python3
import bottle
import click
import json
import logging
import requests
import time
import smtplib

from bottle import Bottle, request, response, static_file, abort
from datetime import timedelta
from email.message import EmailMessage

from timeQueue import TimeQueue
from workQueue import WorkQueue

from logging_utils import configure_logging, wsgi_log_middleware
from utils import log_exceptions, nice_shutdown, graceful_cleanup


log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help']
}

TD_PERIODS = [
    ('year', 60 * 60 * 24 * 365),
    ('month', 60 * 60 * 24 * 30),
    ('day', 60 * 60 * 24),
    ('hour', 60 * 60),
    ('minute', 60),
    ('second', 1)
]


def json_default_error_handler(http_error):
    response.content_type = 'application/json'
    return json.dumps({'error': http_error.body}, separators=(',', ':'))


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


def construct_app(queue,
                  tries, delay_minutes, timeout_seconds,
                  smtp_host, smtp_port,
                  **kwargs):
    app = Bottle()
    app.default_error_handler = json_default_error_handler

    delay = timedelta(minutes=delay_minutes)

    def send_email(email, subject, message):
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = 'up@resisty.com'
        msg['To'] = email
        msg.set_content(message)

        with smtplib.SMTP(host=smtp_host, port=smtp_port) as s:
            s.send_message(msg)

    def queue_url(email, url, tries):

        def try_url(email, url, tries):
            try:
                r = requests.get(url, timeout=timeout_seconds)
                s = r.status_code
                if s >= 500 and s < 600:
                    queue_url(email, url, tries)
                elif s >= 400 and s < 500:
                    subject = f'Up Service: URL {url} responding with a client error'
                    message = f'URL {url} is responding with the status {s} which indicates a client error. ' + \
                              'No futher attempts to reach this URL will be made.'
                    send_email(email, subject, message)
                elif s >= 200 and s < 300:
                    subject = f'Up Service: URL {url} responding successfully!'
                    message = f'URL {url} is responding with the status {s} which indicates success! ' + \
                              'Try it again yourself now.'
                    send_email(email, subject, message)
                else:
                    log.error('Unexpected status [%(status)s] received for url [%(url)s]',
                              {'status': s, 'url': url})
                    subject = f'Up Service: URL {url} responding unexpectedly'
                    message = f'URL {url} is responding in an unexpected way. ' + \
                              'No futher attempts to reach this URL will be made.'
                    send_email(email, subject, message)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                queue_url(email, url, tries)

        if tries > 0:
            queue.addAction(time.time() + delay.total_seconds(), try_url, email, url, tries - 1)
        else:
            subject = f'Up Service: URL {url} still down'
            message = f'URL {url} still appears to be be down and all tries have been exhausted. ' + \
                      'No futher attempts to reach this URL will be made.'
            send_email(email, subject, message)

    @app.get('/status')
    def status():
        return 'OK'

    @app.post('/')
    def post():
        url = request.forms.url
        email = request.forms.email
        if url and email:
            queue_url(email, url, tries)
            return {
                'url': url,
                'email': email,
                'tries': tries,
                'delay_seconds': delay.total_seconds(),
                'message': f'Trying url "{url}" {tries} times, with a delay of {td_format(delay)} between tries.',
            }
        else:
            abort(400, 'Please specify both a url and an email address.')

    @app.get('/')
    def get():
        return static_file('index.html', root='')

    return app


@log_exceptions(exit_on_exception=True)
@nice_shutdown()
@click.command(context_settings=CONTEXT_SETTINGS)
@click.option('--tries', default=10,
              help='Number of times to try a URL (default=10).')
@click.option('--delay-minutes', default=30,
              help='How long to wait between tries of a URL (default=30).')
@click.option('--timeout-seconds', default=10,
              help='Timeout when trying a URL (default=10).')
@click.option('--smtp-host', default='localhost',
              help='SMTP server host (default=localhost).')
@click.option('--smtp-port', default=25,
              help='SMTP server port (default=25).')
@click.option('--port', '-p', default=8080,
              help='Port to serve on (default=8080).')
@click.option('--json', '-j', default=False, is_flag=True,
              help='Log in json.')
@click.option('--verbose', '-v', default=False, is_flag=True,
              help='Log debug messages.')
def main(**options):

    def graceful_shutdown():
        log.info('Starting graceful shutdown.')
        # Sleep for a few seconds to allow for race conditions between sending
        # the SIGTERM and load balancers stopping sending traffic here and
        time.sleep(5)

    configure_logging(json=options['json'], verbose=options['verbose'])

    workQueue = WorkQueue()
    queue = TimeQueue(workQueue)
    queue.daemon = True
    queue.setName('queue')

    app = construct_app(queue, **options)
    app = wsgi_log_middleware(app)

    queue.start()

    with graceful_cleanup(graceful_shutdown):
        bottle.run(app,
                   host='0.0.0.0', port=options['port'],
                   # Disable default request logging - we're using middleware
                   quiet=True, error_log=None)


if __name__ == '__main__':
    main(auto_envvar_prefix='UP_OPT')
