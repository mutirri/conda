import os
import re
import sys
import json
import shutil
import tarfile
import tempfile
from os.path import abspath, basename, islink, join

from conda.install import activated, get_meta, prefix_placeholder
from conda.naming import split_canonical_name

import utils


def conda_installed_files(prefix):
    """
    Return the set of files which have been installed (using conda) info
    given prefix.
    """
    res = set()
    for dist in activated(prefix):
        meta = get_meta(dist, prefix)
        files = meta['files']
        res.update(set(files))
    return res


def get_installed_version(prefix, name):
    for dist in activated(prefix):
        n, v, b = split_canonical_name(dist)
        if n == name:
            return v
    return None


def walk_files(dir_path):
    """
    Return the set of all files in a given directory.
    """
    res = set()
    dir_path = abspath(dir_path)
    for root, dirs, files in os.walk(dir_path):
        for fn in files:
            res.add(join(root, fn)[len(dir_path) + 1:])
        for dn in dirs:
            path = join(root, dn)
            if islink(path):
                res.add(path[len(dir_path) + 1:])
    return res


def new_files(prefix):
    conda_files = conda_installed_files(prefix)
    return {path for path in walk_files(prefix) - conda_files
            if not (path.startswith(('pkgs/', 'envs/', 'conda-meta/')) or
                    path.endswith('~') or path == 'LICENSE.txt' or
                    (path.endswith('.pyc') and path[:-1] in conda_files))}


def create_info(name, version, build_number, requires_py):
    d = dict(
        name = name,
        version = version,
        platform = utils.PLATFORM,
        arch = utils.ARCH_NAME,
        build_number = build_number,
        build = str(build_number),
        requires = [],
    )
    if requires_py:
        d['build'] = ('py%d%d_' % requires_py) + d['build']
        d['requires'].append('python %d.%d' % requires_py)
    return d


shebang_pat = re.compile(r'^#!.+$', re.M)
def fix_shebang(tmp_dir, path):
    if open(path, 'rb').read(2) != '#!':
        return False

    with open(path) as fi:
        data = fi.read()
    m = shebang_pat.match(data)
    if not (m and 'python' in m.group()):
        return False

    data = shebang_pat.sub('#!%s/bin/python' % prefix_placeholder,
                           data, count=1)
    tmp_path = join(tmp_dir, basename(path))
    with open(tmp_path, 'w') as fo:
        fo.write(data)
    os.chmod(tmp_path, 0755)
    return True


def make_tarbz2(prefix, name='unknown', version='0.0', build_number=0):
    files = sorted(new_files(prefix))
    if any('/site-packages/' in f for f in files):
        python_version = get_installed_version(prefix, 'python')
        assert python_version is not None
        requires_py = tuple(int(x) for x in python_version[:3].split('.'))
    else:
        requires_py = False
    info = create_info(name, version, build_number, requires_py)
    fn = '%(name)s-%(version)s-%(build)s.tar.bz2' % info

    has_prefix = []
    tmp_dir = tempfile.mkdtemp()
    t = tarfile.open(fn, 'w:bz2')
    for f in files:
        path = join(prefix, f)
        if f.startswith('bin/') and fix_shebang(tmp_dir, path):
            path = join(tmp_dir, basename(path))
            has_prefix.append(f)
        t.add(path, f)

    info_dir = join(tmp_dir, 'info')
    os.mkdir(info_dir)

    with open(join(info_dir, 'files'), 'w') as fo:
        for f in files:
            fo.write(f + '\n')

    with open(join(info_dir, 'index.json'), 'w') as fo:
        json.dump(info, fo, indent=2, sort_keys=True)

    if has_prefix:
        with open(join(info_dir, 'has_prefix'), 'w') as fo:
            for f in has_prefix:
                fo.write(f + '\n')

    for fn in os.listdir(info_dir):
        t.add(join(info_dir, fn), 'info/' + fn)

    t.close()
    shutil.rmtree(tmp_dir)


if __name__ == '__main__':
    make_tarbz2(sys.prefix)