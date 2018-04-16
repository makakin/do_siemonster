#!/bin/bash
set -e

CONSUL_CLI_VER=0.3.1

mkdir -p /opt/bin

if [ ! -f "/opt/bin/consul-cli" ]; then
    curl -sSL https://github.com/mantl/consul-cli/releases/download/v${CONSUL_CLI_VER}/consul-cli_${CONSUL_CLI_VER}_linux_amd64.tar.gz | tar xvz --strip-components=1 -C /opt/bin/
fi
