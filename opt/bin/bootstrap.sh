#!/bin/bash
set -e

RANCHER_ADMIN_NAME=admin
RANCHER_ADMIN_USERNAME=admin
RANCHER_ADMIN_PASSWORD=siemonster
RANCHER_NFS_ON_REMOVE=purge

AVAHI_DOCKER_IMAGE=registry.gitlab.com/dmitryint/siemonster-avahi-rancher:master
#ETCD_DOCKER_IMAGE=quay.io/coreos/etcd:v2.3.8
CONSUL_DOCKER_IMAGE=consul:1.0.0
RANCHER_SERVER_DOCKER_IMAGE=rancher/server:v1.6.11
RANCHER_AGENT_DOCKER_IMAGE=rancher/agent:v1.2.7

BOOTSTRAP_EXPECT=5
BOOTSTRAP_DIR=/etc/bootstrap

CONSUL_PATH="services/rancher"

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/opt/bin

join_by()
{
    local IFS="$1"; shift; echo "$*";
}

if [ -f "/media/configdrive/docker_images" ]; then
    docker image load --input /media/configdrive/docker_images
fi

if [ ! -f "/opt/bin/consul-cli" ]; then
    curl -sSL https://github.com/mantl/consul-cli/releases/download/v0.3.1/consul-cli_0.3.1_linux_amd64.tar.gz | tar xvz --strip-components=1 -C /opt/bin/
fi

docker run --rm -i \
    --net=host \
    -v "${BOOTSTRAP_DIR}:/env" \
    -e "EXPECT_NODES=${BOOTSTRAP_EXPECT}" \
    ${AVAHI_DOCKER_IMAGE}


source ${BOOTSTRAP_DIR}/self.env
source ${BOOTSTRAP_DIR}/all_nodes.env
IFS=', ' read -r -a entire_ips <<< "$ALL_NODES_IPS"
IFS=', ' read -r -a entire_names <<< "$ALL_NODES_NAMES"
IFS=', ' read -r -a node_all_ips <<< "$NODE_IP_ADDRESSES_LIST"

entire=()
for index in ${!entire_ips[*]}; do
    entire+=("-retry-join=${entire_ips[$index]}")
done
CONSUL_CLUSTER_NODES="$(join_by ' ' ${entire[@]})"

port_mappings=()
advertise_peer_urls=()
for index in ${!node_all_ips[*]}; do
    port_mappings+=("-p ${node_all_ips[$index]}:8300-8302:8300-8302 -p ${node_all_ips[$index]}:8400:8400 -p ${node_all_ips[$index]}:8500:8500")
    advertise_peer_urls+=("-advertise=${node_all_ips[$index]}")
done
DOCKER_PORT_MAPS="$(join_by ' ' ${port_mappings[@]})"
CONSUL_ADVERTISE_PEER_URLS="$(join_by ' ' ${advertise_peer_urls[@]})"

echo "bootstarp: Starting Consul cluster..."
docker ps -a | grep consul && docker rm -f consul
docker run -d --name=consul \
  --restart=always \
  --net=host \
  ${CONSUL_DOCKER_IMAGE} agent -server \
  -node=${NODE_NAME} \
  ${CONSUL_ADVERTISE_PEER_URLS} \
  ${CONSUL_CLUSTER_NODES} \
  -bootstrap-expect=${BOOTSTRAP_EXPECT}

#entire=()
#for index in ${!entire_ips[*]}; do
#    entire+=("${entire_names[$index]}=http://${entire_ips[$index]}:2380")
#done
#ETCD_CLUSTER_NODES="$(join_by , ${entire[@]})"

#port_mappings=()
#advertise_peer_urls=()
#self_cluster_nodes=()
#for index in ${!node_all_ips[*]}; do
#    port_mappings+=("-p ${node_all_ips[$index]}:4001:4001 -p ${node_all_ips[$index]}:2380:2380 -p ${node_all_ips[$index]}:2379:2379")
#    advertise_peer_urls+=("http://${node_all_ips[$index]}:2380")
#    self_cluster_nodes+=(${NODE_NAME}=http://${node_all_ips[$index]}:2380)
#done
#DOCKER_PORT_MAPS="$(join_by ' ' ${port_mappings[@]})"
#ETCD_ADVERTISE_PEER_URLS="$(join_by , ${advertise_peer_urls[@]})"
#ETCD_SELF_CLUSTER_NODES="$(join_by , ${self_cluster_nodes[@]})"

#echo "bootstarp: Starting ETCD cluster..."
#docker ps -a | grep etcd-rancher-cluster && docker rm -f etcd-rancher-cluster
#docker run -d --name=etcd-rancher-cluster \
#    --restart=always \
#    ${DOCKER_PORT_MAPS} \
#    -p 127.0.0.1:4001:4001 -p 127.0.0.1:2380:2380 -p 127.0.0.1:2379:2379 \
#    ${ETCD_DOCKER_IMAGE} \
#    -name "${NODE_NAME}" \
#    -advertise-client-urls http://${NODE_IP_ADDRESS}:2379,http://${NODE_IP_ADDRESS}:4001 \
#    -listen-client-urls http://0.0.0.0:2379,http://0.0.0.0:4001 \
#    -initial-advertise-peer-urls ${ETCD_ADVERTISE_PEER_URLS} \
#    -listen-peer-urls http://0.0.0.0:2380 \
#    -initial-cluster-token etcd-rancher-cluster-1 \
#    -initial-cluster "${ETCD_SELF_CLUSTER_NODES},${ETCD_CLUSTER_NODES}" \
#    -initial-cluster-state new


