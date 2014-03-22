from __future__ import print_function
import yaml
import sys, os, time
import shlex, shutil
import tarfile, gzip, StringIO
from . import checkout
from xmlrpclib import Binary
import logging
log = logging.getLogger(__name__)

VALID_TYPES = {"abstract", "shared", "builder", "default"}

# Allow specfiles to know where the metadata is located
if not "RAILGUN_PACKAGE" in os.environ:
    os.environ["RAILGUN_PACKAGE"] = os.path.dirname(__file__)
if not "RAILGUN_FILES" in os.environ:
    f = os.path.join(os.path.dirname(__file__), "..", "meta")
    if os.path.isdir(f):
        os.environ["RAILGUN_FILES"] = os.path.abspath(f)
    else:
        f = os.path.join(sys.prefix, "railgun")
        if os.path.isdir(f):
            os.environ["RAILGUN_FILES"] = os.path.abspath(f)
    
def get_builders_dir():
    return os.path.join(os.path.dirname(__file__), '..', 'meta', 'builders')
    
def get_services_dir():
    return os.path.join(os.path.dirname(__file__), '..', 'meta', 'services')


class Project(object):
    "Represents a specfile (can hold multiple services)"
    services = None
    filename = None
    raw_docker = False
    name = None
    def __init__(self, source=None):
        self.services = []
        if not source: source = "."
        if os.path.isdir(source):
            self.name = os.path.basename(source)
            if os.path.exists(os.path.join(source, "services.yml")):
                source = os.path.join(source, "services.yml")
            elif os.path.exists(os.path.join(source, "Dockerfile")):
                self.raw_docker = True
            else:
                raise ValueError("Directory is not a Railgun project (nor contains a Dockerfile)")
        elif not os.path.exists(source):
            if not source.endswith(".yml"):
                source = "%s.yml" % source
                
            if not os.path.exists(source):
                raise ValueError("File '%s' does not exist" % source)
            self.name = os.path.splitext(os.path.basename(source))[0]
        else:
            self.name = os.path.splitext(os.path.basename(source))[0]
        
        if self.raw_docker:
            # A Dockerfile-based spec
            self.filename = os.path.join(source, "Dockerfile")
            name = os.path.basename(source)
            self.services.append(Service(name, {'builder':None}, self))
        else:
            # A services.yml-based spec
            self.filename = source
            self.root = yaml.load(file(source))
            if not isinstance(self.root, dict):
                self._fail("Invalid specfile, expected objects at root level")
            
            for n,inst in self.root.items():
                self.services.append(Service(n, inst, self))
            
        self.validate()
        
    def push_to(self, host, push_dependencies=False, force_update=False, no_cache=False):
        for service in self.services:
            service.push_to(host, force_update=force_update, no_cache=no_cache)
        
    def get_service(self, svc):
        for service in self.services:
            if service.name == svc:
                return service
        raise KeyError("Service '%s' not defined" % svc)
        
    def __repr__(self):
        return yaml.dump(self.as_dict())
        
    def as_dict(self):
        d = {}
        for service in self.services:
            d[service.name] = service.as_dict()
        return d
        
    def validate(self):
        names = set()
        for service in self.services:
            nm = service.qualified_name()
            if nm in names:
                self._fail("Duplicate service name '%s'" % nm)
            names.add(nm)
            service.validate()
            
    def _fail(self, message):
        if self.filename:
            message = "%s: %s" % (self.filename, message)
        raise ValueError(message)
        
