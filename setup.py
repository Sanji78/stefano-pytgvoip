#!/usr/bin/env python3

import multiprocessing
import os
import re
import sys
import platform
import sysconfig
import subprocess
import shutil

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext


def check_libraries():
    args = 'gcc -lssl -lopus'.split()
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        stdout, stderr = process.communicate()
        match = re.findall(r'cannot find -l(\w+)', stderr.decode())
        if match:
            raise RuntimeError(
                'Following libraries are not installed: {}\nFor installation guide refer to '
                'https://pytgvoip.readthedocs.io/en/latest/guides/install.html'.format(', '.join(match))
            )


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        super().__init__(name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


def _find_existing_libpython(python_root: str) -> str:
    """
    Try to locate an existing shared libpython for the running interpreter.
    """
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        # Common locations in python installs
        os.path.join(python_root, "lib", f"libpython{ver}.so.1.0"),
        os.path.join(python_root, "lib", f"libpython{ver}.so"),
        # Sometimes in /usr/local/lib or LIBDIR
        os.path.join(sysconfig.get_config_var("LIBDIR") or "", sysconfig.get_config_var("INSTSONAME") or ""),
        os.path.join(sysconfig.get_config_var("LIBDIR") or "", sysconfig.get_config_var("LDLIBRARY") or ""),
    ]
    for c in candidates:
        if c and os.path.exists(c) and c.endswith(".so") or c.endswith(".so.1.0"):
            return c
    # Allow .so.1.0 even if endswith check above is too strict
    for c in candidates:
        if c and os.path.exists(c) and ".so" in os.path.basename(c):
            return c
    return ""


def _find_static_libpython_fallback() -> str:
    """
    Locate a static libpython archive if present (cibuildwheel often has one in internal paths).
    """
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = []

    # sysconfig-derived (may point to .a)
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    ldlibrary = sysconfig.get_config_var("LDLIBRARY") or ""
    if libdir and ldlibrary and ldlibrary.endswith(".a"):
        candidates.append(os.path.join(libdir, ldlibrary))

    # Common internal cibuildwheel locations (best-effort)
    candidates += [
        f"/opt/_internal/cpython-{sysconfig.get_config_var('py_version_nodot') or ''}/lib/libpython{ver}.a",
        f"/opt/_internal/cpython-{sys.version.split()[0]}/lib/libpython{ver}.a",
    ]

    # Broad fallback search (only within /opt to keep it fast-ish)
    for root in ["/opt/_internal", "/opt/python"]:
        if os.path.isdir(root):
            for dirpath, _, filenames in os.walk(root):
                for fn in filenames:
                    if fn == f"libpython{ver}.a":
                        candidates.append(os.path.join(dirpath, fn))

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


def _build_shared_libpython_from_static(static_a: str, out_dir: str) -> str:
    """
    Build a shared libpython from a static libpython archive.
    This is used to produce a self-contained wheel for musl where runtime symbol resolution needs libpython.
    """
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    out_so = os.path.join(out_dir, f"libpython{ver}.so.1.0")

    os.makedirs(out_dir, exist_ok=True)

    # Attempt to create a shared library from the static archive.
    # This is not "pretty" but works in many CI images.
    cmd = [
        "gcc", "-shared", "-Wl,-soname," + os.path.basename(out_so),
        "-o", out_so,
        "-Wl,--whole-archive", static_a, "-Wl,--no-whole-archive",
        "-ldl", "-lpthread", "-lm"
    ]
    subprocess.check_call(cmd)
    return out_so


