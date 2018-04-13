import pip
import os
import json
import logging
import time

LOG_PATH='/var/log'
LOG_FILE='rancher_init.log'
LOG_LEVEL=logging.DEBUG

RANCHER_ENDPOINT = os.environ.get('RANCHER_ENDPOINT')
RANCHER_ADMIN_NAME = os.environ.get('RANCHER_ADMIN_NAME')
RANCHER_ADMIN_USERNAME = os.environ.get('RANCHER_ADMIN_USERNAME')
RANCHER_ADMIN_PASSWORD = os.environ.get('RANCHER_ADMIN_PASSWORD')

RANCHER_STASK_DIR_USER = '/opt/rancher/stacks/user'
RANCHER_CERT_DIR = '/opt/rancher/cert'
RANCHER_NFS_ENDPOINT = os.environ.get('RANCHER_NFS_ENDPOINT')
RANCHER_NFS_ON_REMOVE = os.environ.get('RANCHER_NFS_ON_REMOVE')

RANCHER_SUPPORTED_DOCKER_VERSIONS = "~v1.12.3 || ~v1.13.0 || ~v17.03.0 || ~v17.06.0 || ~v17.09.0"

KV_CONSUL = 'consul'
KV_ETCD = 'etcd'
KV_DB = KV_CONSUL


def install(package):
    pip.main(['install', package])


try:
    import requests
except ImportError:
    install('requests')
    import requests

if KV_CONSUL == KV_ETCD:
    try:
        import etcd
    except ImportError:
        install('python-etcd')
        import etcd
elif KV_CONSUL == KV_CONSUL:
    try:
        import consul
    except ImportError:
        install('python-consul')
        import consul


def wait_for_rancher(rancher_url):
    url = os.path.join(rancher_url, 'v2-beta/localauthconfig')
    headers = {'Accept': 'application/json'}
    resp = None
    while not resp:
        try:
            r = requests.get(url, headers=headers)
            if r.status_code < 500:
                _ = r.json()
                resp = r.status_code
            else:
                logging.info("Staus: %s" % r.status_code)
                time.sleep(1)
        except requests.exceptions.ConnectionError:
            time.sleep(10)
            logging.info("Waiting for Rancher")
        except ValueError as e:
            time.sleep(1)
            logging.info("%s" % e)
    return resp


def rancher_get_pid(rancher_url):
    url = os.path.join(rancher_url, 'v1/projects')
    headers = {'Accept': 'application/json'}
    code=None
    while code != 200:
        try:
            response = requests.get(url, headers=headers)
            logging.debug('Status code: %s' % response.status_code)
            _ = response.json()
            code = response.status_code
        except ValueError as e:
            time.sleep(1)
            logging.info("%s" % e)
    return response.json()['data'][0]['id']


def rancher_get_tid(rancher_url, pid):
    url = os.path.join(rancher_url, 'v1/projects/%s/registrationTokens' % pid)
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers)
    return response.json()['id']


def rancher_get_registration_url(rancher_url, pid, tid):
    url = os.path.join(rancher_url, 'v1/projects/%s/registrationToken/%s' % (pid,tid))
    headers = {
        'Accept': 'application/json',
    }
    key_active = False
    res = None
    while not key_active:
        response = requests.get(url, headers=headers)
        if response.json()['state'] == 'active':
            key_active = True
            res = response.json()['registrationUrl']
        else:
            time.sleep(0.1)
    return res


