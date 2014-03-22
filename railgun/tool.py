from __future__ import print_function
import sys, os
import cmdln
from . import spec, site
import logging
log = logging.getLogger(__name__)

def global_options(func):
    from functools import wraps
    @wraps(func)
    def verbosity_func(self, subcmd, opts, *a, **kw):
        if opts.verbose:
            print("Debug logging")
            logging.basicConfig(stream=sys.stderr,level=logging.DEBUG)
        else:
            logging.basicConfig(stream=sys.stderr,level=logging.INFO)
        return func(self, subcmd, opts, *a, **kw)
    
    return cmdln.option("-v","--verbose", action="count", help="Increase verbosity")(verbosity_func)
    
_dopt_site = cmdln.option("-s","--site", help="Use the specified site. If not set, expects a 'site.yml' in the current directory.")
_dopt_host = cmdln.option("-H","--host", help="Consider only the specified host.")
_dopt_dry = cmdln.option("-n","--dry-run", action="store_true", help="Does not perform any changes, but prints the actions.")

class Tool(cmdln.Cmdln):
    """Usage:
        ${name} SUBCOMMAND [ARGS...]
        ${name} help SUBCOMMAND

    ${command_list}
    ${help_list}
    """
    name = sys.argv[0]

    def __init__(self, *args, **kwargs):
        cmdln.Cmdln.__init__(self, *args, **kwargs)
        cmdln.Cmdln.do_help.aliases.append("h")
        
    @_dopt_host
    @_dopt_site
    @_dopt_dry
    @cmdln.option("-u","--scm-update", action="store_true", help="Updates SCM repositories to the latest version")
    @cmdln.option("--reboot", action="store_true", help="Allows actions that requires the reboot of a host")
    @cmdln.option("-U", "--force-rebuild", action="store_true", help="Forces rebuild of build containers")
    @global_options
    def do_site(self, subcmd, opts):
        """${cmd_name}: Create or update a site based on the specified site configuration.
        
        This involves creating virtual machines, if needed. Physical and remote hosts are
        never managed, but containers on them are.
        
        Usage: ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            hosts = None
            if opts.host: hosts = [opts.host]
            sitespec = site.SiteSpec(opts.site)
            sitespec.update(hosts=hosts, dryrun=bool(opts.dry_run), scm_update=bool(opts.scm_update), reboot=opts.reboot)
            return 0
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    @_dopt_host
    @_dopt_site
    @_dopt_dry
    @cmdln.option("-c","--service", help="Push only the specified service.")
    @cmdln.option("-r","--recursive", help="Push service dependencies recursively.")
    @cmdln.option("-U", "--update", action="store_true", help="Forces update of build containers (and dependencies if -r specified)")
    @cmdln.option("--no-cache", action="store_true", help="Disabled Docker caching")
    @global_options
    def do_push(self, subcmd, opts, source=None):
        """${cmd_name}: Push a service to a destination site.
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            project = spec.Project(source)
            host = site.SiteSpec(opts.site).provider(opts.host)
            if opts.service:
                project.get_service(opts.service).push_to(host, force_update=opts.update, no_cache=opts.no_cache)
            else:
                project.push_to(host, force_update=opts.update, no_cache=opts.no_cache)
            return 0
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    @_dopt_host
    @_dopt_site
    @cmdln.option("-c","--service", help="Run in the container of the specified service. If not set, runs directoy on the host.")
    @cmdln.option("-t","--tty", action="store_true", help="Allocate a tty, allows running interactive programs")
    @global_options
    def do_exec(self, subcmd, opts, command, *args):
        """${cmd_name}: Execute a shell command on a given host defined in a given site.
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            source = opts.site
            return site.SiteSpec(opts.site).provider(opts.host).exec_shell(command,args,tty=bool(opts.tty))
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    @_dopt_host
    @_dopt_site
    @cmdln.option("-c","--service", help="Run in the container of the specified service. If not set, runs directoy on the host.")
    @global_options
    def do_shell(self, subcmd, opts):
        """${cmd_name}: Start a shell on a given host defined in a given site.
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            source = opts.site
            return site.SiteSpec(opts.site).provider(opts.host).start_shell()
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    @_dopt_host
    @_dopt_site
    @cmdln.option("-c","--service", help="Print status about the specified service.")
    @global_options
    def do_status(self, subcmd, opts):
        """${cmd_name}: Prints status information about the specified site, host or service.
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            source = opts.site
            s = site.SiteSpec(opts.site)
            for h in s.get_providers(opts.host and [opts.host]):
                print("%r:" % h)
                for inst in h.get_instances():
                    print("  %-20s %s" % inst)
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
                
        
    @_dopt_site
    @cmdln.option("-p","--project", help="Specify project.")
    @cmdln.option("-c","--service", help="Print status about the specified service.")
    @cmdln.option("-n","--names-only", action="store_true", help="Print only the names.")
    @global_options
    def do_info(self, subcmd, opts):
        """${cmd_name}: Display information about a project (-p) or site (-s)
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            if opts.project:
                project = spec.Project(opts.project)
                if opts.service:
                    if opts.names_only:
                        print(project.get_service(opts.service).qualified_name())
                    else:
                        print(project.get_service(opts.service))
                else:
                    if opts.names_only:
                        for serv in project.services:
                            print(serv.qualified_name())
                    else:
                        print(project)
            else:
                print("Expected one of -p or -s", file=sys.stderr)
                self.do_help(("help","info"))
            return 0
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    @cmdln.option("--no-cache", action="store_true", help="Disabled Docker caching")
    @cmdln.option("-c","--service", help="Print status about the specified service.")
    @global_options
    def do_build(self, subcmd, opts, source=None):
        """${cmd_name}: Builds
        
        ${cmd_usage}
        
        ${cmd_option_list}
        """
        try:
            if not source: source = '.'
            project = spec.Project(source)
            if opts.service:
                project.get_service(opts.service).build()
            else:
                for service in project.services:
                    service.build()
            print(project)
        except:
            print(sys.exc_info()[1], file=sys.stderr)
            return 255
        
    if os.path.exists("/.dockerenv"):
        @cmdln.option("--no-cache", action="store_true", help="Disabled Docker caching")
        @cmdln.option("-c","--service", help="Print status about the specified service.")
        @global_options
        def do_buildcontainer(self, subcmd, opts, source=None):
            try:
                from . import build
                if not source: source = '.'
                project = spec.Project(source)
                if opts.service:
                    svc = project.get_service(opts.service)
                    build.build_container(svc.build(write=True))
                else:
                    if len(project.services) != 1:
                        raise Exception("Must specify service")
                    project.services[0].build(write=True)
                    build.build_container(project.services[0])
                print(project)
            except:
                print(sys.exc_info()[1], file=sys.stderr)
                return 255
            

        
if __name__ == '__main__':
    cmd = Tool()
    sys.exit(cmd.main())
