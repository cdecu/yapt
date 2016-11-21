import os

from yapt import __version__
from setuptools import setup, find_packages

base = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(base, 'README.md'), encoding='utf-8') as file:
    long_description = file.read()

setup(
    name='yapt',
    version=__version__,
    description='PIL based photo tool',
    long_description=long_description,
    url='https://github.com/cdecu/yapt.git',
    download_url='',
    author='cdecu',
    author_email='carlos@decumont.be',
    maintainer='cdecu',
    maintainer_email='carlos@decumont.be',
    license='Freeware',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: Freeware',
        'Natural Language :: English',
        'Natural Language :: French',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Utilities'
    ],
    keywords='PIL based photo tool',
    platforms=['Any'],
    packages=find_packages(),
    install_requires=['Pillow', 'piexif', ''humanize'],
    entry_points={
        'console_scripts': ['yapt=yapt.yapt:main']
    }
)
