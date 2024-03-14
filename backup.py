# -*- coding:utf-8 -*-

import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import logging
import json
import subprocess
import os
import paramiko

DATE_FORMAT = '%Y-%m-%d_%H-%M-%S'


def notify_error_and_stop_script(error):
    # todo: 
    # - write error to log file
    # - send telegram message here to notify error
    print(error)
    exit()


def get_common_config():
    secret_path = os.environ.get('SECRET_PATH', '')
    db_config_file = os.path.join(secret_path, 'odoo-db.json')
    server_config_file = os.path.join(secret_path, 'odoo-server.json')
    local_backup_folder = '/tmp/odoo-backup'
    subprocess.run(f'mkdir -p {local_backup_folder}', shell=True)

    local_db_backup_file_name = 'backup.sql'
    local_filestore_backup_file_name = 'filestore.tar.gz'
    local_db_backup_file_path = os.path.join(local_backup_folder, local_db_backup_file_name)
    local_filestore_backup_file_path = os.path.join(local_backup_folder, local_filestore_backup_file_name)
    # fixme
    db_config_file = '/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/odoo-db.json'
    server_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/odoo-server.json"
    # server_config_file = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/internal-aws.json"
    # fixme
    return dict(
        secret_path=secret_path,
        db_config_file=db_config_file,
        server_config_file=server_config_file,
        local_db_backup_file_name=local_db_backup_file_name,
        local_filestore_backup_file_name=local_filestore_backup_file_name,
        local_backup_folder=local_backup_folder,
        local_db_backup_file_path=local_db_backup_file_path,
        local_filestore_backup_file_path=local_filestore_backup_file_path,
    )


# ================= Backup Database =================

def get_db_config():
    common_config = get_common_config()
    db_config_file = common_config.get('db_config_file')
    with open(db_config_file, 'r') as f:
        config = json.load(f)
        return {**common_config, **config}


def execute_backup_db(**kwargs):
    host = kwargs.get('db_host')
    user = kwargs.get('db_user')
    password = kwargs.get('db_password')
    port = kwargs.get('db_port')
    db_name = kwargs.get('db_name')
    local_db_backup_file_path = kwargs.get('local_db_backup_file_path')

    command = f"export PGPASSWORD={password} && pg_dump -h {host} -p {port} -U {user} --no-owner --format=c {db_name} > {local_db_backup_file_path}"
    process = subprocess.run(command, shell=True, capture_output=True)
    if process.returncode != 0:
        logging.error(f"Error backing up database: {process.stderr}")
        notify_error_and_stop_script(process.stderr)


def backup_db():
    db_config = get_db_config()
    execute_backup_db(**db_config)


# =============== filestore =================

def get_server_config():
    common_config = get_common_config()
    db_config = get_db_config()
    server_config_file = common_config.get('server_config_file')
    with open(server_config_file, 'r') as f:
        config = json.load(f)
    key_file = config.get('key_file')
    secret_path = common_config.get('secret_path')
    key_file_path = os.path.join(secret_path, key_file)
    config.update(dict(
        key_file_path=key_file_path,
    ))
    return {**common_config, **db_config, **config}


def connect_server(**kwargs):
    host = kwargs.get('server_host')
    user = kwargs.get('server_user')
    port = kwargs.get('server_port')
    key_file_path = kwargs.get('key_file_path')
    # fixme
    key_file_path = "/home/xmars/dev/odoo-project/odoo-backup-aws-s3-docker/secret/cuulong16g_key.pem"
    # key_file_path = "/home/xmars/Downloads/vdx-internal.pem"
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
    docker_datadir_path = kwargs.get('datadir_path')
    docker_filestore_path = os.path.join(docker_datadir_path, 'filestore')
    container_id = get_odoo_container_id()

    docker_filestore_backup_name = f"{db_name}.tar.gz"
    docker_filestore_backup_path = f"/tmp/{docker_filestore_backup_name}"
    backup_command = f'docker exec {container_id} sh -c "cd {docker_filestore_path} && tar cf {docker_filestore_backup_path} {db_name}"'
    execute_host_command(backup_command)

    host_filestore_backup_path = f"/tmp/{db_name}.tar.gz"
    copy_backup_file_to_host_command = f"docker cp {container_id}:{docker_filestore_backup_path} {host_filestore_backup_path}"
    execute_host_command(copy_backup_file_to_host_command)

    sftp_client = ssh.open_sftp()
    local_filestore_backup_file_path = kwargs.get('local_filestore_backup_file_path')
    sftp_client.get(remotepath=host_filestore_backup_path, localpath=local_filestore_backup_file_path)
    execute_host_command(f'rm -rf {host_filestore_backup_path}')
    execute_host_command(f'docker exec {container_id} sh -c "rm -rf {docker_filestore_backup_path}"')


def execute_backup_filestore_normal(ssh, **kwargs):
    def execute_host_command(command):
        stdin, stdout, stderr = ssh.exec_command(command)
        return stdout.read().decode()

    db_name = kwargs.get('db_name')
    datadir_path = kwargs.get('datadir_path')
    filestore_path = os.path.join(datadir_path, 'filestore')

    filestore_backup_name = f"{db_name}.tar.gz"
    filestore_backup_path = f"/tmp/{filestore_backup_name}"
    backup_command = f'cd {filestore_path} && tar czf {filestore_backup_path} {db_name}'
    execute_host_command(backup_command)

    sftp_client = ssh.open_sftp()
    local_filestore_backup_file_path = kwargs.get('local_filestore_backup_file_path')
    sftp_client.get(remotepath=filestore_backup_path, localpath=local_filestore_backup_file_path)
    execute_host_command(f'rm -rf {filestore_backup_path}')


def backup_filestore():
    server_config = get_server_config()
    ssh = connect_server(**server_config)
    execute_backup_filestore(ssh, **server_config)
    ssh.close()


def compress_backup_files():
    config = get_server_config()
    db_config = get_db_config()
    local_db_backup_file_name = config['local_db_backup_file_name']
    local_filestore_backup_file_name = config['local_filestore_backup_file_name']
    local_backup_folder = config['local_backup_folder']
    local_backup_file_name = f"{datetime.now(timezone.utc).strftime(DATE_FORMAT)}_{config['db_name']}.tar.gz"
    subprocess.run(
        f'cd {local_backup_folder} && tar -cf {local_backup_file_name} {local_db_backup_file_name} {local_filestore_backup_file_name}')

    return os.path.join(local_backup_folder, local_backup_file_name)


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
    backup_db()
    backup_filestore()
    backup_file = compress_backup_files()


main()