def rancher_create_access_key(rancher_url):
    url = os.path.join(rancher_url, 'v1/apikey')
    payload = {
        'description': 'Rancher init script',
        "name": "srv_init",
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    key_id = response.json()['id']
    res = (response.json()['publicValue'], response.json()['secretValue'])
    key_active = False
    while not key_active:
        response = requests.get("%s/%s" % (url, key_id), headers=headers)
        if response.json()['state'] == 'active':
            key_active = True
        else:
            time.sleep(0.1)
    return res


def rancher_add_certificate(rancher_url, pid, name, cert, key):
    url = os.path.join(rancher_url, 'v2-beta/projects/%s/certificates' % pid)
    payload = {
        "cert": cert,
        "key": key,
        "name": name
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.json()


def rancher_settings_update(rancher_url, key, vaule):
    url = os.path.join(rancher_url, 'v2-beta/settings/%s' % key)
    payload = {
        "value": "%s" % vaule,
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    return response.json()


def rancher_settings_get(rancher_url, key):
    url = os.path.join(rancher_url, 'v2-beta/settings/%s' % key)
    headers = {
        'Accept': 'application/json',
    }
    key_active = False
    res = None
    while not key_active:
        response = requests.get(url, headers=headers)
        if response.json()['type'] == "activeSetting":
            key_active = True
            res = response.json()['value']
        else:
            time.sleep(0.1)
    return res


def rancher_add_catalog(rancher_url, catalog_name, catalog_url, catalog_branch='master'):
    cur_catalog = json.loads(rancher_settings_get(rancher_url, 'catalog.url'))
    item = {
        catalog_name: {
            'url': catalog_url,
            'branch': catalog_branch,
        }
    }
    cur_catalog['catalogs'].update(item)
    rancher_settings_update(rancher_url, 'catalog.url', json.dumps(cur_catalog))


def rancher_set_local_auth_config(rancher_url, admin_name, admin_username, admin_password):
    url = os.path.join(rancher_url, 'v2-beta/localauthconfig')
    print(url)
    payload = {
        'type': 'localAuthConfig',
        'baseType': 'localAuthConfig',
        'accessMode': 'unrestricted',
        'enabled': True,
        'name': admin_name,
        'password': admin_password,
        'username': admin_username,
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print(response.text)
    return response.json()


def fs_list_stacks(dir):
    if os.path.isdir(dir):
        return [o for o in os.listdir(dir)
                if os.path.isdir(os.path.join(dir,o))
                if os.path.isfile(os.path.join(dir, o, 'docker-compose.yml'))
                if os.path.isfile(os.path.join(dir, o, 'rancher-compose.yml'))]
    else:
        return []


def fs_list_certificates(dir):
    if os.path.isdir(dir):
        res = {}
        files = os.listdir(dir)
        keys = set(os.path.splitext(o)[0] for o in files)
        return [(key, '%s.crt' % key, '%s.key' % key) for key in keys if '%s.key' % key in files and '%s.crt' % key in files]
    else:
        return []


def rancher_create_nfs_stack(rancher_url, access_key, access_key_secret, pid, start=False):
    SERVICE_TAG = 'v0.8.5'
    url = os.path.join(rancher_url, 'v2-beta/projects/%s/stacks' % pid)
    payload = {
        "system": True,
        "type": "stack",
        "name": "nfs",
        "startOnCreate": start,
        "environment": {
            "NFS_SERVER": "%s" % RANCHER_NFS_ENDPOINT,
            "ON_REMOVE": "%s" % RANCHER_NFS_ON_REMOVE,
            "MOUNT_DIR": "/nfs",
            "MOUNT_OPTS": "",
            "NFS_VERS": "nfsvers=4",
            "RANCHER_DEBUG": "false"
        },
        "dockerCompose": "version: '2'\nservices:\n  nfs-driver:\n    privileged: true\n    image: rancher/storage-nfs:%s\n    pid: host\n    labels:\n      io.rancher.scheduler.global: 'true'\n      io.rancher.container.create_agent: 'true'\n      io.rancher.container.dns: 'true'\n      io.rancher.container.agent.role: environment\n    environment:\n      NFS_SERVER: '${NFS_SERVER}'\n      MOUNT_DIR: '${MOUNT_DIR}'\n      ON_REMOVE: '${ON_REMOVE}'\n      MOUNT_OPTS: '${MOUNT_OPTS},${NFS_VERS}'\n    volumes:\n    - /run:/run\n    - /var/run:/var/run\n    - /dev:/host/dev\n    - /var/lib/rancher/volumes:/var/lib/rancher/volumes:shared\n    logging:\n      driver: json-file\n      options:\n        max-size: 25m\n        max-file: '2'\n" % SERVICE_TAG,
        "rancherCompose": ".catalog:\n  name: \"Rancher NFS\"\n  version: 0.4.0\n  description: |\n    Docker volume plugin for NFS\n  minimum_rancher_version: v1.6.6-rc1\n  questions:\n  - variable: \"NFS_SERVER\"\n    description: \"IP or hostname of the default NFS Server\"\n    label: \"NFS Server\"\n    required: true\n    type: \"string\"\n  - variable: \"MOUNT_DIR\"\n    label: \"Export Base Directory\"\n    description: \"The default exported base directory\"\n    type: \"string\"\n    required: true\n  - variable: \"MOUNT_OPTS\"\n    label: \"Mount Options\"\n    description: \"Comma delimited list of default mount options, for example: 'proto=udp'. Do not specify `nfsvers` option, it will be ignored.\"\n    type: \"string\"\n  - variable: \"NFS_VERS\"\n    label: NFS Version\n    description: Default NFS version to use\n    type: enum\n    required: true\n    default: nfsvers=4\n    options:\n    - nfsvers=4\n    - nfsvers=3\n  - variable: ON_REMOVE\n    label: On Remove\n    description: On removal of Rancher NFS volume, should the underlying data be retained or purged.\n    type: enum\n    required: true\n    default: purge\n    options:\n    - purge\n    - retain\n  - variable: RANCHER_DEBUG\n    label: Debug Mode\n    type: enum\n    description: Enable or disable verbose logging\n    default: false\n    options:\n    - true\n    - false\nnfs-driver:\n  storage_driver:\n    name: rancher-nfs\n    scope: environment\n    volume_access_mode: multiHostRW\n",
        "externalId": "catalog://library:infra*nfs:4"
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, data=json.dumps(
        payload), auth=(access_key, access_key_secret))
    time.sleep(0.2)
    self_url = response.json()['links']['self']
    stack_name = response.json()['name']
    active = False
    while not active:
        response = requests.get(self_url, headers=headers, auth=(
            access_key, access_key_secret))
        if ('state' in response.json()) and (response.json()['state'] == 'active'):
            active = True
        else:
            logging.info('Waiting for stack: %s CODE: %s STATUS: %s' % (
                stack_name, response.status_code, 'state' in response.json() and response.json()['state'] or '-'))
            time.sleep(0.2)
    return response.json()


def rancher_create_stack(rancher_url, access_key, access_key_secret, pid, stack_dir, stack_name, stack_description=None, start=False, stack_system=False):
    url = os.path.join(rancher_url, 'v2-beta/projects/%s/stacks' % pid)
    payload = {
        "name": stack_name,
        "description": stack_description,
        "dockerCompose": open(os.path.join(stack_dir,stack_name,'docker-compose.yml'), 'r').read(),
        "rancherCompose": open(os.path.join(stack_dir,stack_name,'rancher-compose.yml'), 'r').read(),
        "startOnCreate": start,
        "system": stack_system,
    }
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), auth=(access_key, access_key_secret))
    time.sleep(0.2)
    self_url = response.json()['links']['self']
    stack_name = response.json()['name']
    active = False
    while not active:
        response = requests.get(self_url, headers=headers, auth=(access_key, access_key_secret))
        if ('state' in response.json()) and (response.json()['state'] == 'active'):
            active = True
        else:
            logging.info('Waiting for stack: %s CODE: %s STATUS: %s' % (stack_name, response.status_code, 'state' in response.json() and response.json()['state'] or '-' ))
            time.sleep(0.2)
    return response.json()

if __name__ == '__main__':
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    rootLogger = logging.getLogger()

    fileHandler = logging.FileHandler("{0}/{1}.log".format(LOG_PATH, LOG_FILE))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    rootLogger.setLevel(LOG_LEVEL)

    rancher_local_url = rancher_url = RANCHER_ENDPOINT
    logging.debug("Rancher URL: %s" % rancher_url)

    status_code = wait_for_rancher(rancher_local_url)
    if status_code == 200:
        try:
            if KV_CONSUL == KV_ETCD:
                etcd_client = etcd.Client()
            elif KV_CONSUL == KV_CONSUL:
                consul_client = consul.Consul()

            logging.info("Performing first time configuration")
            pid = rancher_get_pid(rancher_local_url)
            logging.debug('PID: %s' % pid)
            tid = rancher_get_tid(rancher_local_url, pid)
            logging.debug('TID: %s' % tid)

            rancher_settings_update(rancher_local_url, 'api.host', rancher_url)
            logging.debug('Updating setting: "api.host" = "%s"' % rancher_url)

            rancher_settings_update(rancher_url, 'supported.docker.range', RANCHER_SUPPORTED_DOCKER_VERSIONS)
            logging.debug('Updating setting: "supported.docker.range" = "%s"' % RANCHER_SUPPORTED_DOCKER_VERSIONS)

            rancher_add_catalog(rancher_local_url, 'V3', 'https://github.com/siemonster/v3-vmware')
            logging.debug('Adding Rancher catalog: %s: %s' % ('V3', 'https://github.com/siemonster/v3-vmware'))

            for cert_name, cert, key in fs_list_certificates(RANCHER_CERT_DIR):
                logging.debug('Adding a certificate: %s' % cert)
                with open(os.path.join(RANCHER_CERT_DIR, cert), 'r') as cert_fn, open(os.path.join(RANCHER_CERT_DIR, key), 'r') as key_fn:
                    rancher_add_certificate(rancher_local_url, pid, name=cert_name, cert=cert_fn.read(), key=key_fn.read())

            registration_url = rancher_get_registration_url(rancher_local_url, pid, tid)
            logging.debug('Registration URL: %s' % registration_url)

            access_key, access_key_secret = rancher_create_access_key(rancher_local_url)
            logging.debug('Created ACCESS_KEY: %s ACCESS_KEY_SECRET: %s' % (access_key, access_key_secret))

            time.sleep(60)
            logging.info('Creating nfs stack...')
            rancher_create_nfs_stack(rancher_local_url, access_key, access_key_secret, pid, start=True)

            for stack in fs_list_stacks(RANCHER_STASK_DIR_USER):
                res = rancher_create_stack(rancher_local_url, access_key, access_key_secret, pid,
                                           RANCHER_STASK_DIR_USER, stack)
                if res == 0:
                    logging.info('Creating user stack: %s ... OK' % stack)
                else:
                    logging.error('Creating user stack: %s ... FAILED' % stack)

            resp = rancher_set_local_auth_config(rancher_local_url, RANCHER_ADMIN_NAME, RANCHER_ADMIN_USERNAME, RANCHER_ADMIN_PASSWORD)
            logging.debug('Set local auth config: %s' % resp)
            if registration_url:
                if KV_CONSUL == KV_ETCD:
                    logging.info('Setting ETCD record...')
                    etcd_client.write('/services/rancher/mgmt', registration_url)
                elif KV_CONSUL == KV_CONSUL:
                    logging.info('Setting Consul record...')
                    consul_client.kv.put('services/rancher/mgmt', registration_url)
            else:
                logging.error('No registration URL')
                raise ValueError('No registration URL')
        except Exception as e:
            logging.error("%s" % e)
            raise

    elif status_code == 401:
        logging.info("Rancher already configured")