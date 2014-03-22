"Handles SCM checkouts and URL retrieval"
from __future__ import print_function
import sys, os
import urlparse
import urllib2
import subprocess
import logging
log = logging.getLogger(__name__)
    
def _call(cmd, shell=False, cwd=None, env=None, dryrun=False, retcode=None, errlen=1, stdin=None):
    if dryrun:
        print("(in %s)" % cwd)
        print(' '.join(cmd))
    else:
        stdin_param = None
        if stdin: stdin_param = subprocess.PIPE
        proc = subprocess.Popen(cmd, shell=shell, cwd=cwd, env=env, stdin=stdin_param)
        if stdin:
            _write_to_process(proc, stdin)
        ret = proc.wait()
        if not retcode is None:
            if ret != retcode:
                raise IOError("%s failed. See errors above." % ' '.join(cmd[:errlen]))
        return ret

def _write_to_process(proc, stdin):
    # Read standard input from parameter, can be file object or string
    if hasattr(stdin, "read"):
        while True:
            buf = stdin.read(8192)
            if len(buf) == 0:
                proc.stdin.close()
                break
            proc.stdin.write(buf)
    else:
        proc.stdin.write(stdin)
        proc.stdin.close()
        
def _eval(cmd, shell=False, cwd=None, env=None):
    proc = subprocess.Popen(cmd, shell=shell, cwd=cwd, env=env, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    stdout,_ = proc.communicate()
    return stdout.strip()
    
def url_is_local(url):
    if url.startswith("/"):
        return True
    url = urlparse.urlparse(url)
    return url.scheme == "file"
    
def get_local_file(url, ref=None):
    if url.startswith("/"):
        return url
    u = urlparse.urlparse(url)
    if not u.scheme:
        if ref:
            return os.path.abspath(os.path.join(ref, url))
        else:
            return url
    elif u.scheme == "file":
        if ref:
            return os.path.abspath(os.path.join(ref, url.path))
        else:
            return url.path
    return None
    
def is_url_or_file(string):
    "Returns True if the reference is an URL or a file name, as opposed to a container logical name"
    if string.startswith("/") or string.startswith("./") or string.startswith("../"):
        return True
    if os.path.exists(string):
        return True
    if urlparse.urlparse(string).scheme:
        return True
    return False
    
class Repository(object):
    update_callback = None # func(returnpath, post_update, did_change)
    clone_callback = None # func(returnpath, post_update)

class GitRepository(Repository):
    "git repository support"
    def checkout(self, url, local_path, subdir=None, dryrun=False, update_existing=False):
        url = self._normalize_url(url)
        destpath = os.path.join(local_path, self.get_destination_name(url))
        returnpath = destpath
        if subdir:
            returnpath = os.path.join(destpath, subdir)
        if os.path.exists(destpath):
            if os.path.isdir(destpath) and os.path.isdir(os.path.join(destpath, ".git")):
                if update_existing:
                    head = None
                    if self.update_callback:
                        head = _eval(["git","rev-parse","HEAD"], cwd=destpath)
                        self.update_callback(returnpath, False, False)
                    _call(["git","pull","--ff-only",url], cwd=destpath, dryrun=dryrun, retcode=0, errlen=2)
                    if self.update_callback:
                        head2 = _eval(["git","rev-parse","HEAD"], cwd=destpath)
                        self.update_callback(returnpath, True, head != head2)
            else:
                raise IOError("Path '%s' already exists and is not a git repo" % destpath)
        else:
            if self.clone_callback: self.clone_callback(returnpath, False)
            _call(["git","clone",url], cwd=local_path, dryrun=dryrun, retcode=0, errlen=2)
            if not dryrun and not os.path.isdir(destpath):
                raise IOError("Local git clone at '%s' vanished" % destpath)
            if self.clone_callback: self.clone_callback(returnpath, True)
        if not dryrun and subdir and not os.path.isdir(returnpath):
            raise IOError("Subdirectory '%s' does not exist in git repo" % subdir)
        return destpath
    
    def _normalize_url(self, url):
        if url.startswith("/"):
            return url
        url = urlparse.urlparse(url)
        if not url.scheme: url.scheme = "https"
        if url.scheme.startswith("git+"): url.scheme = url.scheme[4:]
        return url.geturl()
        
    def get_destination_name(self, url):
        pth = os.path.basename(url.strip("/"))
        if pth.endswith(".git"): pth = pth[:-4]
        return pth
    
class MercurialRepository(Repository):
    "hg repository support"
    def checkout(self, url, local_path, subdir=None, dryrun=False, update_existing=False):
        
        raise NotImplementedError()
        
def get_scm_provider(url):
    if url.startswith("/") or os.path.isdir(url):
        if os.path.isdir(os.path.join(url, ".git")):
            return GitRepository()
        elif os.path.isdir(os.path.join(url, ".hg")):
            return MercurialRepository()
    if isinstance(url, str) or isinstance(url, unicode):
        url = urlparse.urlparse(url)
    if url.scheme.startswith("git+") or url.path.strip("/").endswith(".git") or url.hostname and (url.hostname == "github.com" or url.hostname.endswith(".github.com")):
        return GitRepository()
    elif url.scheme.startswith("hg+") or url.path.strip("/").endswith(".hg") or url.hostname and (url.hostname == "bitbucket.org" or url.hostname.endswith(".bitbucket.org")):
        return MercurialRepository()
        
def is_scm_url(url):
    "Returns True if the URL is a SCM URL, False otherwise"
    return bool(get_scm_provider(url))

