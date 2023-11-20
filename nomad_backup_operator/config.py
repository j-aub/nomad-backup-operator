import os

TEMPLATE: str = os.getenv('TEMPLATE')
if not TEMPLATE:
    if os.getenv('NOMAD_SECRETS_DIR'):
        TEMPLATE = os.getenv('NOMAD_SECRETS_DIR') + '/template'
    else:
        raise ValueError('A job template must be set.')
