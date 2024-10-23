FROM python:3.11-slim

COPY . /app/

WORKDIR /app

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

CMD [ "python", "exporter.py", "--attachment-dir", "/app/data/attachments"]