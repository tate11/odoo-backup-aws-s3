FROM python:slim-bullseye

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client cron

COPY ./requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
RUN mkdir -p /var/lib/odoo /etc/odoo

COPY ./secret /root/.aws
COPY ./entrypoint.sh /
COPY ./backup.py /
COPY /cronjob.setup /

ENV BACKUP_SECRET_PATH /root/.aws
ENV AWS_SHARED_CREDENTIALS_FILE /root/.aws/credentials
ENV AWS_CONFIG_FILE /root/.aws/config

RUN crontab /cronjob.setup

ENTRYPOINT [ "/entrypoint.sh" ]