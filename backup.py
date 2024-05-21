# -*- coding:utf-8 -*-

import asyncio
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import logging
import json
import subprocess
import os
import paramiko
import telegram
import re

DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"


async def send_telegram_message(message):
    config = get_config()
    server_host = config["server_host"]
    message = f"""
Backup on server {server_host}:
{message}
    """
    telegram_token = config["telegram_token"]
    telegram_channel = config["telegram_channel"]
    bot = telegram.Bot(token=telegram_token)
    await bot.send_message(chat_id=telegram_channel, text=message)


def notify_error_and_stop_script(error):
    message = f"🐞ERROR🐞: {error}"
    asyncio.run(send_telegram_message(message))
    exit()


def get_common_config():
    s3_storage_class = "STANDARD_IA"
    secret_path = os.environ.get("BACKUP_SECRET_PATH", "/root/.aws")
    db_config_file = os.path.join(secret_path, "db.json")
    server_config_file = os.path.join(secret_path, "server.json")

    return dict(
        secret_path=secret_path,
        db_config_file=db_config_file,
        server_config_file=server_config_file,
        s3_storage_class=s3_storage_class,
    )


def get_db_config():
    common_config = get_common_config()
    db_config_file = common_config.get("db_config_file")
    with open(db_config_file, "r") as f:
        config = json.load(f)
        return {**common_config, **config}


def get_config():
    common_config = get_common_config()
    db_config = get_db_config()
    server_config_file = common_config.get("server_config_file")
    with open(server_config_file, "r") as f:
        config = json.load(f)
    key_file = config.get("key_file")
    secret_path = common_config.get("secret_path")
    key_file_path = os.path.join(secret_path, key_file)
    config.update(
        dict(
            key_file_path=key_file_path,
        )
    )
    final_config = {**common_config, **db_config, **config}
    local_backup_folder = final_config.get("local_backup_folder")
    subprocess.run(f"mkdir -p {local_backup_folder}", shell=True)

    local_db_backup_file_name = "backup.sql"
    local_filestore_backup_file_name = "filestore.tar.gz"
    local_db_backup_file_path = os.path.join(
        local_backup_folder, local_db_backup_file_name
    )
    local_filestore_backup_file_path = os.path.join(
        local_backup_folder, local_filestore_backup_file_name
    )

    final_config.update(
        **dict(
            local_db_backup_file_name=local_db_backup_file_name,
            local_filestore_backup_file_name=local_filestore_backup_file_name,
            local_backup_folder=local_backup_folder,
            local_db_backup_file_path=local_db_backup_file_path,
            local_filestore_backup_file_path=local_filestore_backup_file_path,
        )
    )
    return final_config


def connect_server(**kwargs):
    host = kwargs.get("server_host")
    user = kwargs.get("server_user")
    port = kwargs.get("server_port")
    key_file_path = kwargs.get("key_file_path")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        key = paramiko.RSAKey.from_private_key_file(key_file_path)
        ssh.connect(hostname=host, username=user, port=port, pkey=key)
        return ssh
    except paramiko.AuthenticationException:
        notify_error_and_stop_script(
            "Authentication failed! - can't connect to Odoo server"
        )


def execute_server_command(ssh, command):
    stdin, stdout, stderr = ssh.exec_command(command)
    error_message = stderr and stderr.read().decode()
    if error_message:
        notify_error_and_stop_script(error_message)
    return stdout.read().decode()


def get_odoo_container_id(ssh, **kwargs):
    odoo_docker_image = kwargs.get("odoo_docker_image")
    command = (
            "docker ps -q -a | xargs docker inspect --format '{{.Id}} {{.Config.Image}}' | awk -v img=\"%s\" '$2 == img {print $1}'"
            % odoo_docker_image
    )
    return execute_server_command(ssh, command).strip()


