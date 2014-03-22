The Railgun container builder
=============================

Getting started
===============
The easiest way to get started is to have a look at the examples. This project contains
code to set up a basic virtual machine with all the prerequisites preloaded. To get started,
see the [tutorials](doc/Tutorial.md), but it will be easier to understand if you take a couple
of minutes to read through the next section first.

Concepts
========

Sites and hosts
---------------

A *site* is a set of one or more related hosts. The services in a site can refer to other
services in the same site or a parent site.

Because Railgun is essentially decentralized, the site definition does not necessarily fully describe
every aspect of the hosts, nor are all services necessarily managed by the site (although it is possible
to define a default set of services to initialize, if desired).

It is perfectly valid for different development teams to share hosts but still have different site definitions
(though sharing virtual machines managed by Railgun may have some disruptive implications).

A site definition is hierarchical: a site is aware of its parent site (if any), but
the parent site is not aware of its children.

A *host* is a physical or virtual machine that runs one or more services. It is referred to by
an *alias* that in general has nothing to do with its real host name.

Projects and services
---------------------

A *service* is a process (or group of tightly connected processes). Services are implemented
as *containers* using Docker. One service equals one container.

A *project* only exists at the source code level. A project is the definition of one or more
services. By convention, the project definition file is called `railgun.yml` if there is only
one project in a directory, but it can be called anything.

Dependencies and sockets
------------------------

If a service *depends* on another service, it requires that service to be available and
reachable. A service does not depend on a specific service implementation, but instead depends
on one or more named *endpoints* that can be provided by other services. Endpoints are 
similar to interfaces in object-oriented programming, and service dependencies are similar
to dependency injection.


User Guide
==========

The site definition file
------------------------

The main purpose of the site definition file is to tell Railgun where the available hosts
are located and how to access them.

A *site definition file* could be really simple. Consider the following example:

    site:
        description: Sample Vagrant/CoreOS site
    
        hosts:
            coreos:
                type: vagrant
                url: https://github.com/coreos/coreos-vagrant.git
                
This site definition defines a single host, managed by Vagrant (i.e. it depends on
both Vagrant and VirtualBox being installed on the host machine). Its alias is `coreos` and
its `Vagrantfile` is fetched from a GitHub repository (it is possible to have multiple 
`Vagrantfile`s in one repository by using the `subdirectory` and `vagrantfile` attributes).

Here is an even simpler site definition:

    site:
        hosts:
            local:
                type: local
                
The single host defined is the local machine. Obviously, this configuration will only work
on a machine capable of running `docker`.

The final category of site definition is the remote machine definition:

    site:
        description: Two identical hosts for load balancing/failover.
    
        hosts:
            worker1:
                type: ssh
                host: 10.1.12.10
            worker2:
                type: ssh
                host: 10.1.12.11
                
Railgun will access these hosts using SSH. It is worth noting that the value for the `host`
attribute can refer to an host entry in the `$HOME/.ssh/config` file, any SSH configuration
should be done there.

The project file
----------------

The *project file* or *service definition file* is where you define what should be run where, and how.

Here is an example of a very basic project file:

    rabbitmq:
        implements:
            amqp: tcp:5672
            rabbitmq: tcp:5672
    
        container:
            url: https://github.com/mikaelhg/docker-rabbitmq.git
            
This project defines a RabbitMQ service. Since RabbitMQ implements the `AMQP` protocol,
we specify that this service implements both RabbitMQ and AMQP. Dependent services can
then choose if they should depend on RabbitMQ in particular, or any service that 
speaks AMQP.

The `container` section defines how to set up the service's Docker container. The first
attribute is the `url` from where to fetch the `Dockerfile`. This can be a SCM repository
or a direct link to the Dockerfile.

Shell access
------------

Railgun can help providing shell access to the machines and containers in a uniform way. This
is essential when developing services and sites, debugging problems and getting familiar
with the technology.

To run a command on a host defined in a site, use

    railgun exec [-s /path/to/site.yml] [-h hostname] command [args ...]

If the current directory contains a `site.yml` that defines a single host, it is sufficient to type

    railgun exec command [args ...]

To start an interactive shell on a host, use

    railgun shell [-s /path/to/site.yml] [-h hostname]
    
It is also possible to run a command or start a shell in the context of a *service*. To do this,
add the `-c` or `--service=` option, e.g.

    railgun shell [-s /path/to/site.yml] [-h hostname] -c myservice
    
The shell used for the service defaults to `/bin/bash` but can be changed using the `shell` attribute
of the service's `container` attribute.

Docker sockets and remote management
------------------------------------

Railgun can provide a unified interface to the various Docker daemons running on the hosts. To enable this,
either use TCP sockets (default is to use a unix domain socket), or make sure that the users you use
for SSH and local access are all members of the `docker` group.

Builders
--------

A *builder* is a special kind of container that understands how to transform the input source set into
a Docker container.