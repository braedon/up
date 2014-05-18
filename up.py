#!/usr/bin/python3
from bottle import get, post, run, request, static_file
import requests
import time
import logging
import smtplib
from email.message import EmailMessage
from email.headerregistry import Address

from workQueue import WorkQueue
from timeQueue import TimeQueue

timeout = 5
tries = 5
delay = 10

delay_str = time.strftime('%H:%M:%S', time.gmtime(delay))

workQueue = WorkQueue()
queue = TimeQueue(workQueue)
queue.daemon = True
queue.setName('queue')

f = logging.Formatter(
    '[%(asctime)s]%(name)s.%(levelname)s %(threadName)s %(message)s')
logger = logging.getLogger('')
logger.setLevel(10)
fh = logging.FileHandler('all.log')
fh.setFormatter(f)
logger.addHandler(fh)


def send_email(email, subject, message):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = 'up@resisty.com'
    msg['To'] = email
    msg.set_content(message)

    with smtplib.SMTP('localhost') as s:
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

@post('/')
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

@get('/')
def get():
    return static_file('up.html', root='')

if __name__ == "__main__":
    queue.start()
    run(host='localhost', port='8080', debug=True)
