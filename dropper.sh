#!/bin/bash
curl https://raw.githubusercontent.com/makakin/do_siemonster/master/opt/bin/bootstrap.sh > /opt/bin/bootstrap.sh
curl https://raw.githubusercontent.com/makakin/do_siemonster/master/opt/bin/srv_init.py > /opt/bin/srv_init.py
chmod 755 /opt/bin/bootstrap.sh
chmod 755 /opt/bin/srv_init.py
