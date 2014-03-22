# -*- coding: utf-8 -*
from distutils.core import setup
import os

PACKAGE_NAME = "railgun"

def recurse(d):
    ret = []
    for f in os.listdir(d):
        if f.startswith("."): continue
        df = os.path.join(d, f)
        if os.path.isfile(df):
            ret.append(df)
        elif f != "build":
            ret += recurse(df)
    return ret
    
def structure(fs):
    s = {}
    for f in fs:
        d = os.path.dirname(f)
        if not d.startswith("meta/"): continue
        d = PACKAGE_NAME + d[4:]
        v = s.get(d, [])
        s[d] = v
        v.append(f)
    return s.items()
    
setup(name='docker-railgun',
    version='0.1',
    description='Self-organizing Docker-based container building and provisioning',
    author='Rickard Petzäll',
    author_email='rickard@evolviq.com',
    url='https://github.com/evolvIQ/railgun',
    packages=[PACKAGE_NAME, "%s.host_providers" % PACKAGE_NAME],
    scripts=['bin/railgun'],
    data_files=structure(recurse("meta"))
)
