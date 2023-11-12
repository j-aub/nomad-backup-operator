FROM python:3.12-alpine

ARG RESTIC_VERSION=0.16.0
ARG RESTIC_CHECKSUM=sha256:492387572bb2c4de904fa400636e05492e7200b331335743d46f2f2874150162

# some utilities for writing hooks
RUN apk --no-cache add -f \
	coreutils \
	curl \
	jq \
	unzip \
	zip \
	bzip2

# restic install
WORKDIR /usr/local/bin

ADD --checksum=${RESTIC_SHA256} https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_amd64.bz2 restic.bz2

RUN bzip2 -d restic.bz2 && \
	chmod +x restic

# app install
WORKDIR /app

COPY requirements.txt .

RUN python3 -m pip install --no-cache-dir -r requirements.txt
RUN rm requirements.txt

COPY nomad_backup ./nomad_backup

VOLUME ["/repository", "/backup"]

CMD ["python3", "-m", "nomad_backup"]
