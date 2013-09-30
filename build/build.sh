#!/bin/sh

# v1.0 - 2013.9.22
# project inited.

if [ -d 'fakeroot' ]; then
	rm -rvf fakeroot
fi

PYLIB='fakeroot/usr/lib/python3/dist-packages/'
APP='kwplayer'

mkdir -vp fakeroot/usr/bin fakeroot/DEBIAN $PYLIB

cp -v ../kuwo.py fakeroot/usr/bin/kwplayer
cp -rvf ../kuwo $PYLIB/
rm -rvf $PYLIB/kuwo/__pycache__
cp -rvf ../mutagenx $PYLIB/
rm -rvf $PYLIB/mutagenx/__pycache__
cp -rvf ../share fakeroot/usr/share
cp -vf control fakeroot/DEBIAN/
