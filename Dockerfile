FROM python:3.12.2-bullseye

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client cron

RUN mkdir -p /var/lib/odoo /etc/odoo

COPY ./secret /root/.aws
COPY ./entrypoint.sh /
COPY ./requirements.txt requirements.txt

RUN pip3 install -r requirements.txt
ENV SECRET_PATH /root/.aws


ENTRYPOINT [ "/entrypoint.sh" ]