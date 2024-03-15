# About
Backup Odoo database and filestore to S3 AWS

##  Instruction
1. Create a secret folder contain following files

- **_db.json_**
```json
{
    "db_host": "localhost",
    "db_user": "odoo",
    "db_password": "odoo",
    "db_port": 5432,
    "db_name": "odoo database name"
}

```
- **_server.json_**
```json
{
  "server_host": "12.34.56.78",
  "server_user": "root",
  "server_port": 22,
  "key_file": "private-key.pem",
  "datadir_path": "datadir folder path",
  "odoo_docker_image": "if your odoo server running on host, ignore this parameter",
  "telegram_token": "telegram bot token to send notify",
  "telegram_channel": "telegram channel id "
}

```
- **_credentials_**
```editorconfig
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```
- _**config**_
```editorconfig
[default]
region=us-east-1
```
1. Run command
```shell
docker run -d  xmars/odoo-backup-aws-s3 -v <secret_folder>:/root/.aws
```

# Reference
- [AWS S3 credentials](https://boto3.amazonaws.com/v1/documentation/api/1.16.53/guide/quickstart.html#configuration) 
- [AWS S3 boto3](https://boto3.amazonaws.com/v1/documentation/api/1.16.53/reference/services/s3.html#id224)
