from jinja2.exceptions import TemplateSyntaxError
from jinja2 import Template
import logging
from nomad.api.exceptions import BadRequestNomadException
import re
import sys

from nomad_backup_operator import config
from nomad_backup_operator import nomad

logger = logging.getLogger(__name__)
# quality of life
# checks job for backup meta options that aren't valid to warn the user
def check_for_incorrect_meta(job_id, meta):
    valid = {
        'backup_cron',
        'backup_forget_keep_hourly',
        'backup_forget_keep_last',
        'backup_forget_keep_daily',
        'backup_forget_keep_weekly',
        'backup_forget_keep_monthly',
        'backup_forget_keep_yearly',
        'backup_hook',
        'backup_must_run',
        'backup_stop_job',
        'backup_upsteam_port',
        'backup_upstream_name',
        'backup_volume',
        'backup_volume_ro',
        }

    for option in meta:
        if re.match('backup_.*', option) and option not in valid:
            logger.warning( f'{job_id}: found invalid configuration key: {option}')

# creates the backup job template
def init():
    success = False
    # all functions need access
    global template
    try:
        with open(config.TEMPLATE,'r') as template_file:
            template = Template(template_file.read())
        success = True
    except PermissionError:
        logger.error('Insufficient permissions to open the template file!')
    except FileNotFoundError:
        logger.error('The template file does not exist!')
    except TemplateSyntaxError as e:
        logger.error(f'Failed to create the template object: {e}')
    
    return success

# Does a dry run of the entire job building process with dummy values. We
# want to be at least somewhat sure that nothing will fail when deploying
# backup jobs for real workloads
def check_job_builder():
    meta = {
            'backup_cron': '2 0 * * *',
            'backup_volume': 'testing-config',
            'backup_hook': 'true',
            'backup_forget_keep_last': '1',
            'backup_must_run': 'true',
            'backup_stop_job': 'true',
            }

    return make_backup_job('testing', meta) is not None

# create the base job that we will work off of
def make_base(job_id, meta):
    backup_job = None

    backup_volume_ro = (meta['backup_volume_ro'] if 'backup_volume_ro' in
                        meta else 'true')

    backup_job_hcl = template.render(
            backup_job_id=job_id+'-backup',
            backup_volume=meta['backup_volume'],
            backup_volume_ro=backup_volume_ro,
            )

    try:
        backup_job = nomad.parse_job(backup_job_hcl)
    except BadRequestNomadException as e:
        logger.warning(f'{job_id}: failed to parse the job: {e}')

    return backup_job

# creates an env dict
def make_env(job_id, meta):
    # every backup job ought to know this
    env = {'JOB': job_id}

    check_for_incorrect_meta(job_id, meta)

    # mapping of forget settings to env var
    forget_keep = {
        'backup_forget_keep_last': 'FORGET_KEEP_LAST',
        'backup_forget_keep_hourly': 'FORGET_KEEP_HOURLY',
        'backup_forget_keep_daily': 'FORGET_KEEP_DAILY',
        'backup_forget_keep_weekly': 'FORGET_KEEP_WEEKLY',
        'backup_forget_keep_monthly': 'FORGET_KEEP_MONTHLY',
        'backup_forget_keep_yearly': 'FORGET_KEEP_YEARLY',
        }

    if 'backup_must_run' in meta:
        env['MUST_RUN'] = meta['backup_must_run']

    if 'backup_stop_job' in meta:
        env['STOP_JOB'] = meta['backup_stop_job']

    # if a script is provided, enable hook
    if 'backup_hook' in meta:
        env['HOOK'] = 'true'

    # if any of the forgetting settings are set, enable forgetting
    if any(forget in meta for forget in forget_keep):
        env['FORGET'] = 'true'
        # meta of: backup_forget_keep_hourly: 1
        # becomes
        # env of: FORGET_KEEP_HOURLY: 1
        for forget in forget_keep:
            if forget in meta:
                env[forget_keep[forget]] = meta[forget]


    return env

# creates a consul connect sidecar dict
def make_connect(meta):
    connect = {
            'SidecarService': {
                'Proxy': {
                    'Upstreams': [
                        {'DestinationName': meta['backup_upstream_name'],
                        'LocalBindPort': int(meta['backup_upsteam_port']),
                         }
                        ]
                    }
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
    backup_job = make_base(job_id, meta)

    if backup_job is None:
        logger.warning(f'{job_id}: failed to create a base template')
        return None

    # add the cron
    backup_job['Periodic'] = {
            'Spec': meta['backup_cron'],
            'SpecType': 'cron',
            }

    env = make_env(job_id, meta)

    # add the env
    for group in backup_job['TaskGroups']:
        for task in group['Tasks']:
            # put the env in
            # merge the dicts if some values are already filled out
            task['Env'] = task['Env']|env if task['Env'] else env

    # add the hook if necessary
    if 'backup_hook' in meta:
        hook = make_hook(meta)
        for group in backup_job['TaskGroups']:
            for task in group['Tasks']:
                # put the hook in
                task['Templates'].append(hook)

    if 'backup_upstream_name' in meta and 'backup_upsteam_port' in meta:
        connect = make_connect(meta)
        for group in backup_job['TaskGroups']:
            # TODO: if a service block isn't defined in the template then
            # we're silently ignoring the consul connect config
            for service in group['Services']:
                service['Connect'] = service['Connect']|connect if service['Connect'] else connect
    elif 'backup_upstream_name' in meta or 'backup_upsteam_port' in meta:
        logger.warn(f'{job_id}: backup_upstream_name XOR backup_upsteam_port declared. Ignoring connect settings.')

    validation = False
    try:
        # currently python-nomad forgets to convert the response to json..
        validation = nomad.validate_job(backup_job).json()

        if validation['Warnings']:
            warning = validation['Warnings'].replace('\n','')
            logger.warn(f'{job_id}: Job validation raised warning: {warning}')

        if not validation['ValidationErrors'] is None:
            # we don't want to deploy an invalid job
            backup_job = None
            for error in validation['ValidationErrors']:
                error = error.replace('\n','')
                logger.warn(f'{job_id}: Job validation raised error: {error}')

    except BadRequestNomadException as e:
        backup_job = None
        logger.warning(f'{job_id}: validation failed: {e}')

    return backup_job
