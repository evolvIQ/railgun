""" Builder module. Can only be run from inside a Docker container.


"""
from __future__ import print_function

import os, sys
import piperpc
import docker
import tarfile, gzip, tempfile
from . import spec, checkout

if not os.path.exists("/.dockerenv"):
    raise ImportError("The build module can only be imported in a Docker container")

def build_container(service, nocache=False):
    rootdir = service.get_directory()
    name = service.container_name()
    client = docker.Client(os.environ["DOCKER_SOCK"])
    print(os.environ["DOCKER_SOCK"])
    for result in client.build(path=rootdir, tag=name, rm=True, nocache=nocache, stream=True):
        print(result)
