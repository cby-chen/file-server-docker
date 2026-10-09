#!/bin/sh
set -eu
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 -keyout server.key -out server.crt -subj "/CN=file-server"
echo 'Certificate created.'