class Service(object):
    "Represents a service"
    __root = None
    project = None
    name = None
    resolved = False
    def __init__(self, name, root, parent):
        self.__root = root
        self.name = name
        self.project = parent
        
    def validate(self):
        self.type()
    
    def qualified_name(self, short_name=False):
        q = self.__root.get("namespace")
        nm = self.name
        if self.type() == "builder" and not nm.startswith("builder."):
            nm = "builder.%s" % nm
        if q and not short_name:
            return "%s.%s" % (nm, q)
        return nm
        
    def container_name(self):
        return self.qualified_name()
        
    def get_builder(self):
        "Returns the logical name of the builder to use"
        builder = self.__root.get("builder", "base")
        if checkout.is_url_or_file(builder):
            return builder
        if not builder.startswith("builder."):
            builder = "builder.%s" % builder
        return builder
        
    def update_dependencies(self, host, dependencies=False, force_update=False):
        if dependencies:
            # TODO
            pass
            
    def update_prerequisite(self, reference, host, dependencies=False, force_update=True, no_cache=False, stack=None):
        if reference in ("builder.none",):
            return reference
        if stack is None:
            stack = [(os.path.realpath(self.project.filename),self.name)]
        log.info("Updating prerequisite '%s'" % reference)
        service = None
        if checkout.is_url_or_file(reference):
            dest = self.checkout(reference)
            log.info("Checked out dependency URL %s to %s" % (reference, dest))
            svc = None
            # Explicit reference name
            if '#' in reference:
                svc = reference.split('#')[-1]
            proj = Project(dest)
            if svc:
                service = proj.get_service(svc)
            else:
                if len(proj.services) != 1:
                    raise ValueError("Ambiguous service reference in '%s'" % reference)
                service = proj.services[0]
            ent = (os.path.realpath(proj.filename), service.name)
            if ent in stack:
                raise Exception("Cyclic dependency towards '%s'" % ent)
            stack.append(ent)
            service.push_to(host, None, dependencies, force_update=force_update, no_cache=no_cache, stack=stack)
            reference = service.qualified_name()
        else:
            log.debug("Checking service by logical name '%s'" % reference)
        
        if force_update or not host.check_container_exists(reference):
            log.info("Updating dependency/builder container '%s'" % reference)
            if not service:
                # Try to locate service source
                # First in project
                for svc in self.project.services:
                    if svc.qualified_name() == reference or svc.qualified_name(False) == reference:
                        service = svc
                        break
                # Then in builtins
                if reference.startswith("builder."):
                    pfxdir = get_builders_dir()
                else:
                    pfxdir = get_services_dir()
                for f in os.listdir(pfxdir):
                    if service: break
                    try:
                        proj = Project(os.path.join(pfxdir, f))
                    except:
                        continue
                    for svc in self.project.services:
                        if svc.qualified_name() == reference or svc.qualified_name(False) == reference:
                            service = svc
                            break
                if not service:
                    raise Exception("Reference to service '%s' could not be resolved." % reference)
                    
            
        return reference
            
    def push_to(self, host, name=None, push_dependencies=False, force_update=False, no_cache=False, stack=None):
        if name is None:
            services = host.get_service_instances(self.name)
            if not services:
                services = [self.name]
        else:
            services = [name]
        
        builder = self.update_prerequisite(self.get_builder(), host, True, force_update, no_cache=no_cache)
            
        log.debug("Will build %s using builder '%s'" % (', '.join(services), builder))
        proc = host._build_service_container(builder, self.container_name(), no_cache=no_cache)
        
        # Should we download remote files, or should we let the target do it?
        remote = host.should_download_remote_files()
        if builder == 'builder.none':
            # Bootstrap builder cannot download files
            remote = False
        
        # Wrap the pipe, since tarfile insists on calling 'tell'
        class TarPipeWrapper(object):
            fo = None
            def __init__(self, fo):
                self.fo = fo
            def tell(self):
                return 0
            def write(self, *a, **kw):
                self.fo.write(*a, **kw)
            
        # Package to process input
        self.package(TarPipeWrapper(proc.stdin), remote=remote)
        
        last=""
        proc.stdin.close()
        proc.wait()
        if proc.returncode:
            raise Exception("Container build failed. See error messages above")
        
        for service in services:
            d = os.path.dirname(self.project.filename)
            #host.publish_files(d, post_cmd=["pwd", "ls -lh"])
            #host.exec_shell("docker build")
            
    def get_build_dir(self, create=True):
        "Return the directory used for temporary build files, optionally creating it"
        dirname = os.path.join(os.path.dirname(self.project.filename), 
            "build", self.project.name, self.name)
        if create and not os.path.isdir(dirname):
            os.makedirs(dirname)
        return dirname
        
    def is_pure_container(self):
        "Returns True if the project can be transformed to a pure Dockerfile"
        container = self.__root.get("container")
        if container and container.get("url"):
            # Needs to be transformed on host
            if self.get_additional_dockerfile_instructions():
                return False
        return True
        
    def get_projectfile(self):
        if self.project.raw_docker:
            raise Exception("Raw Dockerfile projects do not have project files")
        return self.project.filename
        
    def get_dockerfile(self, local=True, remote=True, path=None):
        "Return the contents of the Dockerfile as a list of rows, or None if Dockerfile cannot be generated"
        rootdir = os.path.dirname(self.project.filename)
        if not path:
            container = self.__root.get("container")
            if container:
                path = container.get("dockerfile")
        if path:
            if os.path.isdir(path):
                path = os.path.join(path, "Dockerfile")
            for line in file(os.path.join(rootdir, path)):
                line = line.strip().split('#',1)[0]
                if not line: continue
                yield line
        for line in self.get_additional_dockerfile_instructions():
            if line: yield line
        
    def get_dockerfile_referenced_files(self, dockerfile):
        "Gets the local files referenced by the generated Dockerfile"
        rootdir = os.path.dirname(self.project.filename)
        for line in dockerfile:
            args = shlex.split(line)
            if args[0].lower() == 'add':
                fn = args[1]
                if '://' in fn: continue
                fna = os.path.join(rootdir, fn)
                fn = os.path.relpath(fna,rootdir)
                if not fna.startswith('../') and os.path.exists(fna):
                    yield fna
            
    def get_additional_dockerfile_instructions(self):
        if self.project.raw_docker:
            return
        if False:
            yield ''
        return
            
    def checkout(self, url, update_existing=False):
        "Checks out an URL into the build directory for further processing"
        rootdir = os.path.dirname(self.project.filename)
        pth = checkout.get_local_file(url, rootdir)
        if pth:
            return pth
        else:
            scm = checkout.get_scm_provider(url)
            if scm:
                dest = scm.get_destination_name(url)
                scm.checkout(url, self.get_build_dir(), update_existing=update_existing)
                return os.path.join(self.get_build_dir(), dest)
            else:
                raise ValueError("Url '%s' not possible to check out" % url)
        
                
    def package(self, outfile, update=False, local=True, remote=True):
        """
        Download all local resources required to build this service and write a tar stream to the output file.
        """
        log.debug("Packaging and streaming %s" % self.name)
        with TarPackaging(outfile) as tar:
            self._build(tar, update, local, remote, True)
        log.debug("Packaged %s" % self.name)
        
    def build(self, update=False, local=True, remote=True, write=False):
        """
        Download all local/remote resources required to build this service and generate build instructions.
        """
        log.debug("Building %s" % self.name)
        dockerfile = write and not os.path.exists(os.path.join(self.get_directory(), "Dockerfile"))
        self._build(LocalPackaging(self.get_directory(), write), update, local, remote, dockerfile)
        
    def _build(self, packaging, update, local, remote, dockerfile):
        def should_handle(url):
            lcl = checkout.url_is_local(url)
            return lcl and local or not lcl and remote
        
        # Create mutable copy of service
        resolved = dict(self.__root)
        
        rootdir = os.path.dirname(self.project.filename)
        container = resolved.get("container")
        
        if container:
            url = container.get("url")
            if url and should_handle(url):
                dest = self.checkout(url)
                del container["url"]
                if "subdirectory" in container:
                    dest = os.path.join(dest, container["subdirectory"])
                    del container["subdirectory"]
                dockerfile = os.path.join(dest, "Dockerfile")
                if not os.path.exists(dockerfile):
                    raise Exception("No Dockerfile found in %s (%s)" % (dest, url))
                container["dockerfile"] = os.path.relpath(dockerfile, rootdir)
                
            for name,src in container.get("files", dict()).items():
                packaging.addmap(src, name)
        df = list(self.get_dockerfile(local, remote))
        if df and "dockerfile" in container:
            packaging.addstr('\n'.join(df), 'Dockerfile')
            
        packaging.addstr(yaml.dump({self.name:resolved}), 'services.yml')

        # Add locally cached artifacts, if any
        d = self.get_build_dir(False)
        if os.path.isdir(d):
            packaging.addrel(d, rootdir)
        for f in self.get_dockerfile_referenced_files(df):
            packaging.addrel(f, rootdir)
   
    def get_directory(self):
        return os.path.dirname(self.project.filename)
             
    def type(self):
        t = self.__root.get("type", "default")
        if t in VALID_TYPES:
            return t
        else:
            self._fail("Service type '%s' is not recognized" % t)
        
    def is_abstract(self):
        return self.type() == "abstract"
        
    def as_dict(self):
        return self.__root
        
    def __repr__(self):
        return yaml.dump(self.as_dict())
        
    def _fail(self, message):
        return self.project._fail(message)

