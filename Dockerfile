FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .

RUN python3 -m pip install --no-cache-dir -r requirements.txt
RUN rm requirements.txt

COPY nomad_backup_operator ./nomad_backup_operator

CMD ["python3", "-m", "nomad_backup_operator"]
