#!/bin/bash
set -e

echo "Spinning up xdist containers with pytest_container_manager.py"
python scripts/xdist/pytest_container_manager.py -a up -n ${XDIST_NUM_TASKS} \
-t ${XDIST_CONTAINER_TASK_NAME} \
-s ${XDIST_CONTAINER_SUBNET} \
-sg ${XDIST_CONTAINER_SECURITY_GROUP}

ip_list=$(<pytest_task_ips.txt)

for ip in $ip_list
do
    container_reqs_cmd="ssh ubuntu@$ip 'cd /edx/app/edxapp/edx-platform;
    git pull -q; git checkout -q ${XDIST_GIT_BRANCH};
    source /edx/app/edxapp/edxapp_env; pip install -qr requirements/edx/testing.txt' & "

    cmd=$cmd$container_reqs_cmd
done
cmd=$cmd"wait"
echo -e "Host * \n StrictHostKeyChecking no" >> ~/.ssh/config
echo "Executing commmand: $cmd"
eval $cmd
