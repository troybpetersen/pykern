# -*- coding: utf-8 -*-
"""Wrapper for setuptools.setup to simplify creating of `setup.py` files.

Python `setup.py` files should be short for well-structured projects.
`b_setup.setup` assumes there are directories such as `tests`, `docs`,
`bin`, etc. PyKern Projects use `py.test` so the appropriate `PyTest`
class is provided by this module.

Example:

    A sample ``setup.py`` script::

        setup(
            name='pyexample',
            description='Some Example app',
            author='Example, Inc.',
            author_email='somebody@example.com',
            url='http://example.com',
        )

Assumptions:

    - the use of ``pytest`` for tests. GUI and console scripts are
      found automatically by special suffixes ``_gui.py`` and
      ``_console.py``. See ``setup`` documentation for an example.

    - Under git control. Even if you are building an app for the first
      time, you should create the repo first. Does not assume anything
      about the remote (i.e. need not be a GitHub repo).

:copyright: Copyright (c) 2015 Radiasoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
# DO NOT import __future__. setuptools breaks with unicode in PY2:
# http://bugs.python.org/setuptools/issue152
# Get errors about package_data not containing wildcards, name not found, etc.

# Import only builtin/standard packages so avoid dependency issues
import copy
import datetime
import distutils.cmd
from distutils import log
from distutils.dist import DistributionMetadata
import errno
import glob
import inspect
import os
import os.path
import pip.download
import pip.req
import pkg_resources
import re
import setuptools
import setuptools.command.sdist
import setuptools.command.test
import subprocess
import sys
from distutils.config import PyPIRCCommand

#: The subdirectory in the top-level Python where to put resources
PACKAGE_DATA = 'package_data'

#: Created only during PyTest run
PYTEST_INI_FILE = 'pytest.ini'

#: Created only during Tox run
TOX_INI_FILE = 'tox.ini'

#: Where scripts live (not bin, because we want
SCRIPTS_DIR = 'scripts'


class NullCommand(distutils.cmd.Command, object):
    """Use to eliminate a ``cmdclass``.

    Does nothing but complies with :class:`distutils.cmd.Command` protocol.
    """

    user_options = []

    def initialize_options(*args, **kwargs):
        pass

    def finalize_options(*args, **kwargs):
        pass

    def run(*args, **kwargs):
        pass


class PKDeploy(NullCommand):
    """Run tests, build sdist or wheel, upload. Only use this on a clean git repo.

    The command will build the distro, then run tests on it with tox, which sets
    up a virtual environment.

    You must have the following environment variables:

    $PKSETUP_PYPI_USER
        Name of the user to login as on pypi

    $PKSETUP_PYPI_PASSWORD
        Name of the password

    This optional variable is useful for testing out your distro:

    $PKSETUP_PYPI_IS_TEST
        If set, will use testpypi, otherwise uses pypi.python.org

    All values provided by environment variables.
    """

    description = 'Runs git clean and tox; if successful, uploads to (test)pypi'

    def run(self):
        if self.distribution.dry_run:
            raise ValueError('--dry-run not supported')
        self.__env = {}
        # We assert these values before git clean, which would be a nasty
        # surprise if executed in an ordinary development environ
        is_test = self.__assert_env('PKSETUP_PYPI_IS_TEST', False)
        password = self.__assert_env('PKSETUP_PYPI_PASSWORD')
        user = self.__assert_env('PKSETUP_PYPI_USER')
        if not self.__assert_env('PKSETUP_PKDEPLOY_IS_DEV', False):
            subprocess.check_call(['git', 'clean', '-dfx'])
        self.__run_cmd('tox')
        sdist = glob.glob('.tox/dist/*-*.*')
        if len(sdist) != 1:
            raise ValueError('{}: should be exactly one sdist'.format(sdist))
        self.distribution.dist_files.append(('sdist', '', sdist[0]))
        repo = 'https://{}pypi.python.org/pypi'.format('test' if is_test else '')
        # Monkey Patch upload command so doesn't read
        self.__run_cmd(
            'upload',
            _read_pypirc=lambda: {
                'username': user,
                'password': password,
                'realm': 'pypi',
                'repository': repo,
            },
        )

    def __assert_env(self, key, default=None):
        v = os.getenv(key, default)
        if v is None:
            raise ValueError('${}: environment variable must be set'.format(key))
        return v

    def __run_cmd(self, cmd_name, **kwargs):
        self.announce('running {}'.format(cmd_name), level=log.INFO)
        klass = self.distribution.get_command_class(cmd_name)
        cmd = klass(self.distribution)
        cmd.initialize_options()
        for k in kwargs:
            assert hasattr(cmd, k), \
                '{}: "{}" command has no such option'.format(k, cmd_name)
            setattr(cmd, k, kwargs[k])
        cmd.finalize_options()
        cmd.run()


class PyTest(setuptools.command.test.test, object):
    """Proper initialization of `pytest` for ``python setup.py test``"""

    def initialize_options(self):
        """Run tests in ``--boxed`` mode (if available).

        Requires pytest plug ``xdist``.
        See https://bitbucket.org/pytest-dev/pytest-xdist#rst-header-boxed
        """
        # Not a new style class so super() doesn't work
        super(PyTest, self).initialize_options()
        self.pytest_args = self._boxed_if_os_supports() + ['-s']

    def finalize_options(self):
        """Initialize test_args and set test_suite to True"""
        super(PyTest, self).finalize_options()
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        """Import `pytest` and calls `main`. Calls `sys.exit` with result"""
        if os.getenv('PKSETUP_PKDEPLOY_IS_DEV', False):
            log.info('*** DEV MODE: not running tests ***')
            sys.exit(0)
        import pytest
        try:
            self._pytest_ini()
            exit = pytest.main(self.pytest_args)
        finally:
            _remove(PYTEST_INI_FILE)
        sys.exit(exit)

    def _boxed_if_os_supports(self):
        """Test for existence of `os.fork`

        This should be a conditional test in xdist.

        Returns:
            list: will be ``[--boxed]]`` if can `fork`
        """
        if hasattr(os, 'fork'):
            return ['--boxed']
        return []

    def _pytest_ini(self):
        """Create pytest.ini

        If you specify norecursedirs, pytest assumes that you don't
        just want to find files in "tests". This means it recurses
        ".tox", for example.

        We have a default set of subdirectories (*_work and *_data)
        which may contain python modules so we need to list norecursedirs.

        To workaround the problem, we specify "tests" in addopts.
        """
        _write(
            PYTEST_INI_FILE,
            '''[pytest]
# OVERWRITTEN by pykern.pksetup every "python setup.py test" run
norecursedirs = *_data *_work
addopts = tests
''',
        )


class SDist(setuptools.command.sdist.sdist, object):
    """Fix up a few things before running sdist"""

    def check_readme(self, *args, **kwargs):
        """Avoid README error message. We assert differntly.

        Currently only supports ``README.txt`` and ``README``,
        but we may have ``README.md``.
        """
        pass


class Tox(setuptools.Command, object):
    """Create tox.ini file"""

    description = 'create tox.ini and run tox'

    user_options = []

    def initialize_options(self, *args, **kwargs):
        pass

    def finalize_options(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        params = self._distribution_to_dict()
        _sphinx_apidoc(params)
        tox_ini = '''# OVERWRITTEN by pykern.pksetup every "python setup.py tox" run
[tox]
envlist={pyenv}
[testenv]
passenv=PKSETUP_PKDEPLOY_IS_DEV
deps=-rrequirements.txt
commands=python setup.py build test
[testenv:docs]
basepython=python
changedir=docs
commands=sphinx-build -b html -d {{envtmpdir}}/doctrees . {{envtmpdir}}/html
'''
        try:
            _write(TOX_INI_FILE, tox_ini.format(pyenv=self._pyenv(params)))
            subprocess.check_call(['tox'])
        finally:
            _remove(TOX_INI_FILE)

    def _distribution_to_dict(self):
        d = self.distribution.metadata
        res = {}
        for k in d._METHOD_BASENAMES:
            m = getattr(d, 'get_' + k)
            res[k] = m()
        res['packages'] = self.distribution.packages
        return res

    def _pyenv(self, params):
        pyenv = []
        for c in params['classifiers']:
            m = re.search(
                'Programming Language :: Python :: (\d+).(\d+)',
                c,
                flags=re.IGNORECASE,
            )
            if m:
                pyenv.append('py{}{}'.format(m.group(1), m.group(2)))
        if not pyenv:
            pyenv.append('py27')
        return ','.join(pyenv)


def setup(**kwargs):
    """Parses `README.*` and `requirements.txt`, sets some defaults, then
    calls `setuptools.setup`.

    Scripts are found by looking for files in the top level package directory
    which end with ``_console.py`` or ``_gui.py``. These files must have a
    function called ``main``.

    Example:
        The file ``pykern_console.py`` might contain::

            def main():
                print('hello world')

        This would create a program called command line program ``pykern`` which
        would call ``main()`` when invoked.

    Args:
        kwargs: see `setuptools.setup`
