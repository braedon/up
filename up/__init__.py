import logging
import requests
import rfc3339
import smtplib
import time

from bottle import Bottle, request, static_file, template
from datetime import timedelta
from email.message import EmailMessage

from .dao import Job
from .misc import abort, html_default_error_hander, generate_id, security_headers


log = logging.getLogger(__name__)

TD_PERIODS = [
    ('year', 60 * 60 * 24 * 365),
    ('month', 60 * 60 * 24 * 30),
    ('day', 60 * 60 * 24),
    ('hour', 60 * 60),
    ('minute', 60),
    ('second', 1)
]


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


def construct_app(dao, tries, initial_delay_minutes, timeout_seconds, **kwargs):
    app = Bottle()
    app.default_error_handler = html_default_error_hander
    app.install(security_headers)

    initial_delay = timedelta(minutes=initial_delay_minutes)

    @app.get('/status')
    def status():
        return 'OK'

    @app.get('/')
    def index():
        return template('index')

    @app.get('/main.css')
    def css():
        return static_file('main.css', root='static')

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

    @app.get('/check')
    def check():
        url = request.query.url
        if not url:
            abort(400, 'Please specify a url.')

        try:
            r = requests.get(url, timeout=timeout_seconds)
            s = r.status_code

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return template('check_down', url=url)

        if s >= 500 and s < 600:
            return template('check_down', url=url)

        if s >= 400 and s < 500:
            return template('check_client_error', url=url)
        elif s >= 200 and s < 300:
            return template('check_up', url=url)
        else:
            log.error('[Check] Unexpected status %(status)s received for url %(url)s.',
                      {'status': s, 'url': url})
            abort(500)

    @app.post('/submit')
    def submit():
        url = request.forms.url
        email = request.forms.email
        if not (url and email):
            abort(400, 'Please specify both a url and an email address.')

        now_dt = rfc3339.now()
        job = Job(job_id=generate_id(),
                  status='pending',
                  run_dt=now_dt + initial_delay,
                  email=email,
                  url=url,
                  tries=tries,
                  delay_s=initial_delay.total_seconds())
        dao.insert_job(job)
        return template('submit_result', url=url, email=email)

    return app


def run_worker(dao, from_address, delay_multiplier, timeout_seconds,
               smtp_host, smtp_port, **kwargs):

    def send_email(email, subject, message):
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_address
        msg['To'] = email
        msg.set_content(message)

        with smtplib.SMTP(host=smtp_host, port=smtp_port) as s:
            s.send_message(msg)

    def maybe_requeue(job):
        if job.tries > 1:
            delay = timedelta(seconds=job.delay_s) * delay_multiplier
            new_job = Job(job_id=generate_id(),
                          status='pending',
                          run_dt=job.run_dt + delay,
                          email=job.email,
                          url=job.url,
                          tries=job.tries - 1,
                          delay_s=delay.total_seconds())
            log.info('[%(job_id)s] Couldn\'t load url %(url)s. Retrying. New job: %(new_job_id)s',
                     {'job_id': job.job_id, 'url': job.url,
                      'new_job_id': new_job.job_id})
            dao.finish_job(job.job_id, new_job=new_job)

        else:
            log.info('[%(job_id)s] Couldn\'t load url %(url)s and out of tries. Notifying user.',
                     {'job_id': job.job_id, 'url': job.url})
            subject = f'Up Service: URL {job.url} still down'
            message = f'URL {job.url} still appears to be be down and all tries have been exhausted. ' + \
                      'No futher attempts to reach this URL will be made.'
            send_email(job.email, subject, message)
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

        if s >= 500 and s < 600:
            maybe_requeue(job)
            return

        if s >= 400 and s < 500:
            log.info('[%(job_id)s] Client error %(status)s received for url %(url)s. Notifying user.',
                     {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Up Service: URL {job.url} responding with a client error'
            message = f'URL {job.url} is responding with the status {s} which indicates a client error. ' + \
                      'No futher attempts to reach this URL will be made.'
        elif s >= 200 and s < 300:
            log.info('[%(job_id)s] Successful status %(status)s received for url %(url)s. Notifying user.',
                     {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Up Service: URL {job.url} responding successfully!'
            message = f'URL {job.url} is responding with the status {s} which indicates success! ' + \
                      'Try it again yourself now.'
        else:
            log.error('[%(job_id)s] Unexpected status %(status)s received for url %(url)s. Notifying user.',
                      {'job_id': job.job_id, 'status': s, 'url': job.url})
            subject = f'Up Service: URL {job.url} responding unexpectedly'
            message = f'URL {job.url} is responding in an unexpected way. ' + \
                      'No futher attempts to reach this URL will be made.'

        send_email(job.email, subject, message)
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
