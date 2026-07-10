#!/bin/sh
set -eu

mkdir -p /data
touch '/data/First Run'
rm -rf /data/Singleton*

echo "sandbox entrypoint starting supervisord"
exec supervisord -c /supervisord.conf
