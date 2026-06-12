#!/usr/bin/env python3
"""
MinecraftModelMigrator-Pro - Setup Configuration
==================================================
Package: minecraft-model-migrator
Version: 1.0.0
Entry point: cli:main
"""

from setuptools import setup, find_packages

setup(
    name='minecraft-model-migrator',
    version='1.0.0',
    description='Convert Minecraft 1.12.2 entity models to GeckoLib 1.20.1 format',
    long_description=open('README.md', 'r', encoding='utf-8').read() if __import__('os').path.exists('README.md') else '',
    long_description_content_type='text/markdown',
    author='MinecraftModelMigrator-Pro Team',
    license='MIT',
    python_requires='>=3.8',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'minecraft-model-migrator=cli:main',
            'animforge=animforge.main:main',
        ],
    },
    install_requires=[
        'numpy',
        'jinja2',
    ],
    extras_require={
        'full': [
            'javalang',
        ],
        'dev': [
            'pytest',
            'flake8',
        ],
    },
    package_data={
        'templates': [
            '*.j2',
        ],
    },
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language': 'Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Games/Entertainment',
        'Topic :: Software Development :: Code Generators',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='minecraft geckolib model converter migration 1.12.2 1.20.1',
)
