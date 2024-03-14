# -*- coding:utf-8 -*-

import logging
import json
import boto3
import subprocess
from botocore.exceptions import ClientError
import os
import paramiko


def notify_error_and_stop_script(error):
    # todo: 
    # - write error to log file
    # - send telegram message here to notify error
    exit()


def populate_variable():
    global secret_path
    global odoo_db_config_file
    global odoo_server_config_file
    global db_backup_file_path
    global filestore_backup_file_path
    secret_path = os.environ.get('SECRET_PATH', '')
    odoo_db_config_file = os.path.join(secret_path, 'odoo-db.json')
    odoo_server_config_file = os.path.join(secret_path, 'odoo-server.json')
    db_backup_file_path = '/tmp/backup.sql'
    filestore_backup_file_path = '/tmp/filestore'


def get_db_config(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    return config


def execute_backup_db(**kwargs):
    host = kwargs.get('db_host')
    user = kwargs.get('db_user')
    password = kwargs.get('db_password')
    port = kwargs.get('db_port')
    db_name = kwargs.get('db_name')
    db_backup_file_path = kwargs.get('db_backup_file_path')

    command = f"export PGPASSWORD={password} && pg_dump -h {host} -p {port} -U {user} --no-owner --format=c {db_name} > {db_backup_file_path}"
    process = subprocess.run(command, shell=True, capture_output=True)
    if process.returncode != 0:
        logging.error(f"Error backing up database: {process.stderr}")
        notify_error_and_stop_script(process.stderr)
    return True


def backup_db():
    db_config = get_db_config(odoo_db_config_file)
    db_config['db_backup_file_path'] = db_backup_file_path
    execute_backup_db(**db_config)


# =============== filestore =================

def get_server_config(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    key_file = config.get('key_file')
    key_file_path = os.path.join(secret_path, key_file)
    config.update(dict(
        key_file_path=key_file_path,
        filestore_backup_file_path=filestore_backup_file_path
    ))
    return config


def connect_server(**kwargs):
    host = kwargs.get('server_host')
    user = kwargs.get('server_user')
    port = kwargs.get('server_port')
    key_file_path = kwargs.get('key_file_path')
    # fixme
    key_file_path = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/cuulong16g_key.pem"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        key = paramiko.RSAKey.from_private_key_file(key_file_path)
        ssh.connect(hostname=host, username=user, port=port, pkey=key)
        return ssh
    except paramiko.AuthenticationException:
        notify_error_and_stop_script("Authentication failed!")


def execute_backup_filestore(ssh, **kwargs):
    odoo_docker_image = kwargs.get('odoo_docker_image')
    if odoo_docker_image:
        execute_backup_filestore_docker(ssh, **kwargs)
    else:
        execute_backup_filestore_normal(ssh, **kwargs)


def execute_backup_filestore_docker(ssh, **kwargs):
    def execute_host_command(command):
        stdin, stdout, stderr = ssh.exec_command(command)
        return stdout.read().decode()

    def get_odoo_container_id():
        odoo_docker_image = kwargs.get('odoo_docker_image')
        command = "docker ps -q -a | xargs docker inspect --format '{{.Id}} {{.Config.Image}}' | awk -v img=\"%s\" '$2 == img {print $1}'" % odoo_docker_image
        return execute_host_command(command).strip()

    db_name = kwargs.get('db_name')
    datadir_path = kwargs.get('datadir_path')
    filestore_path = os.path.join(datadir_path, 'filestore', db_name)
    container_id = get_odoo_container_id()

    filestore_backup_name = f"{db_name}.tar.gz"
    filestore_backup_path = f"/tmp/{filestore_backup_name}"
    backup_command = f'docker exec {container_id} sh -c "tar czf {filestore_backup_path} {filestore_path}"'
    execute_host_command(backup_command)

    copy_backup_file_to_host_command = f"docker cp {container_id}:{filestore_backup_path} {filestore_backup_path}"
    execute_host_command(copy_backup_file_to_host_command)

    sftp_client = ssh.open_sftp()
    local_filestore_backup_path = filestore_backup_path
    sftp_client.get(remotepath=filestore_backup_path, localpath=local_filestore_backup_path)
    execute_host_command(f'rm -rf {filestore_backup_path}')

    return local_filestore_backup_path


def execute_backup_filestore_normal(ssh, **kwargs):
    pass


def backup_filestore():
    # fixme:
    odoo_server_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/odoo-server.json"
    odoo_db_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/odoo-db.json"
    # fixme above
    server_config = get_server_config(odoo_server_config_file)
    db_config = get_db_config(odoo_db_config_file)
    config = {**server_config, **db_config}
    ssh = connect_server(**server_config)
    execute_backup_filestore(ssh, **config)
    ssh.close()


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
