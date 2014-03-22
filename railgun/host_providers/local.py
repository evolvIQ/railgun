from ..site import *

class LocalHostProvider(HostProvider):
    "Manages the local machine as a site's host"
    def __init__(self, name, cluster, root, qualifier, parent):
        super(LocalHostProvider, self).__init__(name, cluster, root, qualifier, parent)
        if cluster:
            raise ValueError("Local host provider does not support clusters")
        
    def update_host(self, dryrun, scm_update, reboot):
        code = self.exec_shell("docker 2> /dev/null")
        if code == 127:
            log.warn("Host '%s' does not seem to have Docker installed." % self.name)
        elif code != 0:
            log.warn("Host '%s': Docker command gave exit code %d." % (self.name, code))
        
            
    def popen(self, args, bufsize=0, stdin=None, stdout=None, stderr=None, cwd=None, env=None, tty=False, compress=False):
        """Performs the equivalent of subprocess.Popen but executes the command on the remote
        host. TTY options, input/output redirection and other options tries as much as possible
        to emulate Popen. Not all of Popen's options are supported.
        
        The additional tty and compress options are ignored.
        """ 
        return subprocess.Popen(args, bufsize=bufsize, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr)
            
    def exec_shell(self, cmd, args=[], tty=None, stdin=None):
        "Executes a shell command on this host"
        cmd = [cmd] + args
        return _call(cmd, stdin=stdin)
            
    def start_shell(self):
        "Starts an interactive shell on this host"
        shell = self.root.get("shell")
        if not shell: shell = "bash"
        
        _call(shell)
        
HostProvider = LocalHostProvider