# Check that ETCD cluster is healthy
#until $(/usr/bin/etcdctl cluster-health 2>&1 >/dev/null); do
#    echo "bootstarp: Waiting until the cluster rises."
#    sleep 1
#done

until [ "$(curl -s http://localhost:8500/v1/status/leader)" == "\"\"" ]; do
    echo "bootstarp: Waiting until the cluster rises."
    sleep 1
done

mkdir -p /etc/motd.d

if [ -z "$(consul-cli kv read ${CONSUL_PATH}/setupComplete >/dev/null 2>&1)" ]; then
    if consul-cli kv write ${CONSUL_PATH}/setupLock 1 --modifyindex="0"  >/dev/null 2>&1 ; then
        echo "bootstarp: obtained the lock to proceed with setting up."

        hostnamectl set-hostname makara

        mkdir -p /nfs
        echo "/nfs    ${NODE_NETMASK}(rw,async,no_wdelay,crossmnt,insecure,all_squash,insecure_locks,sec=sys,anonuid=0,anongid=0)" > /etc/exports
        systemctl enable nfs-server
        systemctl start nfs-server

        echo "RANCHER_ADMIN_NAME=${RANCHER_ADMIN_NAME}" > /etc/rancher_server.env
        echo "RANCHER_ADMIN_USERNAME=${RANCHER_ADMIN_USERNAME}" >>/etc/rancher_server.env
        echo "RANCHER_ADMIN_PASSWORD=${RANCHER_ADMIN_PASSWORD}" >>/etc/rancher_server.env
        echo "RANCHER_NFS_ENDPOINT=${NODE_IP_ADDRESS}" >>/etc/rancher_server.env
        echo "RANCHER_NFS_ON_REMOVE=${RANCHER_NFS_ON_REMOVE}" >>/etc/rancher_server.env
        echo "RANCHER_ENDPOINT=http://${NODE_IP_ADDRESS}:8080" >>/etc/rancher_server.env
        echo "Rancher URL: http://${NODE_IP_ADDRESS}:8080">>/etc/motd.d/rancher.conf
        /usr/lib/coreos/motdgen

        docker run -d -p 8080:8080 --restart=always --name rancher-mgmt ${RANCHER_SERVER_DOCKER_IMAGE}

        export `cat /etc/rancher_server.env`
        /opt/bin/python /opt/bin/srv_init.py

        consul-cli kv write ${CONSUL_PATH}/rancher_endpoint "${RANCHER_ENDPOINT}" >/dev/null
        consul-cli kv write ${CONSUL_PATH}/setupComplete youBetcha >/dev/null

        RANCHER_REGISTRATION_URL=$(consul-cli kv read ${CONSUL_PATH}/mgmt)
        echo 'RANCHER_LABELS=makara=1' >/etc/rancher_agent.env
        echo "CATTLE_AGENT_IP=${NODE_IP_ADDRESS}" >>/etc/rancher_agent.env
        echo "RANCHER_REGISTRATION_URL=${RANCHER_REGISTRATION_URL}" >>/etc/rancher_agent.env

        export `cat /etc/rancher_agent.env`
        docker run --rm --privileged \
            -e CATTLE_AGENT_IP=$CATTLE_AGENT_IP \
            -e CATTLE_HOST_LABELS=$RANCHER_LABELS \
            --name rancher-agent-launch \
            -v /var/run/docker.sock:/var/run/docker.sock \
            ${RANCHER_AGENT_DOCKER_IMAGE} \
            ${RANCHER_REGISTRATION_URL}

        exit 0
    fi
fi

until [ "$(consul-cli kv read ${CONSUL_PATH}/setupComplete 2>&1)" == "youBetcha" ] ; do
    echo "bootstarp: waiting for Rancher server..."
    sleep 5
done

RANCHER_REGISTRATION_URL=$(consul-cli kv read ${CONSUL_PATH}/mgmt)
RANCHER_ENDPOINT=$(consul-cli kv read ${CONSUL_PATH}/rancher_endpoint)

echo "Rancher URL: ${RANCHER_ENDPOINT}">>/etc/motd.d/rancher.conf
/usr/lib/coreos/motdgen

declare -A labels=( ["capricorn"]='capricorn=1' ["proteus"]='proteus=1' ["kraken"]='kraken=1' ["tiamat"]='tiamat=1')

for key in "${!labels[@]}"
do
    if consul-cli kv write ${CONSUL_PATH}/labels/$key ${NODE_NAME} --modifyindex="0" >/dev/null 2>&1; then
        echo "RANCHER_LABELS=${labels[$key]}" >/etc/rancher_agent.env
        echo "CATTLE_AGENT_IP=${NODE_IP_ADDRESS}" >>/etc/rancher_agent.env
        echo "RANCHER_REGISTRATION_URL=${RANCHER_REGISTRATION_URL}" >>/etc/rancher_agent.env

        hostnamectl set-hostname $key

        export `cat /etc/rancher_agent.env`
        docker run --rm --privileged \
            -e CATTLE_AGENT_IP=$CATTLE_AGENT_IP \
            -e CATTLE_HOST_LABELS=$RANCHER_LABELS \
            --name rancher-agent-launch \
            -v /var/run/docker.sock:/var/run/docker.sock \
            ${RANCHER_AGENT_DOCKER_IMAGE} \
            ${RANCHER_REGISTRATION_URL}
        exit 0
   fi
done