def is_older_file(file_name, number_of_days):
    current_datetime = datetime.now(timezone.utc)
    date_str = re.search(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", file_name)
    if not date_str:
        return False
    # add offset aware to compare with utc datetime
    date_str = f"{date_str[0]} +0000"
    file_datetime = datetime.strptime(date_str, DATE_FORMAT + " %z")
    if (current_datetime - file_datetime).days > number_of_days:
        return True
    return False


# ================= Backup Database =================
def execute_backup_db(ssh, **kwargs):
    odoo_docker_image = kwargs.get("odoo_docker_image")
    if odoo_docker_image:
        execute_backup_db_docker(ssh, **kwargs)
    else:
        execute_backup_db_normal(ssh, **kwargs)


def execute_backup_db_normal(ssh, **kwargs):
    host = kwargs.get("db_host")
    user = kwargs.get("db_user")
    password = kwargs.get("db_password")
    port = kwargs.get("db_port")
    db_name = kwargs.get("db_name")
    local_db_backup_file_path = kwargs.get("local_db_backup_file_path")
    server_db_backup_file_path = f"/tmp/{db_name}_{datetime.now().timestamp()}"

    try:
        command = f"export PGPASSWORD={password} && pg_dump -h {host} -p {port} -U {user} --no-owner --format=c {db_name} > {server_db_backup_file_path}"
        execute_server_command(ssh, command)
        sftp_client = ssh.open_sftp()
        sftp_client.get(
            remotepath=server_db_backup_file_path, localpath=local_db_backup_file_path
        )
        execute_server_command(ssh, f"rm -rf {server_db_backup_file_path}")
        sftp_client.close()
    except Exception as e:
        notify_error_and_stop_script(e)


def execute_backup_db_docker(ssh, **kwargs):
    host = kwargs.get("db_host")
    user = kwargs.get("db_user")
    password = kwargs.get("db_password")
    port = kwargs.get("db_port")
    db_name = kwargs.get("db_name")
    local_db_backup_file_path = kwargs.get("local_db_backup_file_path")
    server_db_backup_file_path = f"/tmp/{db_name}_{datetime.now().timestamp()}.sql"

    try:
        container_id = get_odoo_container_id(ssh, **kwargs)
        command = f"export PGPASSWORD={password} && pg_dump -h {host} -p {port} -U {user} --no-owner --format=c {db_name} > {server_db_backup_file_path}"
        docker_command = f'docker exec {container_id} sh -c "{command}"'
        execute_server_command(ssh, docker_command)
        execute_server_command(
            ssh,
            f"docker cp {container_id}:{server_db_backup_file_path} {server_db_backup_file_path}",
        )

        sftp_client = ssh.open_sftp()
        sftp_client.get(
            remotepath=server_db_backup_file_path, localpath=local_db_backup_file_path
        )
        execute_server_command(ssh, f"rm -rf {server_db_backup_file_path}")
        execute_server_command(
            ssh,
            f'docker exec {container_id} sh -c "rm -rf {server_db_backup_file_path}"',
        )
        sftp_client.close()
    except Exception as e:
        notify_error_and_stop_script(e)


def backup_db():
    config = get_config()
    ssh_client = connect_server(**config)
    execute_backup_db(ssh_client, **config)
    ssh_client.close()


# =============== Backup filestore =================
def execute_backup_filestore(ssh, **kwargs):
    odoo_docker_image = kwargs.get("odoo_docker_image")
    if odoo_docker_image:
        execute_backup_filestore_docker(ssh, **kwargs)
    else:
        execute_backup_filestore_normal(ssh, **kwargs)


def execute_backup_filestore_docker(ssh, **kwargs):
    db_name = kwargs.get("db_name")
    docker_datadir_path = kwargs.get("datadir_path")
    docker_filestore_path = os.path.join(docker_datadir_path, "filestore")
    container_id = get_odoo_container_id(ssh, **kwargs)

    docker_filestore_backup_name = f"{db_name}.tar.gz"
    docker_filestore_backup_path = f"/tmp/{docker_filestore_backup_name}"
    backup_command = f'docker exec {container_id} sh -c "cd {docker_filestore_path} && tar cf {docker_filestore_backup_path} {db_name}"'
    execute_server_command(ssh, backup_command)

    host_filestore_backup_path = f"/tmp/{db_name}.tar.gz"
    copy_backup_file_to_host_command = f"docker cp {container_id}:{docker_filestore_backup_path} {host_filestore_backup_path}"
    execute_server_command(ssh, copy_backup_file_to_host_command)

    sftp_client = ssh.open_sftp()
    local_filestore_backup_file_path = kwargs.get("local_filestore_backup_file_path")
    sftp_client.get(
        remotepath=host_filestore_backup_path,
        localpath=local_filestore_backup_file_path,
    )
    execute_server_command(ssh, f"rm -rf {host_filestore_backup_path}")
    execute_server_command(
        ssh, f'docker exec {container_id} sh -c "rm -rf {docker_filestore_backup_path}"'
    )
    sftp_client.close()


def execute_backup_filestore_normal(ssh, **kwargs):
    db_name = kwargs.get("db_name")
    datadir_path = kwargs.get("datadir_path")
    filestore_path = os.path.join(datadir_path, "filestore")

    filestore_backup_name = f"{db_name}.tar.gz"
    filestore_backup_path = f"/tmp/{filestore_backup_name}"
    backup_command = f"cd {filestore_path} && tar czf {filestore_backup_path} {db_name}"
    execute_server_command(ssh, backup_command)

    sftp_client = ssh.open_sftp()
    local_filestore_backup_file_path = kwargs.get("local_filestore_backup_file_path")
    sftp_client.get(
        remotepath=filestore_backup_path, localpath=local_filestore_backup_file_path
    )
    execute_server_command(ssh, f"rm -rf {filestore_backup_path}")
    sftp_client.close()


def backup_filestore():
    server_config = get_config()
    ssh = connect_server(**server_config)
    execute_backup_filestore(ssh, **server_config)
    ssh.close()


def compress_backup_files():
    config = get_config()
    local_db_backup_file_name = config["local_db_backup_file_name"]
    local_filestore_backup_file_name = config["local_filestore_backup_file_name"]
    local_backup_folder = config["local_backup_folder"]
    local_backup_file_name = (
        f"{config['db_name']}_{datetime.now(timezone.utc).strftime(DATE_FORMAT)}.tar.gz"
    )
    subprocess.run(
        f'cd {local_backup_folder} && tar -cf "{local_backup_file_name}" {local_db_backup_file_name} {local_filestore_backup_file_name}',
        shell=True,
    )
    return os.path.join(local_backup_folder, local_backup_file_name)


# ============================= AWS S3 ===============================
def get_bucket_name(s3_client, **kwargs):
    server_host = kwargs.get("server_host")
    server_host = server_host.replace(".", "-")
    s3_bucket_name = f"server-{server_host}-odoo-backup"
    try:
        s3_client.head_bucket(Bucket=s3_bucket_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":  # Bucket not found (doesn't exist)
            s3_client.create_bucket(Bucket=s3_bucket_name)
            logging.info(f"Bucket '{s3_bucket_name}' created successfully!")
        else:
            notify_error_and_stop_script(f"AWS S3: An unexpected error occurred: {e}")
    return s3_bucket_name


def get_list_files(s3_client, bucket_name):
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        if "Contents" in response:
            object_names = [obj["Key"] for obj in response["Contents"]]
            return object_names
    except ClientError as e:
        pass
    return False


def delete_old_files(s3_client, list_files, bucket_name, day_to_retains):
    if not list_files:
        return False
    old_files = []

    for file_name in list_files:
        if is_older_file(file_name, day_to_retains):
            old_files.append(file_name)
    if not old_files:
        return True

    try:
        delete_file_objects = [{"Key": f} for f in old_files]
        s3_client.delete_objects(
            Bucket=bucket_name, Delete={"Objects": delete_file_objects, "Quiet": True}
        )
    except ClientError as e:
        notify_error_and_stop_script(f"Delete object error: {e}")


def upload_file(s3_client, file_name, bucket, **kwargs):
    s3_storage_class = kwargs.get("s3_storage_class")
    object_name = os.path.basename(file_name)
    try:
        s3_client.upload_file(
            file_name, bucket, object_name, ExtraArgs={"StorageClass": s3_storage_class}
        )
        asyncio.run(
            send_telegram_message(f"🎉🎉🎉 Backup success a file named {file_name}")
        )
    except ClientError as e:
        notify_error_and_stop_script(
            f"AWS S3: Upload backup file failed with error: {e}"
        )
    return True


def backup_file_on_s3(backup_file):
    config = get_config()
    if not config.get("put_to_aws_s3"):
        return False
    number_of_day_to_retain = config.get("num_day_to_retain")
    s3_client = boto3.client("s3")
    s3_bucket_name = get_bucket_name(s3_client, **config)
    list_files = get_list_files(s3_client, s3_bucket_name)
    delete_old_files(s3_client, list_files, s3_bucket_name, number_of_day_to_retain)
    upload_file(s3_client, backup_file, s3_bucket_name, **config)


def delete_local_file(file_name):
    config = get_config()
    local_backup_folder = config.get("local_backup_folder")
    files_and_dirs = os.listdir(local_backup_folder)

    # Filter out directories, only keep files
    files = [f for f in files_and_dirs if os.path.isfile(os.path.join(local_backup_folder, f))]
    days_to_retain = config.get("num_day_to_retain")
    for file in files:
        if is_older_file(file, days_to_retain):
            subprocess.run(f"rm -rf {file_name}", shell=True)
    return True


def main():
    print(f"=========== Backup: {datetime.now(timezone.utc)} ==================")
    backup_db()
    backup_filestore()
    backup_file = compress_backup_files()
    backup_file_on_s3(backup_file)
    delete_local_file(backup_file)


main()
