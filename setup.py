"""Setup script for the urwid-uikit library."""

from setuptools import setup, find_packages

requires = [
    "future>=0.17.1",
    "urwid>=2.0.1"
]

__version__ = None
exec(open("urwid_uikit/version.py").read())

setup(
    name="urwid-uikit",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    install_requires=requires
)
