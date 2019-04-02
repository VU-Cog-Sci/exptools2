import os.path as op
import os
from setuptools import setup, find_packages

# Format expected by setup.py and doc/source/conf.py: string of form "X.Y.Z"
_version_major = 0
_version_minor = 1
_version_micro = ''  # use '' for first of series, number for 1 and above
_version_extra = 'dev'
# _version_extra = ''  # Uncomment this for full releases

# Construct full version string from these.
_ver = [_version_major, _version_minor]
if _version_micro:
    _ver.append(_version_micro)
if _version_extra:
    _ver.append(_version_extra)

__version__ = '.'.join(map(str, _ver))

CLASSIFIERS = ["Development Status :: 3 - Alpha",
               "Environment :: Console",
               "Intended Audience :: Science/Research",
               "License :: OSI Approved :: MIT License",
               "Operating System :: OS Independent",
               "Programming Language :: Python",
               "Topic :: Scientific/Engineering"]

# Description should be a one-liner:
description = "exptools2: stimulus presentation for psychophysics experiments"
# Long description will go up on the pypi page
long_description = """
exptools2
=========
Bla bla.
To get started, please go to the repository README_.
.. _README: https://github.com/VU-Cog-Sci/exptools2/blob/master/README.md
"""

NAME = "exptools2"
MAINTAINER = "Tomas Knapen"
MAINTAINER_EMAIL = "tomasknapen@gmail.com"
DESCRIPTION = description
LONG_DESCRIPTION = long_description
URL = "http://github.com/VU-Cog-Sci/exptools2"
DOWNLOAD_URL = ""
LICENSE = "MIT"
AUTHOR = "Tomas Knapen"
AUTHOR_EMAIL = "tomasknapen@gmail.com"
PLATFORMS = "OS Independent"
MAJOR = _version_major
MINOR = _version_minor
MICRO = _version_micro
VERSION = __version__
PACKAGE_DATA = {'exptools2': [op.join('data', '*')]}
PACKAGES = find_packages()
REQUIRES = [
    'psychopy>=3.0.4',
    'pyyaml',
    'pandas>=0.23.0',
    'numpy>=1.14.3',
    'msgpack_numpy'
]

opts = dict(
    name=NAME,
    maintainer=MAINTAINER,
    maintainer_email=MAINTAINER_EMAIL,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    url=URL,
    download_url=DOWNLOAD_URL,
    license=LICENSE,
    classifiers=CLASSIFIERS,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    platforms=PLATFORMS,
    version=VERSION,
    packages=PACKAGES,
    package_data=PACKAGE_DATA,
    install_requires=REQUIRES,
    entry_points={
                'console_scripts': [
                    'exptools2_fLoc = exptools2.experiments.fLoc.main:main_api',
                    ]
                }
)


if __name__ == '__main__':
    setup(**opts)
