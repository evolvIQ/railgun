from __future__ import print_function
from ..site import *
from ..checkout import _call
import boto
        
class EC2HostProvider(HostProvider):
    "Manages hosts on AWS EC2 using the boto module"
    conn = None
    filters = None
    
    def __init__(self, name, cluster, root, qualifier, parent):
        super(EC2HostProvider, self).__init__(name, cluster, root, qualifier, parent)
        self.root = root
        if cluster:
            self.conn = boto.connect_ec2()
            self.filters = root.get("matching")
            if not self.filters:
                self.filters = {'tag:Name':self.name}
        else:
            raise ValueError("EC2 provider should specify clusters, not hosts!")
        self.site = parent
        
    def _get_instances(self):
        return self.conn.get_only_instances(filters=self.filters) 
        
    def get_instances(self):
        for inst in self._get_instances():
            yield (inst.id, inst.ip_address)
        
    def update_host(self, dryrun, scm_update, reboot):
        code = self.exec_shell("docker 2> /dev/null")
        if code == 255:
            log.info("Host '%s' does not seem to be reachable." % self.name)
        elif code == 127:
            log.info("Host '%s' does not seem to have Docker installed." % self.name)
        elif code != 0:
            log.warn("Host '%s': Docker command gave exit code %d." % (self.name, code))
            
    def popen(self, args, bufsize=0, stdin=None, stdout=None, stderr=None, cwd=None, env=None, tty=False, compress=False):
        """Performs the equivalent of subprocess.Popen but executes the command on the remote
        host. TTY options, input/output redirection and other options tries as much as possible
        to emulate Popen. Not all of Popen's options are supported.
        
        The additional tty option tells the SSH client to allocate a pseudo-terminal to work
        with terminal applications.
        The additional compress option requests SSH session data compression.
        """ 
        if isinstance(args, str) or isinstance(args, unicode):
            l = [ args ]
        else:
            quote = lambda s:"'" + s.replace("'", "'\\''") + "'"
            l = map(quote, list(args))
        cmd = ["ssh", self.hostname]
        if tty: cmd.append("-t")
        if compress: cmd.append("-C")
        cmd.append(' '.join(l))
        return subprocess.Popen(cmd, bufsize=bufsize, stdin=stdin, stdout=stdout, stderr=stderr)
            
    def start_shell(self):
        "Starts an interactive shell on this host"
        cmd = ["ssh", self.hostname]
        _call(cmd)
        
HostProvider = EC2HostProvider