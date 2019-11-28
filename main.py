#!/usr/bin/python3
import bottle
import click
import logging
import time

from up import construct_app
from up.timeQueue import TimeQueue
from up.workQueue import WorkQueue

from logging_utils import configure_logging, wsgi_log_middleware
from utils import log_exceptions, nice_shutdown, graceful_cleanup


log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help']
}


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
