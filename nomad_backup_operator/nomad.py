import logging
import nomad
import queue
import re
import requests_unixsocket
import signal

from nomad_backup_operator import job_builder

logger = logging.getLogger(__name__)
n = nomad.Nomad(session=requests_unixsocket.Session())

# TODO: if the seen set is never cleaned we'll run out of memory!
# we don't want to repeat the same events over and over
seen = set()

# creates job dict from hcl
# raises BadRequestNomadException
def parse_job(job_hcl):
    return n.jobs.parse(job_hcl, canonicalize=True)

# validates job dict
def validate_job(job):
    return n.validate.validate_job({'Job': job})

def stop_job(job_id):
    n.job.deregister_job(job_id)

def handle_register(job_id):
    job = n.job[job_id]

    # job has to be running
    # not be an instance of a batch job
    # and not be a backup job
    if (job['Status'] == 'running' and
        job['ParentID'] == '' and
        not re.match('.+-backup', job_id)):

        logger.info(f'found potential job with ID {job_id}')
        # is the backup_cron and backup_volume options are set we assume
        # the job wants a backup job created
        if (job['Meta'] is not None and 
            'backup_cron' in job['Meta'] and 
            'backup_volume' in job['Meta']):

            logger.info(f'{job_id}: backup job desired')

            backup_job = job_builder.make_backup_job(job_id, job['Meta'])

            if backup_job is None:
                logger.warning(f'{job_id}: could not create backup job!')
            else:
                n.job.register_job(backup_job['ID'], {'Job': backup_job})
                logger.info(f'{job_id}: deployed backup job')
        else:
            logger.info(f'{job_id}: backup job not wanted')

def handle_deregister(job_id):
    job = n.job[job_id]

    # job has to be dead
    # not be an instance of a batch job
    # and not be a backup job
    if (job['Status'] == 'dead' and
        job['ParentID'] == '' and
        not re.match('.+-backup', job_id)):

        logger.info(f'stopping backup job of job ID {job_id} if any')
        stop_job(job_id+'-backup')

# create/remove backup jobs for all the currently deployed jobs
# TODO: we will end up with stale jobs if a job is deregistered while the
# operator isn't running. Best to clean up stale jobs on boot
def create_existing():
    for job in n.jobs:
        job_status = job['Status']
        job_id = job['ID']


        if job_status == 'running':
            handle_register(job_id)
        elif job_status == 'dead':
            handle_deregister(job_id)

def handle_events(events):
    # that's right there are multiple events in a single event
    for event in events['Events']:
        if event['Index'] not in seen:
            seen.add(event['Index'])
            job_id = event['Payload']['Job']['ID']
            if event['Type'] == 'JobRegistered':
                handle_register(job_id)
            elif event['Type'] == 'JobDeregistered':
                handle_deregister(job_id)

def end_stream(signum, frame):
    signame = signal.Signals(signum).name
    logger.info(f'Received {signame}. Exiting gracefully.')
    stream_exit_event.set()

def event_loop():
    # signal handler needs it
    global stream_exit_event
    # it's not great that the stream needs to keep getting reestablished
    # for graceful exiting to work
    stream, stream_exit_event, events = n.event.stream.get_stream(
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
