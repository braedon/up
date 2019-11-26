#!/usr/bin/python3
import bottle
import click
import json
import logging
import requests
import time
import smtplib

from bottle import Bottle, request, response, static_file
from email.message import EmailMessage

from timeQueue import TimeQueue
from workQueue import WorkQueue

from logging_utils import configure_logging, wsgi_log_middleware
from utils import log_exceptions, nice_shutdown, graceful_cleanup


log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help']
}


def json_default_error_handler(http_error):
    response.content_type = 'application/json'
    return json.dumps({'error': http_error.body}, separators=(',', ':'))


def construct_app(queue, smtp_host, smtp_port, **kwargs):
    app = Bottle()
    app.default_error_handler = json_default_error_handler

    timeout = 5
    tries = 5
    delay = 10

    delay_str = time.strftime('%H:%M:%S', time.gmtime(delay))

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
                r = requests.get(url, timeout=timeout)
                s = r.status_code
                if s >= 500 and s < 600:
                    queue_url(email, url, tries)
                elif s >= 400 and s < 500:
                    subject = 'Up Service: URL {} responding with a client error'.format(
                        url)
                    message = 'URL {} is responding with the status {} which indicates a client error. No futher attempts to reach this URL will be made.'.format(
                        url,
                        s)
                    send_email(email, subject, message)
                elif s >= 200 and s < 300:
                    subject = 'Up Service: URL {} responding successfully!'.format(
                        url)
                    message = 'URL {} is responding with the status {} which indicates success! Try it again yourself now.'.format(
                        url,
                        s)
                    send_email(email, subject, message)
                else:
                    log.error(
                        'unexpected status [{}] received for url [{}]'.format(
                            s,
                            url))
                    subject = 'Up Service: URL {} responding unexpectedly'.format(
                        url)
                    message = 'URL {} is responding in an unexpected way. No futher attempts to reach this URL will be made.'.format(
                        url)
                    send_email(email, subject, message)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                queue_url(email, url, tries)

        if tries > 0:
            queue.addAction(time.time() + delay, try_url, email, url, tries - 1)
        else:
            subject = 'Up Service: URL {} still down'.format(url)
            message = 'URL {} still appears to be be down and all tries have been exhausted. No futher attempts to reach this URL will be made.'.format(
                url)
            send_email(email, subject, message)

    @app.post('/')
    def post():
        url = request.query.url
        email = request.query.email
        if url and email:
            queue_url(email, url, tries)
            return 'Trying url {} {} times with delay of {} between tries. Will notify {}.'.format(
                url,
                tries,
                delay_str,
                email)
        else:
            return 'Please specify both a url and an email address.'

    @app.get('/')
    def get():
        return static_file('up.html', root='')

    return app


@log_exceptions(exit_on_exception=True)
@nice_shutdown()
@click.command(context_settings=CONTEXT_SETTINGS)
@click.option('--port', '-p', default=8080,
              help='Port to serve on (default=8080)')
@click.option('--smtp-host', default='localhost',
              help='SMTP server host (default=localhost)')
@click.option('--smtp-port', default=25,
              help='SMTP server port (default=25)')
@click.option('--json', '-j', default=False, is_flag=True,
              help='Log in json')
@click.option('--verbose', '-v', default=False, is_flag=True,
              help='Log debug messages')
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
