import re
import sys
import logging
from jinja2 import Template
from jinja2.exceptions import TemplateSyntaxError

from nomad_backup_operator import config

logger = logging.getLogger(__name__)
# quality of life
# checks job for backup meta options that aren't valid to warn the user
def check_for_incorrect_meta(job_id, meta):
    valid = {
        'backup_cron',
        'backup_forget_keep_hourly',
        'backup_forget_keep_last',
        'backup_forget_keep_weekly',
        'backup_forget_keep_yearly',
        'backup_hook',
        'backup_must_run',
        'backup_stop_job',
        'backup_upsteam_port',
        'backup_upstream_name',
        'backup_volume',
        }

    for option in meta:
        if re.match('backup_.+', option) and option not in valid:
            logger.warning( f'{job_id}: found invalid configuration key {option}!')

# creates the backup job template
def init():
    # all functions need access
    global template
    try:
        with open(config.TEMPLATE,'r') as template_file:
            template = Template(template_file.read())
    except PermissionError:
        logger.error('Insufficient permissions to open the template file')
        sys.exit(1)
    except FileNotFoundError:
        logger.error('The template file does not exist')
        sys.exit(1)
    except TemplateSyntaxError as e:
        logger.error(f'Failed to create the template object: {e}')
        sys.exit(1)


# validates some basic assumptions about the base template
# if they don't hold we shouldn't bother starting the event monitoring
def check_base():
    # we will template the template with some dummy values to see if
    # anything breaks
    backup_job_hcl = template.render(
            backup_job_id='testing-backup',
            backup_volume='testing-config',
            )

    backup_job = nomad.parse_job(backup_job_hcl)

    return nomad.validate_job(backup_job)

# create the base job that we will work off of
def make_base(job_id, meta):
    pass

# creates an env dict
def make_env(job_id, meta):
    # every backup job ought to know this
    env = {'JOB': job_id}

    check_for_incorrect_meta(meta)

    # mapping of forget settings to env var
    forget_keep = {
        'backup_forget_keep_last': 'FORGET_KEEP_LAST',
        'backup_forget_keep_hourly': 'FORGET_KEEP_HOURLY',
        'backup_forget_keep_weekly': 'FORGET_KEEP_WEEKLY',
        'backup_forget_keep_yearly': 'FORGET_KEEP_YEARLY',
        }

    if 'backup_must_run' in job['Meta']:
        env['MUST_RUN'] = meta['backup_must_run']

    if 'backup_stop_job' in job['Meta']:
        env['STOP_JOB'] = meta['backup_stop_job']

    # if a script is provided, enable hook
    if 'backup_hook' in meta:
        env['HOOK'] = 'true'

    # if any of the forgetting settings are set, enable forgetting
    if any(forget in meta for forget in forget_keep):
        env['FORGET'] = 'true'

    return env

# creates a consul connect sidecar dict
def make_connect(meta):
    connect = {
            'SidecarService': {
                'Upstreams': [
                    {'DestinationName': meta['backup_upstream_name'],
                    'LocalBindPort': meta['backup_upsteam_port'],
                     }
                    ]
                }
            }
    return connect

# creates a hook file template
def make_hook(meta):
    hook = {
            'DestPath': 'local/hook',
            'EmbeddedTmpl': meta['backup_hook'],
            # must be executable
            'Perms': '755',
            }
    return hook

# creates a backup job dict for the input job
def make_backup_job(job_id, meta):
    return None
    backup_job = make_base()

    # add the cron
    job['Periodic'] = {
            'Spec': meta['backup_cron'],
            'SpecType': 'cron',
            }

    env = make_env(job_id, meta)

    # add the env
    for group in backup_job['TaskGroups']:
        for task in group['Tasks']:
            # put the env in
            # marge the dicts if some values are already filled out
            task['Env'] = task['Env']|env if task['Env'] else env

    # add the hook if necessary
    if 'backup_hook' in job['Meta']:
        hook = make_hook(meta)
        for group in backup_job['TaskGroups']:
            for task in group['Tasks']:
                # put the hook in
                task['Templates'].append(hook)

    if 'backup_upstream_name' in job['Meta'] and 'backup_upsteam_port' in job['Meta']:
        connect = make_connect(meta)
        for group in backup_job['TaskGroups']:
            # TODO: if a service block isn't defined in the template then
            # we're silently ignore the consul connect config
            for service in group['Services']:
                service['Connect'] = service['Connect']|connect if service['Connect'] else connect

    return backup_job
