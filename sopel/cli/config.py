# coding=utf-8
"""Sopel Config Command Line Interface (CLI): ``sopel-config``"""
from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os

from sopel import tools
from sopel.config import types
from . import utils


def build_parser():
    """Build and configure an argument parser for ``sopel-config``.

    :return: the argument parser
    :rtype: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Sopel configuration tool')

    # Subparser: sopel-config <sub-parser> <sub-options>
    subparsers = parser.add_subparsers(
        help='Actions to perform',
        dest='action')

    # sopel-config list
    list_parser = subparsers.add_parser(
        'list',
        help="List available configurations from Sopel's config directory",
        description="""
            List available configurations from Sopel's config directory
            with the extension "{ext}". Use option ``--config-dir`` to use a
            specific config directory.
        """.format(ext='.cfg'))
    utils.add_common_arguments(list_parser)
    list_parser.add_argument(
        '-e', '--ext', '--extension',
        dest='extension',
        default='.cfg',
        help='Filter by extension (default to "%(default)s)"')
    list_parser.add_argument(
        '-p', '--path',
        action='store_true',
        dest='display_path',
        default=False,
        help='Display a list of absolute filenames instead of their names')

    # sopel-config init
    init_parser = subparsers.add_parser(
        'init',
        help='Initialize Sopel configuration file',
        description='Initialize Sopel configuration file')
    utils.add_common_arguments(init_parser)

    # sopel-config get <section> <key>
    get_parser = subparsers.add_parser(
        'get',
        help="Get a configuration option's value",
        description="Get a configuration option's value",
    )
    get_parser.add_argument('section')
    get_parser.add_argument('option')
    utils.add_common_arguments(get_parser)

    # sopel-config set <section> <key> <value>
    set_parser = subparsers.add_parser(
        'set',
        help="Set a configuration option's value",
        description="Set a configuration option's value",
    )
    set_parser.add_argument('section')
    set_parser.add_argument('option')
    set_parser.add_argument('value')
    utils.add_common_arguments(set_parser)

    # sopel-config unset <section> <key>
    unset_parser = subparsers.add_parser(
        'unset',
        help="Unset a configuration option",
        description="Unset a configuration option",
    )
    unset_parser.add_argument('section')
    unset_parser.add_argument('option')
    utils.add_common_arguments(unset_parser)

    return parser


def handle_list(options):
    """Display a list of configurations available in Sopel's config directory.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine

    This command displays an unordered list of config names from Sopel's
    config directory, without their extensions::

        $ sopel-config list
        default
        custom

    By default, the config directory is ``~/.sopel``. To select a different
    config directory, options ``--config-dir`` can be used.

    It is possible to filter by extension using the
    ``-e``/``--ext``/``--extension`` option; default is ``.cfg``
    (the ``.`` prefix is not required).
    """
    configdir = options.configdir
    display_path = options.display_path
    extension = options.extension
    if not extension.startswith('.'):
        extension = '.' + extension
    configs = utils.enumerate_configs(configdir, extension)

    for config_filename in configs:
        if display_path:
            print(os.path.join(configdir, config_filename))
        else:
            name, _ = os.path.splitext(config_filename)
            print(name)

    return 0  # successful operation


def handle_init(options):
    """Use config wizard to initialize a new configuration file for the bot.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine;
             1 if the file is invalid or if it already exists

    .. note::

       Due to how the config wizard works, the configuration filename's
       extension **must be** ``.cfg``.

    """
    config_filename = utils.find_config(options.configdir, options.config)
    config_name, ext = os.path.splitext(config_filename)

    if ext and ext != '.cfg':
        tools.stderr('Configuration wizard accepts .cfg files only')
        return 1
    elif not ext:
        config_filename = config_name + '.cfg'

    if os.path.isfile(config_filename):
        tools.stderr('Configuration file %s already exists' % config_filename)
        return 1

    print('Starting Sopel config wizard for: %s' % config_filename)
    utils.wizard(config_name)
    return 0  # successful operation


def handle_get(options):
    """Read the settings to display the value of ``<section> <key>``.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine;
             1 if the section and/or key does not exist;
             2 if the settings can't be loaded
    """
    try:
        settings = utils.load_settings(options)
    except Exception as error:
        tools.stderr(error)
        return 2

    section = options.section
    option = options.option

    # Making sure the section.option exists
    if not settings.parser.has_section(section):
        tools.stderr('Section "%s" does not exist' % section)
        return 1
    if not settings.parser.has_option(section, option):
        tools.stderr(
            'Section "%s" does not have a "%s" option' % (section, option))
        return 1

    # Display the value
    print(settings.get(section, option))
    return 0  # successful operation


def handle_set(options):
    """Set the ``<section> <key>`` setting to ``<value>``.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine;
             1 if the section and/or key does not exist;
             2 if the settings can't be loaded
             3 if the input was not valid
    """
    try:
        settings = utils.load_settings(options)
    except Exception as error:
        tools.stderr('Cannot load settings: ' + str(error))
        return 2

    section_name = options.section
    option_name = options.option
    value = options.value

    # Make sure the section exists
    section = getattr(settings, section_name, False)
    if not section:
        tools.stderr(
            'Section "%s" does not exist' % section_name)
        return 1

    # Make sure option exists, if section is static
    # TODO: With current (7.1-dev) settings loader, only `core` will ever be
    # a StaticSection, meaning plugin sections' values won't be validated.
    static_sec = isinstance(section, types.StaticSection)
    if static_sec and not hasattr(section, option_name):
        tools.stderr(
            'Section "%s" does not have an option "%s"'
            % (section_name, option_name))
        return 1

    # Validate value if possible
    descriptor = getattr(section.__class__, option_name) if static_sec else None
    if descriptor is not None:
        try:
            value = descriptor._parse(value, settings, section)
        except ValueError as e:
            tools.stderr(
                'Cannot set "{}.{}": {}'.format(section_name, option_name, str(e)))
            return 3

    # Update the option & save config file
    setattr(section, option_name, value)
    settings.save()
    print('Updated option "{}.{}"'.format(section_name, option_name))
    return 0  # successful operation


def handle_unset(options):
    """Unset the setting value of ``<section> <key>``.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine;
             1 if the section and/or key does not exist;
             2 if the settings can't be loaded
    """
    try:
        settings = utils.load_settings(options)
    except Exception as error:
        tools.stderr(error)
        return 2

    section = options.section
    option = options.option

    # Make sure the section exists
    if not settings.parser.has_section(section):
        tools.stderr('Section "%s" does not exist' % section)
        return 1

    # Unset the option
    removed = settings.parser.remove_option(section, option)
    # Remove section completely if empty
    if len(settings.parser.options(section)) == 0:
        settings.parser.remove_section(section)
    # Save config file
    settings.save()
    # Report result
    if removed:
        print('Unset option "{}.{}"'.format(section, option))
    else:
        print('Option "{}.{}" was not set'.format(section, option))
    return 0  # successful operation


def main():
    """Console entry point for ``sopel-config``."""
    parser = build_parser()
    options = parser.parse_args()
    action = options.action

    if not action:
        parser.print_help()
        return

    # init command does not require existing settings
    if action == 'list':
        return handle_list(options)
    elif action == 'init':
        return handle_init(options)
    elif action == 'get':
        return handle_get(options)
    elif action == 'set':
        return handle_set(options)
    elif action == 'unset':
        return handle_unset(options)
