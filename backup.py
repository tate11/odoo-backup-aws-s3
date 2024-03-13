# -*- coding:utf-8 -*-

import logging
import json
import boto3
import subprocess
from botocore.exceptions import ClientError
import os
import paramiko

def populate_variable():
    global secret_path
    global odoo_db_config_file
    global odoo_server_config_file
    global db_backup_file_path
    global filestore_backup_file_path
    secret_path=os.environ.get('SECRET_PATH', '')
    odoo_db_config_file = os.path.join(secret_path, 'odoo-db.json')
    odoo_server_config_file = os.path.join(secret_path, 'odoo-server.json')
    db_backup_file_path = '/tmp/backup.sql'
    filestore_backup_file_path = '/tmp/filestore'

def get_db_config(config_file):
    with open(config_file, 'r') as f:
        data = json.load(f)
    host = data.get('host', 'localhost')
    port = str(data.get('port', 5432))
    user = data.get('user', 'odoo')
    password = data.get('password', 'odoo')
    db_name = data.get('db_name', 'odoo')
    
    return dict(
        host=host,
        port=port,
        user=user,
        password=password,
        db_name=db_name,
        db_backup_file_path=db_backup_file_path
    )
    
def execute_backup_db(**kwargs):
    host = kwargs.get('host')
    user = kwargs.get('user')
    password = kwargs.get('password')
    port = kwargs.get('port')
    db_name = kwargs.get('db_name')
    db_backup_file_path = kwargs.get('db_backup_file_path')
    
    command = f"export PGPASSWORD={password} && pg_dump -h {host} -p {port} -U {user} --no-owner --format=c {db_name} > {db_backup_file_path}"
    process = subprocess.run(command,shell=True, capture_output=True)
    if process.returncode != 0:
        logging.error(f"Error backing up database: {process.stderr}")
        # todo: 
        # - write error to log file
        # - send telegram message here to notify backup failed
        exit()
    return True
    
def backup_db():
    db_config = get_db_config(odoo_db_config_file)
    execute_backup_db(**db_config)

# =============== filestore =================

def get_server_config(config_file):
    with open(config_file, 'r') as f:
        data = json.load(f)
    host = data.get('host')
    user = data.get('user')
    port = data.get('port')
    key_file = data.get('key_file')
    key_file_path = os.path.join(secret_path, key_file)
    return dict(
        host=host,
        user=user,
        port=port,
        key_file_path=key_file_path,    
        filestore_backup_file_path=filestore_backup_file_path
    )
    
def connect_server(**kwargs):
    host = kwargs.get('host')
    user = kwargs.get('user')
    port = kwargs.get('port')
    key_file_path = kwargs.get('key_file_path')
    filestore_backup_file_path = kwargs.get('filestore_backup_file_path')
    #fixme
    key_file_path = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/cuulong16g_key.pem"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        key = paramiko.RSAKey.from_private_key_file(key_file_path)
        ssh.connect(hostname=host, username=user, port=port, pkey=key)
        return ssh
    except paramiko.AuthenticationException:
        logging.error("Authentication failed!")
        return False    
    
def execute_backup_filestore(**kwargs):
    host = kwargs.get('host')
    user = kwargs.get('user')
    port = kwargs.get('port')
    key_file_path = kwargs.get('key_file_path')
    filestore_backup_file_path = kwargs.get('filestore_backup_file_path')
    #fixme
    key_file_path = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/cuulong16g_key.pem"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        key = paramiko.RSAKey.from_private_key_file(key_file_path)
        ssh.connect(hostname=host, username=user, port=port, pkey=key)
        backup_command = ""
        stdin, stdout, stderr = ssh.exec_command(command)

    except paramiko.AuthenticationException:
        logging.error("Authentication failed!")
        return False
    
def backup_filestore():
    odoo_server_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/odoo-server.json"
    server_config = get_server_config(odoo_server_config_file)
    execute_backup_filestore(**server_config)
    




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

def main():
    populate_variable()
    # backup_db()
    backup_filestore()
    
    
main()