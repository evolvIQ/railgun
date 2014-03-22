"""
Manages a site.
"""
from __future__ import print_function
import yaml
import sys, os, subprocess, tempfile, logging
import docker
from . import checkout
_call = checkout._call
log = logging.getLogger(__name__)

class SiteSpec(object):
    root = None
    filename = None
    def __init__(self, source):
        if not source: source = "."
        if os.path.isdir(source):
            source = os.path.join("site.yml")
            if not os.path.exists(source):
                raise ValueError("Directory does not contain a 'site.yml'")
        elif not os.path.exists(source):
            if not source.endswith(".yml"):
                source = "%s.yml" % source
            if not os.path.exists(source):
                raise ValueError("File '%s' does not exist" % source)
        self.filename = source
        
        d = yaml.load(file(source))
        
        if not isinstance(d, dict) or len(d) != 1 or not "site" in d:
            self._fail("Expected 'site' root element")
        self.root = d["site"]
        
    def get_providers(self, hosts=None):
        hs = self.hosts()
        cs = self.clusters()
        if not hosts is None:
            for h in hosts:
                if not h in hs and not h in cs:
                    self._fail("Host '%s' not defined" % h)
        providers = []
        for alias in hs:
            if hosts is None or alias in hosts:
                providers.append(self.provider(alias))
        for alias in cs:
            if hosts is None or alias in hosts:
                providers.append(self.provider(alias))
        return providers
    
        
    def update(self, hosts=None, dryrun=False, scm_update=False, reboot=False):
        log.debug("%s site update of %s" % (["Performing","Simulating"][dryrun], self.filename))
        for provider in self.get_providers(hosts):
            provider.update_host(dryrun=dryrun, scm_update=scm_update, reboot=reboot)
        
    def hosts(self):
        "The hosts defined in this site specification"
        h = self.root.get("hosts")
        if h:
            if not isinstance(h, dict):
                self._fail("Invalid 'hosts' specification")
            return h
        else:
            return {}
            
    def clusters(self):
        "The clusters defined in this site specification"
        h = self.root.get("clusters")
        if h:
            if not isinstance(h, dict):
                self._fail("Invalid 'clusters' specification")
            return h
        else:
            return {}
            
    def provider(self, alias):
        "Instantiate a host provider for the specified host"
        cluster = False
        if not alias:
            hl = self.hosts()
            cl = self.clusters()
            if len(hl) + len(cl) == 1:
                if len(cl) == 1:
                    alias = list(cl)[0]
                    h = cl[alias]
                    cluster = True
                else:
                    alias = list(hl)[0]
                    h = hl[alias]
            elif len(hl) == 0:
                raise ValueError("Site has no hosts or clusters defined")
            else:
                raise ValueError("Host is ambiguous, must specify host/cluster alias")
        else:
            h = self.hosts().get(alias)
            if not h:
                h = self.clusters().get(alias)
                cluster = True
        if h is None:
            raise ValueError("Host alias '%s' not recognized" % alias)
        typ = h.get("type", "ssh")
        mod = None
        
        def load_provider(n):
            mod = __import__('.'.join(n))
            for a in n[1:]: mod = getattr(mod, a)
            return mod
            
        if not '.' in typ:
            try:
                n = __name__.split('.')[:-1] + ["host_providers", typ]
                mod = load_provider(n)
            except ImportError:
                raise
        if not mod:
            mod = load_provider(typ.split('.'))
        p = mod.HostProvider(alias, cluster, h, "", self)
        return p
            
    def _fail(self, message):
        if self.filename:
            message = "%s: %s" % (self.filename, message)
        raise ValueError(message)
        
class HostProvider(object):
    root = None
    site = None
    name = None
    tempdir = None
    cluster = None
    def __init__(self, name, cluster, root, qualifier, parent):
        self.name = name
        self.root = root
        self.site = parent
        self.tempdir = "$(mktemp -d /tmp/tarXXXXXX.$$)"
        self.cluster = cluster
        
    def get_service_instances(self, servicename=None):
        "Get service instances (of the given service if specified). Returns a dictionary of {instancename:dict}"
        srv = self.root.get("services", {})
        d = dict()
        if isinstance(srv, dict):
            for k,v in srv.items():
                if isinstance(v, str) or isinstance(v, unicode):
                    s = {'name':v}
                elif isinstance(v, dict):
                    s = v
                else:
                    self._fail("Invalid service element : %r" % v)
                if servicename is None or servicename == s["name"]:
                    d[k] = s
                
        elif isinstance(srv, list):
            for s in srv:
                if isinstance(s, str) or isinstance(s, unicode):
                    k = s
                    v = {'name':s}
                elif isinstance(s,dict):
                    k = s['name']
                    v = s
                else:
                    self._fail("Invalid service element : %r" % s)
                if k in d: self._fail("Service '%s' specified more than once. Instance name required" % s)
                if servicename is None or servicename == v["name"]:
                    d[k] = v
        else:
            self._fail("Invalid 'services' element")
        return d
        
    def should_download_remote_files(self):
        "Return True if the host can download remote files, set to False if host has limited Internet access, for example"
        return True
            
    def exec_shell(self, cmd, args=None, tty=None, stdin=None):
        "Executes a shell command on this host"
        if args is not None:
            cmd = [cmd] + list(args)
        stdin_flag = None
        if stdin:
            stdin_flag = subprocess.PIPE
        proc = self.popen(cmd, tty=tty, stdin=stdin_flag)
        if stdin:
            checkout._write_to_process(proc, stdin)
        return proc.wait()
        
    def popen(*args, **kwargs):
        """Performs the equivalent of subprocess.Popen but executes the command on the remote
        host. TTY options, input/output redirection and other options tries as much as possible
        to emulate Popen. Not all of Popen's options are supported.""" 
        raise NotImplementedError("popen")
        
    def check_container_exists(self, name):
        cmd = "docker history %s > /dev/null 2>/dev/null" % name
        if self.exec_shell(cmd) == 0:
            log.debug("Site container '%s' exists on %s" % (name, self.name))
            return True
        else:
            log.debug("Site container '%s' missing on %s" % (name, self.name))
            return False
        
    def _build_service_container(self, builder, name, no_cache=False):
        "Invokes a builder and returns a process object whose stdin should receive a tar stream of the project to build"      
        if not builder:
            raise ValueError("Empty builder attribute in service '%s'" % name)
        cmd = []
        if builder == 'builder.none':
            # No builder container - use raw (used for bootstrapping and plain Dockerfiles)
            # In this case, just untar to a temp directory and run 'docker build'
            opts = ["-rm=true"]
            if no_cache:
                opts.append("--no-cache")
            cmd += [ "TDIR=%s" % self.tempdir,
                    "tar -xmC $TDIR",
                    "docker build %s -t '%s' $TDIR" % (' '.join(opts), name),
                    "EXITCODE=$?",
                    "rm -rf $TDIR",
                    "exit $EXITCODE"
                  ]
        else:
            cmd.append("docker run -i -rm=true -v /var/run/:/host/var/run -e DOCKER_SOCK=unix:///host/var/run/docker.sock '%s' build" % builder)
        
        log.debug('Executing:\n  ' + '\n  '.join(cmd))
        return self.popen(' ; '.join(cmd), stdin=subprocess.PIPE)
        
    def get_node_ip(self):
        return "-"
        
    def get_instances(self):
        yield (self.name, self.get_node_ip())
        
    def _fail(self, message):
        return self.site._fail(message)
        
    def __repr__(self):
        return "%s (%s)" % (self.name, type(self).__name__)
