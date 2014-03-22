FROM ubuntu:13.10
RUN apt-get update
RUN apt-get install -y python curl python-setuptools python-dev build-essential rsync git subversion
RUN easy_install pip
RUN easy_install mercurial
RUN pip install pyyaml cmdln>=1.0 git+http://github.com/evolvIQ/python-pipe-rpc.git git+http://github.com/dotcloud/docker-py.git
VOLUME /buildroot
ADD build /bin/
ADD railgun /railgun/railgun
ADD railgun_files /railgun/meta 
