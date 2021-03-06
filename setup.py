#!/usr/bin/env python

#------------------------------------------------------------------------

import os
import sys
import shutil
import textwrap
from os.path import join

from distutils.core import Command, setup
from distutils.sysconfig import get_python_inc, get_config_var

#------------------------------------------------------------------------
# Top Level Packages
#------------------------------------------------------------------------

packages = [
    'blaze',
    'blaze.algo',
    'blaze.algo.linalg',
    'blaze.aterm',
    'blaze.blir',
    'blaze.carray',
    'blaze.datashape',
    'blaze.desc',
    'blaze.dist',
    'blaze.expr',
    'blaze.include',
    'blaze.layouts',
    'blaze.persistence',
    'blaze.module',
    'blaze.rts',
    'blaze.sources',
    'blaze.ts',
    'blaze.ts.ucr_dtw',
]

#------------------------------------------------------------------------
# Minimum Versions
#------------------------------------------------------------------------

min_cython_version = '0.16'
min_numpy_version  = '1.5'
min_llvmpy_version = '0.11.1'

#------------------------------------------------------------------------
# Utilities
#------------------------------------------------------------------------

# Some functions for showing errors and warnings.
def _print_admonition(kind, head, body):
    tw = textwrap.TextWrapper(
        initial_indent='   ', subsequent_indent='   ')

    print ".. %s:: %s" % (kind.upper(), head)
    for line in tw.wrap(body):
        print line

def exit_with_error(head, body=''):
    _print_admonition('error', head, body)
    sys.exit(1)

def print_warning(head, body=''):
    _print_admonition('warning', head, body)

def check_import(pkgname, pkgver):
    try:
        mod = __import__(pkgname)
    except ImportError:
            exit_with_error(
                "You need %(pkgname)s %(pkgver)s or greater to run carray!"
                % {'pkgname': pkgname, 'pkgver': pkgver} )
    else:
        if mod.__version__ < pkgver:
            exit_with_error(
                "You need %(pkgname)s %(pkgver)s or greater to run carray!"
                % {'pkgname': pkgname, 'pkgver': pkgver} )

    print ( "* Found %(pkgname)s %(pkgver)s package installed."
            % {'pkgname': pkgname, 'pkgver': mod.__version__} )
    globals()[pkgname] = mod

#------------------------------------------------------------------------
# Cython Sanity Check
#------------------------------------------------------------------------

try:
    from Cython.Distutils import Extension, build_ext
    from Cython.Compiler.Main import Version
except:
    exit_with_error(
        "You need %(pkgname)s %(pkgver)s or greater to compile carray!"
        % {'pkgname': 'Cython', 'pkgver': min_cython_version} )

if Version.version < min_cython_version:
    exit_with_error(
        "At least Cython %s is needed so as to generate extensions!"
        % (min_cython_version) )
else:
    print ( "* Found %(pkgname)s %(pkgver)s package installed."
            % {'pkgname': 'Cython', 'pkgver': Version.version} )

#------------------------------------------------------------------------
# Numpy Sanity Check
#------------------------------------------------------------------------

check_import('numpy', min_numpy_version)

#------------------------------------------------------------------------
# LLVM Sanity Check
#------------------------------------------------------------------------

#check_import('llvmpy', min_llvmpy_version)

#------------------------------------------------------------------------
# C Compiler Environment
#------------------------------------------------------------------------

# Global variables
CFLAGS = os.environ.get('CFLAGS', '').split()
LFLAGS = os.environ.get('LFLAGS', '').split()

lib_dirs = []
libs = []
# Include NumPy header dirs
from numpy.distutils.misc_util import get_numpy_include_dirs
optional_libs = []

# Handle --lflags=[FLAGS] --cflags=[FLAGS]
args = sys.argv[:]
for arg in args:
    if arg.find('--lflags=') == 0:
        LFLAGS = arg.split('=')[1].split()
        sys.argv.remove(arg)
    elif arg.find('--cflags=') == 0:
        CFLAGS = arg.split('=')[1].split()
        sys.argv.remove(arg)

# Add -msse2 flag for optimizing shuffle in include Blosc
if os.name == 'posix':
    CFLAGS.append("-msse2")

# Add some macros here for debugging purposes, if needed
def_macros = [('DEBUG', 0)]


#------------------------------------------------------------------------
# Extension
#------------------------------------------------------------------------

numpy_path = get_numpy_include_dirs()[0]

