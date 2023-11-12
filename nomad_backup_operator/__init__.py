import sys
import logging
import subprocess
import urllib3
import os
import signal
import nomad
import queue
import re

logger = logging.getLogger(__name__)

def configure_logging():
    # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings
    # properly log the python-nomad ssl error
    logging.captureWarnings(True)
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s %(name)-15s %(levelname)-4s: %(message)s',
        '%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

def end_stream(signum, frame):
    signame = signal.Signals(signum).name
    logger.info(f'Received {signame}. Exiting gracefully.')
    stream_exit_event.set()

def handle_events(events):
    # that's right there are multiple events in a single event
    for event in events['Events']:
        # we don't need backup jobs for a batch job
        print(event)
        if event['Payload']['Job']['ParentID'] == '':
            logger.info('job does not have a ParentID')
            # avoid backup jobs like the plague
            # getting into an infinite job deploying loop would really suck
            if not re.match('.+-backup', event['Payload']['Job']['ID']):
                logger.info('the job is not a backup job')
                if event['Type'] == 'JobRegistered':
                        logger.info('a job registered.')
                elif event['Type'] == 'JobDeregistered':
                        logger.info('a job deregistered.')

def main():
    # supress python-nomad warning about untrusted ca
    # python-nomad has no way to add a cacert so there's no way to get rid
    # of the error properly
    urllib3.disable_warnings()

    configure_logging()

    n = nomad.Nomad()

    # signal handler needs it
    global stream_exit_event
    # it's not great that the stream needs to keep getting reestablished
    # for graceful exiting to work
    stream, stream_exit_event, events = n.event.stream.get_stream(
            topic={'Job'}, timeout=5.0)
    signal.signal(signal.SIGINT, end_stream)
    # docker uses SIGTERM
    signal.signal(signal.SIGTERM, end_stream)

    stream.start()
    while True:
        if not stream.is_alive():
            logger.info('Stream is not alive.')
            break

        try:
            # we can't block here infinitely in case the stream dies
            event = events.get(timeout=1.0)

            handle_events(event)

            events.task_done()
        except queue.Empty:
            continue
