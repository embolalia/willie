"""Test for the ``sopel.plugins`` module."""
from __future__ import generator_stop

import sys

import pkg_resources
import pytest

from sopel import plugins


MOCK_MODULE_CONTENT = """from __future__ import generator_stop
from sopel import plugin


@plugin.commands("first")
def first_command(bot, trigger):
    pass


@plugin.commands("second")
def second_command(bot, trigger):
    pass


@plugin.interval(5)
def interval5s(bot):
    pass


@plugin.interval(10)
def interval10s(bot):
    pass


@plugin.url(r'.\\.example\\.com')
def example_url(bot):
    pass


@plugin.event('TOPIC')
def on_topic_command(bot):
    pass


def shutdown():
    pass


def ignored():
    pass

"""


def test_plugin_load_pymod(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    mod_file = root.join('file_mod.py')
    mod_file.write(MOCK_MODULE_CONTENT)

    plugin = plugins.handlers.PyFilePlugin(mod_file.strpath)
    plugin.load()

    test_mod = plugin._module

    assert hasattr(test_mod, 'first_command')
    assert hasattr(test_mod, 'second_command')
    assert hasattr(test_mod, 'interval5s')
    assert hasattr(test_mod, 'interval10s')
    assert hasattr(test_mod, 'example_url')
    assert hasattr(test_mod, 'shutdown')
    assert hasattr(test_mod, 'ignored')


def test_plugin_load_pymod_bad_file_pyc(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    test_file = root.join('file_module.pyc')
    test_file.write('')

    with pytest.raises(Exception):
        plugins.handlers.PyFilePlugin(test_file.strpath)


def test_plugin_load_pymod_bad_file_no_ext(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    test_file = root.join('file_module')
    test_file.write('')

    with pytest.raises(Exception):
        plugins.handlers.PyFilePlugin(test_file.strpath)


def test_plugin_load_pypackage(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    package_dir = root.mkdir('dir_mod')
    mod_file = package_dir.join('__init__.py')
    mod_file.write(MOCK_MODULE_CONTENT)

    plugin = plugins.handlers.PyFilePlugin(package_dir.strpath)
    plugin.load()

    test_mod = plugin._module

    assert hasattr(test_mod, 'first_command')
    assert hasattr(test_mod, 'second_command')
    assert hasattr(test_mod, 'interval5s')
    assert hasattr(test_mod, 'interval10s')
    assert hasattr(test_mod, 'example_url')
    assert hasattr(test_mod, 'shutdown')
    assert hasattr(test_mod, 'ignored')


def test_plugin_load_pypackage_bad_dir_empty(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    package_dir = root.mkdir('dir_package')

    with pytest.raises(Exception):
        plugins.handlers.PyFilePlugin(package_dir.strpath)


def test_plugin_load_pypackage_bad_dir_no_init(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    package_dir = root.mkdir('dir_package')
    package_dir.join('no_init.py').write('')

    with pytest.raises(Exception):
        plugins.handlers.PyFilePlugin(package_dir.strpath)


def test_plugin_load_entry_point(tmpdir):
    root = tmpdir.mkdir('loader_mods')
    mod_file = root.join('file_mod.py')
    mod_file.write(MOCK_MODULE_CONTENT)

    # generate setuptools Distribution object
    distrib = pkg_resources.Distribution(root.strpath)
    sys.path.append(root.strpath)

    # load the entry point
    try:
        entry_point = pkg_resources.EntryPoint(
            'test_plugin', 'file_mod', dist=distrib)
        plugin = plugins.handlers.EntryPointPlugin(entry_point)
        plugin.load()
    finally:
        sys.path.remove(root.strpath)

    assert plugin.name == 'test_plugin'

    test_mod = plugin._module

    assert hasattr(test_mod, 'first_command')
    assert hasattr(test_mod, 'second_command')
    assert hasattr(test_mod, 'interval5s')
    assert hasattr(test_mod, 'interval10s')
    assert hasattr(test_mod, 'example_url')
    assert hasattr(test_mod, 'shutdown')
    assert hasattr(test_mod, 'ignored')
