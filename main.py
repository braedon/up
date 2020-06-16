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
from pymysql import Connection

from utils import log_exceptions, nice_shutdown, graceful_cleanup
from utils.logging import configure_logging, wsgi_log_middleware

from up import construct_app, run_worker, td_format
from up.dao import UpDao, create_db
from up.session import TokenDecoder

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
@click.option('--json', '-j', default=False, is_flag=True,
              help='Log in json.')
@click.option('--verbose', '-v', default=False, is_flag=True,
              help='Log debug messages.')
@log_exceptions(exit_on_exception=True)
@nice_shutdown()
def init(**options):

    configure_logging(json=options['json'], verbose=options['verbose'])

    connection = Connection(host=options['mysql_host'],
                            port=options['mysql_port'],
                            user=options['mysql_user'],
                            password=options['mysql_password'],
                            charset='utf8mb4',
                            cursorclass=pymysql.cursors.DictCursor)

    create_db(connection, options['mysql_database'])

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


@click.command()
@click.option('--tries', default=9,
              help='Number of times to try a URL (default=9).')
@click.option('--initial-delay-minutes', default=15,
              help='How long to wait before the first try of a URL (default=15).')
@click.option('--timeout-seconds', default=10,
              help='Timeout when trying a URL (default=10).')
@click.option('--service-protocol', type=click.Choice(('https', 'http')),
              default='https',
              help='The protocol for the public service. (default=https)')
@click.option('--service-hostname', default='localhost',
              help='The hostname for the public service. (default=localhost)')
@click.option('--service-port', default='',
              help='The port for the public service, if non standard.')
@click.option('--service-path', default='',
              help='The path prefix for the public service, if any.'
                   'Should start with a "/", but not end with one.')
@click.option('--oidc-name', default='Alias',
              help='Name of the OpenID Connect provider to use for login.')
@click.option('--oidc-iss', required=True,
              help='Issuer string of the OpenID Connect provider.')
@click.option('--oidc-about-url', required=True,
              help='URL of an about page for the OpenID Connect provider.')
@click.option('--oidc-auth-endpoint', required=True,
              help='URL of the authenticaiton endpoint of the OpenID Connect provider.')
@click.option('--oidc-token-endpoint', required=True,
              help='URL of the token endpoint of the OpenID Connect provider.')
@click.option('--oidc-public-key-file', default='id_rsa.pub', type=click.File(mode='rb'),
              help='Path to RSA256 public key file for the OpenID Connect provider. '
                   '(default=id_rsa.pub)')
@click.option('--oidc-client-id', required=True,
              help='Client ID issued by the OpenID Connect provider.')
@click.option('--oidc-client-secret', required=True,
              help='Client secret issued by the OpenID Connect provider.')
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
@click.option('--testing-mode', default=False, is_flag=True,
              help='Relax security to simplify testing, e.g. allow http cookies')
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

    with options['oidc_public_key_file'] as file:
        public_key = file.read()
    token_decoder = TokenDecoder(public_key, options['oidc_iss'], options['oidc_client_id'])

    app = construct_app(up_dao, token_decoder, **options)
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
@click.option('--oidc-token-endpoint', required=True,
              help='URL of the token endpoint of the OpenID Connect provider.')
@click.option('--oidc-send-endpoint', required=True,
              help='URL of the send message endpoint of the OpenID Connect provider.')
@click.option('--oidc-client-id', required=True,
              help='Client ID issued by the OpenID Connect provider.')
@click.option('--oidc-client-secret', required=True,
              help='Client secret issued by the OpenID Connect provider.')
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


main.add_command(init)
main.add_command(server)
main.add_command(worker)
main.add_command(show_schedule)


if __name__ == '__main__':
    main(auto_envvar_prefix='UP_OPT')