class LocalPackaging:
    def __init__(self, root, write):
        self.root = root
        self.write = write
    
    def addrel(self, filename, rootdir):
        arcname = os.path.relpath(filename, rootdir)
        log.debug("[f] %s" % arcname)
        return arcname
        
    def addstr(self, string, filename):
        log.debug("[g] %s:\n  %s" % (filename, '\n  '.join(string.split('\n'))))
        
class TarPackaging(tarfile.TarFile):
    def __init__(self, outfile):
        tarfile.TarFile.__init__(self, fileobj=outfile, mode='w')
        
    def addrel(self, filename, rootdir):
        arcname = os.path.relpath(filename, rootdir)
        self.add(filename, arcname=arcname)
        log.debug("[F] %s" % arcname)
        return arcname
        
    def addstr(self, string, filename):
        tarinfo = tarfile.TarInfo(name=filename)
        tarinfo.size = len(string)
        tarinfo.mtime = time.time()
        self.addfile(tarinfo=tarinfo, fileobj=StringIO.StringIO(string))
        log.debug("[G] %s" % filename)
        
    def addmap(self, src, arcname):
        src = os.path.expandvars(src)
        self.add(src, arcname=arcname)
        log.debug("[M] %s (%s)" % (arcname, src))
        
    

if __name__ == '__main__':
    print(Spec(file(sys.argv[1]), filename=sys.argv[1]))
