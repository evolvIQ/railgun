from ..site import *
from ..checkout import _call
        
class RemoteHostProvider(HostProvider):
    "Manages a site's host over SSH"
    hostname = None
    def __init__(self, name, cluster, root, qualifier, parent):
        super(RemoteHostProvider, self).__init__(name, cluster, root, qualifier, parent)
        self.root = root
        self.hostname = self.root.get("host")
        if not self.hostname:
            raise ValueError("Host name must be specified")
        if cluster:
            raise ValueError("SSH host provider does not support clusters")
        self.site = parent
        
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
        
HostProvider = RemoteHostProvider