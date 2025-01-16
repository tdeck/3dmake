#! /bin/bash

pyinstaller -y 3dm.spec
cd dist
tar -czvf 3dmake_linux.tar.gz 3dmake