class CMakeBuild(build_ext):
    def run(self):
        try:
            subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed to build the following extensions: " +
                               ", ".join(e.name for e in self.extensions))

        if platform.system() != 'Windows':
            check_libraries()

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))

        python_exe = sys.executable
        python_root = os.path.dirname(os.path.dirname(python_exe))
        python_include = sysconfig.get_path("include") or ""

        # 1) Ensure we have a shared libpython we can bundle
        libpython = _find_existing_libpython(python_root)
        if not libpython:
            static_a = _find_static_libpython_fallback()
            if static_a:
                # Build the shared libpython into the build temp directory
                libpython = _build_shared_libpython_from_static(static_a, out_dir=os.path.abspath(self.build_temp))
            else:
                # Hard fail: cannot produce a wheel that doesn't require container setup on musl without libpython
                raise RuntimeError(
                    "Could not find libpython shared library or static archive to synthesize it. "
                    "Cannot build self-contained musl wheel."
                )

        # 2) Configure CMake args
        cmake_args = [
            f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}',
            f'-DPYTHON_EXECUTABLE={python_exe}',          # legacy
            f'-DPython3_EXECUTABLE={python_exe}',         # FindPython3
            f'-DPython3_ROOT_DIR={python_root}',
            '-DPython3_FIND_STRATEGY=LOCATION',
        ]

        if python_include:
            cmake_args += [
                f'-DPython3_INCLUDE_DIR={python_include}',
                f'-DPython3_INCLUDE_DIRS={python_include}',
            ]

        # Tell CMake to link against our bundled libpython
        cmake_args += [f'-DBUNDLED_PYTHON_LIBRARY={libpython}']

        print(">>> CMake Python3 hints:")
        print(">>>   Python3_EXECUTABLE =", python_exe)
        print(">>>   Python3_ROOT_DIR   =", python_root)
        print(">>>   Python3_INCLUDE    =", python_include)
        print(">>>   Bundled libpython  =", libpython)

        cfg = 'Release'
        build_args = ['--config', cfg, '--target', '_tgvoip']

        if platform.system() == "Windows":
            cmake_args += [f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}']
            cmake_args += ['-A', 'x64' if sys.maxsize > 2**32 else 'Win32']
            build_args += ['--', f'/m:{multiprocessing.cpu_count() + 1}']
        else:
            cmake_args += [f'-DCMAKE_BUILD_TYPE={cfg}']
            build_args += ['--', f'-j{multiprocessing.cpu_count() + 1}']

        env = os.environ.copy()
        env['CXXFLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(
            env.get('CXXFLAGS', ''),
            self.distribution.get_version()
        )

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
        subprocess.check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)

        # Copy stub typing file
        shutil.copy(os.path.join('src', '_tgvoip.pyi'), extdir)

        # 3) Bundle libpython next to the extension for musl runtime
        # Copy to extdir so it gets included in wheel
        shutil.copy(libpython, extdir)


def get_version():
    init_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'src', 'tgvoip', '__init__.py')
    with open(init_path, encoding='utf-8') as f:
        version = re.findall(r"__version__ = '(.+)'", f.read())[0]
        if os.environ.get('BUILD') is None and 'pip' not in __file__:
            version += '+develop'
        return version


def get_long_description():
    with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'README.md'), encoding='utf-8') as f:
        return f.read()


setup(
    name='stefano-pytgvoip',
    version="0.0.7.8",
    license='LGPLv3+',
    author='bakatrouble',
    author_email='bakatrouble@gmail.com',
    description='Telegram VoIP Library for Python',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    url='https://github.com/Sanji78/telegram_voip',
    keywords='telegram messenger voip library python',
    project_urls={
        'Tracker': 'https://github.com/bakatrouble/pytgvoip/issues',
        'Community': 'https:/t.me/pytgvoip',
        'Source': 'https://github.com/bakatrouble/pytgvoip',
    },
    python_requires='>=3.8',
    ext_modules=[CMakeExtension('_tgvoip')],
    packages=['tgvoip'],
    package_dir={'tgvoip': 'src/tgvoip'},
    cmdclass={'build_ext': CMakeBuild},
    zip_safe=False,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: C++',
        'Topic :: Internet',
        'Topic :: Communications',
        'Topic :: Communications :: Internet Phone',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
