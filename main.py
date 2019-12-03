#!/usr/bin/python3
from gevent import monkey; monkey.patch_all()

import bottle
import click
import logging
import pymysql
import time

from datetime import timedelta
from DBUtils.PooledDB import PooledDB
from gevent.pool import Pool

from up import construct_app, run_worker, td_format
from up.dao import UpDao

from logging_utils import configure_logging, wsgi_log_middleware
from utils import log_exceptions, nice_shutdown, graceful_cleanup

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help']
}

log = logging.getLogger(__name__)

# Use an unbounded pool to track gevent greenlets so we can
# wait for them to finish on shutdown.
gevent_pool = Pool()


@click.group(context_settings=CONTEXT_SETTINGS)
def main():
    pass


@click.command()
@click.option('--tries', default=9,
              help='Number of times to try a URL (default=9).')
@click.option('--initial-delay-minutes', default=15,
              help='How long to wait before the first try of a URL (default=15).')
@click.option('--timeout-seconds', default=10,
              help='Timeout when trying a URL (default=10).')
@click.option('--mysql-host', default='localhost',
              help='MySQL server host (default=localhost).')
@click.option('--mysql-port', default=3306,
              help='MySQL server port (default=3306).')
@click.option('--mysql-user', default='up',
              help='MySQL server user (default=up).')
@click.option('--mysql-password', default='',
              help='MySQL server password (default=None).')
@click.option('--mysql-database', default='up',
              help='MySQL server database (default=up).')
@click.option('--port', '-p', default=8080,
              help='Port to serve on (default=8080).')
@click.option('--json', '-j', default=False, is_flag=True,
              help='Log in json.')
@click.option('--verbose', '-v', default=False, is_flag=True,
              help='Log debug messages.')
@log_exceptions(exit_on_exception=True)
@nice_shutdown()
def server(**options):

    def graceful_shutdown():
        log.info('Starting graceful shutdown.')
        # Sleep for a few seconds to allow for race conditions between sending
        # the SIGTERM and load balancers stopping sending traffic here and
        time.sleep(5)
        # Allow any running requests to complete before exiting.
        # Socket is still open, so assumes no new traffic is reaching us.
        gevent_pool.join()

    configure_logging(json=options['json'], verbose=options['verbose'])

    connection_pool = PooledDB(creator=pymysql,
                               mincached=1,
                               maxcached=10,
                               # max connections currently in use - doesn't
                               # include cached connections
                               maxconnections=50,
                               blocking=True,
                               host=options['mysql_host'],
                               port=options['mysql_port'],
                               user=options['mysql_user'],
                               password=options['mysql_password'],
                               database=options['mysql_database'],
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
    up_dao = UpDao(connection_pool)
    up_dao.create_job_table()

    app = construct_app(up_dao, **options)
    app = wsgi_log_middleware(app)

    with graceful_cleanup(graceful_shutdown):
        bottle.run(app,
                   host='0.0.0.0', port=options['port'],
                   server='gevent', spawn=gevent_pool,
                   # Disable default request logging - we're using middleware
                   quiet=True, error_log=None)


@click.command()
@click.option('--delay-multiplier', default=2,
              help='Multiplier to apply to the delay after each try of a URL (default=2).')
@click.option('--timeout-seconds', default=10,
              help='Timeout when trying a URL (default=10).')
@click.option('--mysql-host', default='localhost',
              help='MySQL server host (default=localhost).')
@click.option('--mysql-port', default=3306,
              help='MySQL server port (default=3306).')
@click.option('--mysql-user', default='up',
              help='MySQL server user (default=up).')
@click.option('--mysql-password', default='',
              help='MySQL server password (default=None).')
@click.option('--mysql-database', default='up',
              help='MySQL server database (default=up).')
@click.option('--smtp-host', default='localhost',
              help='SMTP server host (default=localhost).')
@click.option('--smtp-port', default=25,
              help='SMTP server port (default=25).')
@click.option('--json', '-j', default=False, is_flag=True,
              help='Log in json.')
@click.option('--verbose', '-v', default=False, is_flag=True,
              help='Log debug messages.')
@log_exceptions(exit_on_exception=True)
@nice_shutdown()
def worker(**options):

    configure_logging(json=options['json'], verbose=options['verbose'])

    connection_pool = PooledDB(creator=pymysql,
                               mincached=1,
                               maxcached=1,
                               # max connections currently in use - doesn't
                               # include cached connections
                               maxconnections=1,
                               blocking=True,
                               host=options['mysql_host'],
                               port=options['mysql_port'],
                               user=options['mysql_user'],
                               password=options['mysql_password'],
                               database=options['mysql_database'],
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
    up_dao = UpDao(connection_pool)
    up_dao.create_job_table()

    run_worker(up_dao, **options)


@click.command()
@click.option('--tries', default=9,
              help='Number of times to try a URL (default=9).')
@click.option('--initial-delay-minutes', default=15,
              help='How long to wait before the first try of a URL (default=15).')
@click.option('--delay-multiplier', default=2,
              help='Multiplier to apply to the delay after each try of a URL (default=2).')
def show_schedule(tries, initial_delay_minutes, delay_multiplier):

    delay = timedelta(minutes=initial_delay_minutes)
    total_delay = delay
    for t in range(1, tries + 1):
        print(f'{t:5}: {td_format(delay)}')
        delay = delay * delay_multiplier
        total_delay += delay

    print(f"Total: {td_format(delay)}")


main.add_command(server)
main.add_command(worker)
main.add_command(show_schedule)


if __name__ == '__main__':
    main(auto_envvar_prefix='UP_OPT')
