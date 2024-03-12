FROM python:3.12.2-bullseye

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client cron

RUN pip3 install boto3

RUN mkdir -p /var/lib/odoo /etc/odoo

COPY ./secret /root/.aws
COPY ./entrypoint.sh /


ENTRYPOINT [ "/entrypoint.sh" ]