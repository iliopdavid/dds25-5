FROM python:3.12-slim

WORKDIR /home/flask-app

COPY ./requirements.txt .

RUN pip install -r requirements.txt
RUN pip install --upgrade google-api-python-client

COPY . .

RUN apt-get update && apt-get install -y supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

EXPOSE 50051 5000