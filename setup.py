from setuptools import setup

setup(
    name='hive-archeology-bot',
    version="0.1.1",
    description="Hive Archeology Bot",
    long_description="Simple HIVE bot that allows its owner to up-vote valuable timeless HIVE posts.",
    author='Rob Meijer',
    author_email='pibara@gmail.com',
    url='https://github.com/pibara/hive-archeology',
    license='BSD',
    py_modules=['hive_archeology'],
    include_package_data=True,
    zip_safe=False,
    python_requires='>=3.6',
    entry_points={
        'console_scripts': [
            'hive-archeology-bot = hive_archeology:_main',
        ],
    },
    keywords='hive web3 bot',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=["base58", "aioflureedb>=0.6.4", "requests<=2.28.1"],
)
