from ..site import *

class VagrantHostProvider(HostProvider):
    "Manages a site's host as a Vagrant-managed VM"
    dirname = None
    ssh_config = None
    def __init__(self, name, cluster, root, qualifier, parent):
        super(VagrantHostProvider, self).__init__(name, cluster, root, qualifier, parent)
        self.dirname = os.path.abspath(os.path.dirname(parent.filename))
        if not "url" in root:
            self._fail("Missing 'url' for Vagrant host '%s'" % name)
        self.subdir = self.root.get("subdirectory")
        if not self.subdir: self.subdir = None
        self.vagrantdir = self.dirname
        scm = checkout.get_scm_provider(self.root["url"])
        if scm:
            dest = scm.get_destination_name(self.root["url"])
            if dest: self.vagrantdir = os.path.join(self.vagrantdir, dest)
        if self.subdir: self.vagrantdir = os.path.join(self.vagrantdir, self.subdir)
        
    def update_host(self, dryrun, scm_update, reboot):
        "Updates or creates this virtual machine"
        scm = checkout.get_scm_provider(self.root["url"])
        if scm:
            def update_hook(repo, post, change):
                if post and change:
                    if reboot:
                        _call(["vagrant","reload"],cwd=repo,dryrun=dryrun)
                    else:
                        print("Not rebooting '%s'." % name)
                    _call(["vagrant","up"],cwd=repo,dryrun=dryrun)
            def clone_hook(repo, post):
                if post:
                    _call(["vagrant","up"],cwd=repo,dryrun=dryrun)
            scm.update_callback = update_hook
            scm.clone_callback = clone_hook
            dest = scm.checkout(self.root["url"], self.dirname, self.subdir, dryrun=dryrun, update_existing=scm_update)
            scm.update_callback = None
            scm.clone_callback = None
            vagrantfile = self.root.get("vagrantfile", "Vagrantfile")
            vagrantfile = os.path.join(dest, vagrantfile)
            if not dryrun and not os.path.isfile(vagrantfile):
                raise IOError("Did not find '%s'" % vagrantfile)
                
            code = self.exec_shell("docker 2> /dev/null")
            if code == 255:
                if self.exec_shell("exit 0") == 255:
                    log.info("Host '%s' does not seem to be up.%s" % (self.name, [" Starting it.", ""][dryrun]))
                    _call(["vagrant","up"],cwd=dest,dryrun=dryrun)
                else:
                    log.warn("Host '%s': Docker command gave exit code %d." % (self.name, code))
            elif code == 127:
                log.info("Host '%s' does not seem to have Docker installed." % self.name)
            elif code != 0:
                log.warn("Host '%s': Docker command gave exit code %d." % (self.name, code))
            
            
            #_call(
        else:
            print("Download")
            
    def start_shell(self):
        "Starts an interactive shell on this host"
        cmd = ["vagrant","ssh"]        
        _call(cmd, cwd=self.vagrantdir)
        
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
        ssh = self._get_vagrant_ssh_command(l, tty, compress=compress)
        return subprocess.Popen(ssh, bufsize=bufsize, cwd=self.vagrantdir, stdin=stdin, stdout=stdout, stderr=stderr)
        
    def _get_vagrant_ssh_command(self, args, tty, compress=False):
        # Vagrant-ssh messes up signal handling, so we use regular SSH with vagrant config

        # Read and parse Vagrant machine's SSH configuration
        if not self.ssh_config:
            config,_ = subprocess.Popen(["vagrant","ssh-config"], cwd=self.vagrantdir, stdout=subprocess.PIPE).communicate()
            parse = lambda x:x.strip().split(None, 2)
            self.ssh_config = map(lambda t: "-o%s=%s" % (t[0], t[1]),(x for x in map(parse,config.split("\n")[1:]) if x))
        # Run SSH with no configuration file to avoid conflicts with ~/.ssh/config
        cmd = ["ssh", "default", "-F/dev/null"] + self.ssh_config
        if tty: cmd.append("-t")
        else: cmd.append("-T")
        if compress: cmd.append("-C")
        return cmd + args
        
        
    def get_node_ip(self):
        return "127.0.0.1"
HostProvider = VagrantHostProvider