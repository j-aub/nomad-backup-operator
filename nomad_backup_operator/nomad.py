import logging
import nomad as n
import queue
import re
import requests_unixsocket
import signal

from nomad_backup_operator import job_builder

logger = logging.getLogger(__name__)
nomad = n.Nomad(session=requests_unixsocket.Session())

# TODO: if the seen set is never cleaned we'll run out of memory!
# we don't want to repeat the same events over and over
seen = set()

def handle_register(job):
    job_id = job['ID']
    # is the backup_cron option is set we assume the job wants a backup job
    # created
    if job['Meta'] is not None and 'backup_cron' in job['Meta']:
        logger.info(f'creating a backup job for job ID {job_id}')
        backup_job = job_builder.make_backup_job(job_id, job['Meta'])

        pass
    else:
        logger.info(f'job ID {job_id} did not want a backup job')

def handle_deregister(job):
    pass

def handle_events(events):
    # that's right there are multiple events in a single event
    for event in events['Events']:
        if event['Index'] not in seen:
            seen.add(event['Index'])
            # we don't need backup jobs for batch jobs
            if event['Payload']['Job']['ParentID'] == '':
                # we most definitely don't need backup jobs for backup jobs
                # getting into an infinite job deploying loop would really suck
                if not re.match('.+-backup', event['Payload']['Job']['ID']):
                    job_id = event['Payload']['Job']['ID']
                    if event['Type'] == 'JobRegistered':
                        logger.info(f'found potential job with ID {job_id}')
                        handle_register(event['Payload']['Job'])
                    elif event['Type'] == 'JobDeregistered':
                        logger.info(f'job ID {job_id} deregistered')
                        handle_deregister(event['Payload']['Job'])

def end_stream(signum, frame):
    signame = signal.Signals(signum).name
    logger.info(f'Received {signame}. Exiting gracefully.')
    stream_exit_event.set()

def event_loop():
    # signal handler needs it
    global stream_exit_event
    # it's not great that the stream needs to keep getting reestablished
    # for graceful exiting to work
    stream, stream_exit_event, events = nomad.event.stream.get_stream(
            topic={'Job'}, timeout=3.0)
    signal.signal(signal.SIGINT, end_stream)
    # docker uses SIGTERM
    signal.signal(signal.SIGTERM, end_stream)

    stream.start()
    while True:
        if not stream.is_alive():
            logger.info('Stream is not alive.')
            break

        try:
            # we can't block infinitely in case the stream dies
            event = events.get(timeout=1.0)
            handle_events(event)
            events.task_done()
        except queue.Empty:
            continue
