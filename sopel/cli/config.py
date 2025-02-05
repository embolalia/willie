"""Sopel Config Command Line Interface (CLI): ``sopel-config``"""
from __future__ import annotations

import argparse
import os
import subprocess

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

    # sopel-config edit
    edit_parser = subparsers.add_parser(
        'edit',
        help='Open Sopel configuration file in your default text editor',
        description='Open Sopel configuration file in your default text editor')
    utils.add_common_arguments(edit_parser)

    # sopel-config get <section> <key>
    get_parser = subparsers.add_parser(
        'get',
        help="Get a configuration option's value",
        description="Get a configuration option's value",
    )
    get_parser.add_argument(
        'section',
        help='The name of the section to look in',
    )
    get_parser.add_argument(
        'option',
        help='The name of the option to retrieve',
    )
    utils.add_common_arguments(get_parser)

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

    found = False
    for config_filename in configs:
        found = True
        if display_path:
            print(os.path.join(configdir, config_filename))
        else:
            name, _ = os.path.splitext(config_filename)
            print(name)

    if not found:
        utils.stderr('No config file found at this location: %s' % configdir)
        utils.stderr('Use `sopel-config init` to create a new config file.')

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
        utils.stderr('Configuration wizard accepts .cfg files only')
        return 1
    elif not ext:
        config_filename = config_name + '.cfg'

    if os.path.isfile(config_filename):
        utils.stderr('Configuration file %s already exists' % config_filename)
        return 1

    print('Starting Sopel config wizard for: %s' % config_filename)
    try:
        utils.wizard(config_name)
    except KeyboardInterrupt:
        utils.stderr('\nOperation cancelled; no file has been created.')
        return 1  # cancelled operation

    return 0  # successful operation


def handle_edit(options):
    """Open the specified config file in the user's ``$EDITOR``.

    :param options: parsed arguments
    :type options: :class:`argparse.Namespace`
    :return: 0 if everything went fine;
             1 if the specified config file doesn't exist;
             2 if the user doesn't have a valid ``$EDITOR``
    """
    editor = os.environ.get('EDITOR', None)
    if editor is None:
        print('No $EDITOR found. Please configure your shell.')
        return 2

    config_filename = utils.find_config(options.configdir, options.config)
    if not os.path.isfile(config_filename):
        print('No config file found at {}'.format(config_filename))
        return 1

    subprocess.Popen([editor, config_filename])
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
        utils.stderr(error)
        return 2

    section = options.section
    option = options.option

    # Making sure the section.option exists
    if not settings.parser.has_section(section):
        utils.stderr('Section "%s" does not exist' % section)
        return 1
    if not settings.parser.has_option(section, option):
        utils.stderr(
            'Section "%s" does not have a "%s" option' % (section, option))
        return 1

    # Display the value
    print(settings.get(section, option))
    return 0  # successful operation


def main():
    """Console entry point for ``sopel-config``."""
    parser = build_parser()
    options = parser.parse_args()
    action = options.action

    if not action:
        parser.print_help()
        return

    try:
        # init command does not require existing settings
        if action == 'list':
            return handle_list(options)
        elif action == 'init':
            return handle_init(options)
        elif action == 'edit':
            return handle_edit(options)
        elif action == 'get':
            return handle_get(options)
    except KeyboardInterrupt:
        # ctrl+c was used, nothing to report here
        pass
