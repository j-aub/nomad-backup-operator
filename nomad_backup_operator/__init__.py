import sys
import logging
import urllib3
import os

from nomad_backup_operator import nomad
from nomad_backup_operator import job_builder

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

def main():
    # supress python-nomad warning about untrusted ca python-nomad has no
    # way to add a cacert when using mtls so there's no way to get rid of
    # the error properly
    urllib3.disable_warnings()

    configure_logging()
    job_builder.init()

    if not job_builder.check_base():
        loggererror('the job template is invalid')
        sys.exit(1)

    nomad.event_loop()