blosc_path  = 'blaze/include/blosc/'
desc_path   = "blaze/desc/"


carray_source = [
    "blaze/carray/carrayExtension.pyx"
]

carray_depends = [
]

blosc_source = [
    blosc_path + "blosc.c",
    blosc_path + "blosclz.c",
    blosc_path + "shuffle.c"
]

blosc_depends = [
    blosc_path + "blosc.h",
    blosc_path + "blosclz.h",
    blosc_path + "shuffle.h"
]

descriptor_depends = [
    desc_path + "lldescriptors.pxd",
    desc_path + "lldescriptors.pyx",
    desc_path + "llindexers.pyx",
]

extensions = [
    Extension(
        "blaze.carray.carrayExtension",
        include_dirs=[
            blosc_path,
            numpy_path,
        ],

        sources = list(carray_source + blosc_source),
        depends = list(carray_depends + blosc_depends),

        library_dirs=lib_dirs,
        libraries=libs,
        extra_link_args=LFLAGS,
        extra_compile_args=CFLAGS,
        define_macros=def_macros,
   ),
   Extension(
        "blaze.ts.ucr_dtw.ucr",
        sources = ["blaze/ts/ucr_dtw/ucr.pyx", "blaze/ts/ucr_dtw/dtw.c"],
        depends = ["blaze/ts/ucr_dtw/dtw.h"],
        include_dirs = [numpy_path]
   ),
   Extension(
       "blaze.desc.lldescriptors",
       ["blaze/desc/lldescriptors.pyx"],
       include_dirs = [],
       depends=descriptor_depends,
   ),
   Extension(
       "blaze.desc.llindexers",
       ["blaze/desc/llindexers.pyx"],
       include_dirs = [],
       depends=descriptor_depends,
   ),

   Extension(
        "blaze.cutils", ["blaze/cutils.pyx"],
        include_dirs = [numpy_path],
   ),

   Extension(
        "blaze.algo.stats",
        sources = ["blaze/algo/stats.pyx"],
        include_dirs = [numpy_path]
   ),

   # ----------------------------------------

   #Extension(
   #     "blaze.rts.runtime",
   #     sources = ["blaze/rts/runtime.c"],
   #     include_dirs = [],
   #),
   #Extension(
   #     "blaze.rts.wrapper",
   #     sources = ["blaze/rts/wrapper.pyx"],
   #     include_dirs = [numpy_path],
   #),

   # ----------------------------------------

   Extension(
        "blaze.blir.datashape",
        sources = ["blaze/blir/datashape.c"],
        include_dirs = [],
   ),

#   Extension(
#        "blaze.blir.prelude",
#        sources = ["blaze/blir/prelude.c"],
#        depends = ["blaze/blir/datashape.c"],
#        include_dirs = [],
#   ),
]

#------------------------------------------------------------------------
# Commands
#------------------------------------------------------------------------

class CleanCommand(Command):
    """Custom distutils command to clean the .so and .pyc files."""

    user_options = []

    def initialize_options(self):
        self._clean_me = []
        self._clean_trees = []

        for toplevel in packages:
            for root, dirs, files in list(os.walk(toplevel)):
                for f in files:
                    if os.path.splitext(f)[-1] in ('.pyc', '.so', '.o', '.pyd'):
                        self._clean_me.append(join(root, f))

        for d in ('build',):
            if os.path.exists(d):
                self._clean_trees.append(d)

    def finalize_options(self):
        pass

    def run(self):
        for clean_me in self._clean_me:
            try:
                print 'flushing', clean_me
                os.unlink(clean_me)
            except Exception:
                pass
        for clean_tree in self._clean_trees:
            try:
                print 'flushing', clean_tree
                shutil.rmtree(clean_tree)
            except Exception:
                pass

#------------------------------------------------------------------------
# Setup
#------------------------------------------------------------------------

longdesc = open('README.md').read()

setup(
    name='blaze',
    version='dev',
    author='Continuum Analytics',
    author_email='blaze-dev@continuum.io',
    description='Blaze',
    long_description=longdesc,
    data_files=[],
    license='BSD',
    platforms = ['any'],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Education',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering',
        'Topic :: Utilities',
    ],
    packages=packages,
    ext_modules=extensions,
    cmdclass = {
        'build_ext' : build_ext,
        'clean'     : CleanCommand,
    },
    scripts=['bin/blirc'],
)
