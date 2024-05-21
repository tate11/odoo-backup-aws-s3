# About

This script is designed to backup Odoo databases and filestores to AWS S3.

## Instructions

1. Add below files to **secret** folder:

   - **_db.json_**

     ```json
     {
         "db_host": "localhost",
         "db_user": "odoo",
         "db_password": "odoo",
         "db_port": 5432,
         "db_name": "odoo_database_name"
     }
     ```

   - **_server.json_**

     ```json
     {
       "server_host": "12.34.56.78",
       "server_user": "root",
       "server_port": 22,
       "key_file": "private-key.pem - private key file to ssh to server - add the key file with the same name to the secret folder",
       "datadir_path": "datadir_folder_path",
       "odoo_docker_image": "if your Odoo server is running on host, ignore this parameter",
       "telegram_token": "telegram_bot_token_to_send_notifications",
       "telegram_channel": "telegram_channel_id"
     }
     ```

   - **_credentials_**

     ```config
     [default]
     aws_access_key_id = YOUR_ACCESS_KEY
     aws_secret_access_key = YOUR_SECRET_KEY
     ```

   - **_config_**

     ```config
     [default]
     region=us-east-1
     ```

2. Run the docker command, this will create a container with a cronjob run everyday, at 00:00

   ```shell
   docker run -d xmars/odoo-backup-aws-s3 -v <secret_folder_path>:/root/.aws

3. (Optional) If you want to run _backup.py_ script directly, create secret files in '~/.aws' and run script

    ```shell
    python3 -m venv venv
    source venv/bin/activate && pip install -r requirements.txt 
    BACKUP_SECRET_PATH=<secret_folder_path> AWS_SHARED_CREDENTIALS_FILE=<secret_folder_path>/credentials AWS_CONFIG_FILE=<secret_folder_path>/config python3 backup.py
    ```
