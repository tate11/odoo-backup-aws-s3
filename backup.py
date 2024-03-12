# -*- coding:utf-8 -*-

import logging
import json
import boto3
import subprocess
from botocore.exceptions import ClientError

def backup_db():
    odoo_db_config_file = '/root/.aws/odoo-db.json'
    odoo_db_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/test.json"
    with open(odoo_db_config_file, 'r') as f:
        data = json.load(f)
    db_host = data.get('host', 'localhost')
    db_port = str(data.get('port', 5432))
    db_user = data.get('user', 'odoo')
    db_password = data.get('password', 'odoo')
    db_name = data.get('db_name', 'odoo')
    command = f"export PGPASSWORD={db_password} && pg_dump -h {db_host} -p {db_port} -U {db_user} --no-owner --format=c {db_name} > /tmp/backup.sql"
    process = subprocess.run(command,shell=True, capture_output=True)
    if process.returncode != 0:
        print("Error executing command:", process.stderr)
    else:
        print("Output:", process.stdout)


def get_odoo_config():
    config_file = open('/etc/odoo/odoo.conf')
    need_keys = ['db_name', 'db_host', 'db_user', 'db_password', 'db_port']
    config_dict = {}
    with open(config_file, 'r') as f:
        data = f.read()
        for line in data.splitlines():
            if not line or line.startswith('#') or line.startswith(';'):  # Skip empty lines and comments
                continue
            key, value = line.strip().split('=', 1)
            config_dict[key.strip()] = value.strip()
    return config_dict


def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True

backup_db()