"""
    name = kwargs['name']
    assert type(name) == str, \
        'name must be a str; remove __future__ import unicode_literals in setup.py'
    reqs = pip.req.parse_requirements(
        'requirements.txt', session=pip.download.PipSession())
    install_requires = [str(i.req) for i in reqs]
    # If the incoming is unicode, this works in Python3
    # https://bugs.python.org/issue13943
    del kwargs['name']
    base = {
        'classifiers': [],
        'cmdclass': {
            'test': PyTest,
            'sdist': SDist,
            'tox': Tox,
            'pkdeploy': PKDeploy,
        },
        'test_suite': 'tests',
        'entry_points': _entry_points(name),
        # These both need to be set
        'install_requires': install_requires,
        'setup_requires': install_requires,
        'name': name,
        'packages': _packages(name),
        'tests_require': ['pytest'],
        'pksetup': kwargs['pksetup'] if 'pksetup' in kwargs else {}
    }
    base = _state(base)
    if 'cmdclass' in kwargs:
        cc = kwargs['cmdclass']
        if cc:
            base['cmdclass'].update(cc)
        del kwargs['cmdclass']
    base.update(kwargs)
    if os.getenv('READTHEDOCS'):
        _sphinx_apidoc(base)
    del base['pksetup']
    setuptools.setup(**base)


def _entry_points(pkg_name):
    """Find all *_{console,gui}.py files and define them

    Args:
        pkg_name (str): name of the package (directory)

    Returns:
        dict: Mapping of script names to module:methods
    """
    res = {}
    for s in ['console', 'gui']:
        tag = '_' + s
        for p in glob.glob(os.path.join(pkg_name, '*' + tag + '.py')):
            m = re.search(
                r'^([a-z]\w+)' + tag, os.path.basename(p), flags=re.IGNORECASE)
            if m:
                ep = res.setdefault(s + '_scripts', [])
                #TODO(robnagler): assert that 'def main()' exists in python module
                ep.append('{} = {}.{}:main'.format(m.group(1), pkg_name, m.group(0)))
    return res


def _find_files(dirname):
    """Find all files checked in with git and otherwise.

    Asserts git is installed and git repo.

    Args:
        dirname (str): directory

    Returns:
        list: Files to include in package
    """
    if _git_exists():
        res = _git_ls_files(['--others', '--exclude-standard', dirname])
        res.extend(_git_ls_files([dirname]))
    else:
        res = []
        for r, _, files in os.walk(dirname):
            for f in files:
                res.append(os.path.join(r, f))
    return sorted(res)


def _git_exists():
    """Have a git repo?

    Returns:
        bool: True if .git dir exists
    """
    return os.path.isdir('.git')


def _git_ls_files(extra_args):
    """Find all the files under git control

    Will return nothing if package_data doesn't exist or no files in it.

    Args:
        extra_args (list): other args to append to command

    Returns:
        list: Files under git control.
    """
    cmd = ['git', 'ls-files']
    cmd.extend(extra_args)
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return out.splitlines()


def _packages(name):
    """Find all packages by looking for ``__init__.py`` files.

    Mostly borrowed from https://bitbucket.org/django/django/src/tip/setup.py

    Args:
        name (str): name of the package (directory)

    Returns:
        list: packages names
    """
    def _fullsplit(path, result=None):
        """
        Split a pathname into components (the opposite of os.path.join) in a
        platform-neutral way.

        """
        if result is None:
            result = []
        head, tail = os.path.split(path)
        if head == '':
            return [tail] + result
        if head == path:
            return result
        return _fullsplit(head, [tail] + result)

    res = []
    for dirpath, _, filenames, in os.walk(name):
        if '__init__.py' in filenames:
            res.append(str('.'.join(_fullsplit(dirpath))))
    return res


def _read(filename):
    """Open and read filename

    Args:
        filename (str): what to read

    Returns:
        str: contents of filename
    """
    with open(filename, 'r') as f:
        return f.read()


def _readme():
    """Find the README.*. Prefer README.rst

    Returns:
        str: Name of README
    """
    for which in 'README.rst', 'README.md', 'README.txt':
        if os.path.exists(which):
            return which
    raise ValueError('You need to create a README.rst')


def _remove(path):
    """Remove path without throwing an exception"""
    try:
        os.remove(path)
    except OSError:
        pass


def _sphinx_apidoc(base):
    """Call `sphinx-apidoc` with appropriately configured ``conf.py``.

    Args:
        base (dict): values to be passed to ``conf.py.in`` template
    """
    # Deferred import so initial setup.py works
    values = copy.deepcopy(base)
    values['year'] = datetime.datetime.now().year
    values['empty_braces'] = '{}'
    from pykern import pkresource
    data = _read(pkresource.filename('docs-conf.py.format'))
    _write('docs/conf.py', data.format(**values))
    subprocess.check_call(
        [
            'sphinx-apidoc',
            '-f',
            '-o',
            'docs',
        ] + base['packages'],
    )
    return base


def _state(base):
    """Gets version and package_data. Writes MANIFEST.in.

    Args:
        base (dict): our base params

    Returns:
        dict: base updated
    """
    state = {
        'version': _version(base),
    }
    manifest = '''# OVERWRITTEN by pykern.pksetup every "python setup.py"
include LICENSE
include requirements.txt
'''
    readme = _readme()
    state['long_description'] = _read(readme)
    manifest += 'include {}\n'.format(readme)
    dirs = ['docs', 'tests']
    if 'extra_directories' in base['pksetup']:
        dirs.extend(base['pksetup']['extra_directories'])
    for which in (PACKAGE_DATA, SCRIPTS_DIR):
        is_pd = which == PACKAGE_DATA
        d = os.path.join(base['name'], which) if is_pd else which
        f = _find_files(d)
        if f:
            if is_pd:
                state[which] = {base['name']: f}
                state['include_package_data'] = True
            else:
                state[which] = f
            dirs.append(d)
    manifest += ''.join(['recursive-include {} *\n'.format(d) for d in dirs])
    _write('MANIFEST.in', manifest)
    base.update(state)
    return base


def _version(base):
    """Get a chronological version from git or PKG-INFO

    Args:
        base (dict): state

    Returns:
        str: Chronological version "yyyymmdd.hhmmss"
    """
    v1 = _version_from_pkg_info(base)
    v2 = _version_from_git(base)
    if v1:
        if v2:
            return v1 if float(v1) > float(v2) else v2
        return v1
    if v2:
        return v2
    raise ValueError('Must have a git repo or an source distribution')


def _version_from_git(base):
    """Chronological version string for most recent commit or time of newer file.

    Finds the commit date of the most recent branch. Uses ``git
    ls-files`` to find files under git control which are modified or
    to be deleted, in which case we assume this is a developer, and we
    should just use the current time for the version. It will be newer
    than any committed version, which is all we care about for upgrades.

    Args:
        base (dict): state

    Returns:
        str: Chronological version "yyyymmdd.hhmmss"
    """
    if not _git_exists():
        return
    # Under development?
    if len(_git_ls_files(['--modified', '--deleted'])):
        vt = datetime.datetime.utcnow()
    else:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD']).rstrip()
        vt = subprocess.check_output(
            ['git', 'log', '-1', '--format=%ct', branch]).rstrip()
        vt = datetime.datetime.fromtimestamp(float(vt))
    v = vt.strftime('%Y%m%d.%H%M%S')
    # Avoid 'UserWarning: Normalizing' by setuptools
    return str(pkg_resources.parse_version(v))


def _version_from_pkg_info(base):
    """Extra existing version from PKG-INFO if there

    Args:
        base (dict): state

    Returns:
        str: Chronological version "yyyymmdd.hhmmss"
    """
    try:
        d = _read(base['name'] + '.egg-info/PKG-INFO')
        # Must match yyyymmdd version, else generate
        m = re.search(r'Version:\s*(\d{8}\.\d+)\s', d)
        if m:
            return m.group(1)
    except IOError:
        pass


def _write(filename, content):
    """Writes a file"""
    with open(filename, 'w') as f:
        f.write(content)
