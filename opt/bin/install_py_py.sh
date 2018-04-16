#!/bin/bash
set -e

PYPY_VER=5.7.1

mkdir -p /opt/bin

cd /opt
curl -sSL https://bitbucket.org/pypy/pypy/downloads/pypy2-v${PYPY_VER}-linux64.tar.bz2 -O
tar -xjf pypy2-v${PYPY_VER}-linux64.tar.bz2
ln -fs /lib64/libncurses.so.5.9 /opt/pypy2-v${PYPY_VER}-linux64/bin/libtinfo.so.5
mv pypy2-v${PYPY_VER}-linux64 pypy
curl -sSL https://bootstrap.pypa.io/get-pip.py -O
LD_LIBRARY_PATH=/opt/pypy/bin /opt/pypy/bin/pypy get-pip.py
rm get-pip.py


cat > /opt/bin/python <<EOF
#!/bin/bash
LD_LIBRARY_PATH=/opt/pypy/bin /opt/pypy/bin/pypy \$@
EOF

cat > /opt/bin/pip <<EOF
#!/bin/bash
LD_LIBRARY_PATH=/opt/pypy/bin /opt/pypy/bin/pip \$@
EOF

cat > /opt/bin/pip2 <<EOF
#!/bin/bash
LD_LIBRARY_PATH=/opt/pypy/bin /opt/pypy/bin/pip2 \$@
EOF

chown root:root \
    /opt/bin/python \
    /opt/bin/pip \
    /opt/bin/pip2

chmod 755 \
    /opt/bin/python \
    /opt/bin/pip \
    /opt/bin/pip2

/opt/pypy/bin/pip install requests python-etcd python-consul
