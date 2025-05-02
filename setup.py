from setuptools import setup
from setuptools.command.install import install
import subprocess

class CustomInstallCommand(install):
    def run(self):
        install.run(self)
        try:
            subprocess.check_call(['playwright', 'install'])
        except Exception as e:
            print(f"Warning: playwright install failed: {e}")

setup(
    name="operative",
    # ... you may want to add more metadata here ...
    cmdclass={
        'install': CustomInstallCommand,
    },
) 