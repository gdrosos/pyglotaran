from setuptools import setup
from setuptools.extension import Extension
# TODO: include generated c and include switches if cython is not available ->
# https://stackoverflow.com/questions/4505747/how-should-i-structure-a-python-package-that-contains-cython-code
from Cython.Distutils import build_ext
# TODO: bootstrap numpy ->
# https://stackoverflow.com/questions/19919905/how-to-bootstrap-numpy-installation-in-setup-py
import numpy
import scipy
import sys

if sys.platform == 'win32':
    ext_modules = [
        Extension("c_matrix",
                  ["glotaran_models/kinetic/c_matrix.pyx"],
                  include_dirs=[numpy.get_include(),scipy.get_include()],
                  extra_compile_args=["-O3", "-ffast-math", "-march=native",
                                      "-fopenmp"],
                  extra_link_args=['-fopenmp']),
        Extension("c_matrix_gaussian_irf",
                  ["glotaran_models/kinetic/c_matrix_gaussian_irf.pyx"],
                  include_dirs=[numpy.get_include(), scipy.get_include()],
                  extra_compile_args=["-O3", "-ffast-math", "-march=native",
                                      "-fopenmp"],
                  extra_link_args=['-fopenmp'])
                  ]
else:
    ext_modules = [
        Extension("c_matrix",
                  ["glotaran_models/kinetic/c_matrix.pyx"],
                  include_dirs=[numpy.get_include(), scipy.get_include()],
                  libraries=["m"],
                  extra_compile_args=["-O3", "-ffast-math", "-march=native",
                                      "-fopenmp"],
                  extra_link_args=['-fopenmp']),
        Extension("c_matrix_gaussian_irf",
                  ["glotaran_models/kinetic/c_matrix_gaussian_irf.pyx"],
                  include_dirs=[numpy.get_include(), scipy.get_include()],
                  libraries=["m"],
                  extra_compile_args=["-O3", "-ffast-math", "-march=native",
                                      "-fopenmp"],
                  extra_link_args=['-fopenmp'])
                  ]


setup(
    name="glotaran-core",
    version="0.1.0",
    description='The Glotaran fitting engine.',
    url='http://github.com/ThingiverseIO/pythingiverseio',
    author='Joris Snellenburg, Stefan Schuetz, Joern Weissenborn',
    author_email="""j.snellenburg@vu.nl,
                    YamiNoKeshin@gmail.com,
                    joern.weissenborn@gmail.com""",
    license='GPLv3',
    packages=['glotaran_core.fitting.variable_projection',
              'glotaran_core.model',
              'glotaran_models.kinetic',
              'glotaran_models.kinetic.c_matrix_opencl',
              'glotaran_tools.specification_parser'
              ],
    install_requires=[
        'numpy',
        'click',
        'scipy',
        'lmfit',
        'pyyaml',
    ],
    package_data={'glotaran_models.kinetic.c_matrix_opencl':
                  ['*.cl']},
    cmdclass={"build_ext": build_ext},
    ext_modules=ext_modules,
    test_suite='nose.collector',
    tests_require=['nose'],
)
