from setuptools import setup
import redistrib

setup(
    name='redis-trib',
    version=redistrib.__version__,
    author='Chris Hoffman',
    author_email='chris@quixey.com',
    license='MIT',
    keywords='Redis Cluster',
    url=redistrib.REPO,
    description='Redis Cluster tools in Python2',
    packages=['redistrib'],
    long_description='Visit ' + redistrib.REPO + ' for details. Module forked from '
                                                 'https://github.com/HunanTV/redis-trib.py',
    install_requires=[
        'hiredis',
        'retrying',
        'six',
        'redis'
    ],
    zip_safe=False,
    entry_points=dict(
        console_scripts=[
            'redis-trib.py=redistrib.console:main',
        ],
    ),
)
