import os
from setuptools import setup, find_packages

def parse_requirements(filename):
    """Load requirements from a pip requirements file."""
    with open(filename, 'r') as req_file:
        # Filter out comments and empty lines
        lines = req_file.read().splitlines()
        requirements = [
            line.strip() for line in lines 
            if line.strip() and not line.startswith('#')
        ]
    return requirements

# Construct the absolute path to your custom requirements file
base_dir = os.path.abspath(os.path.dirname(__file__))

# Define extras_require using the parsed requirements
extras_require = {
    'transcription': parse_requirements(
        os.path.join(base_dir, 'transcription', 'requirements.txt')
    )
}

setup(
    name='VideoNet',
    description='Fine-grained Action Recognition in Video',
    author='Tanush Yadav',
    author_email='tanush@cs.washington.edu',
    packages=find_packages(),
    extras_require=extras_require,
)
