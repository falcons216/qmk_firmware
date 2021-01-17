"""Format C code according to QMK's style.
"""
import json
import subprocess
from argparse import SUPPRESS
from os import environ, path
from pathlib import Path
from shutil import which

from milc import cli

from qmk.path import normpath
from qmk.c_parse import c_source_files

c_file_suffixes = ('c', 'h', 'cpp')
core_dirs = ('drivers', 'quantum', 'tests', 'tmk_core', 'platforms')
ignored = ('tmk_core/protocol/usb_hid', 'quantum/template', 'platforms/chibios')


def find_clang_format():
    """Returns the path to clang-format.
    """
    for clang_version in [7, 8, 9, 10]:
        binary = f'clang-format-{clang_version}'

        if which(binary):
            return binary

    return 'clang-format'


def find_diffs(files):
    """Run clang-format and diff it against a file.
    """
    found_diffs = False

    for file in files:
        cli.log.debug('Checking for changes in %s', file)
        clang_format = subprocess.Popen([find_clang_format(), file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        diff = cli.run(['diff', '-u', f'--label=a/{file}', f'--label=b/{file}', str(file), '-'], stdin=clang_format.stdout, capture_output=True)

        if diff.returncode != 0:
            print(diff.stdout)
            found_diffs = True

    return found_diffs


def cformat_run(files):
    """Spawn clang-format subprocess with proper arguments
    """
    # Determine which version of clang-format to use
    clang_format = [find_clang_format(), '-i']

    try:
        cli.run(clang_format + map(str, files), check=True, capture_output=False)
        cli.log.info('Successfully formatted the C code.')
        return True

    except subprocess.CalledProcessError as e:
        cli.log.error('Error formatting C code!')
        cli.log.debug('%s exited with returncode %s', e.cmd, e.returncode)
        cli.log.debug('STDOUT:')
        cli.log.debug(e.stdout)
        cli.log.debug('STDERR:')
        cli.log.debug(e.stderr)
        return False


@cli.argument('--ci', arg_only=True, action='store_true', help=SUPPRESS)
@cli.argument('-n', '--dry-run', arg_only=True, action='store_true', help="Flag only, don't automatically format.")
@cli.argument('-b', '--base-branch', default='origin/master', help='Branch to compare to diffs to.')
@cli.argument('-a', '--all-files', arg_only=True, action='store_true', help='Format all core files.')
@cli.argument('files', nargs='*', arg_only=True, type=normpath, help='Filename(s) to format.')
@cli.subcommand("Format C code according to QMK's style.", hidden=False if cli.config.user.developer else True)
def cformat(cli):
    """Format C code according to QMK's style.
    """
    # Find the list of files to format
    if cli.args.ci:
        if cli.args.files or cli.args.all_files:
            cli.log.warning('Filename or -a passed with --ci, only formatting CI files.')

        files_json = Path(environ.get('HOME', '~'), 'files.json').resolve()
        all_changed_files = json.load(files_json.open())
        files = [file for file in all_changed_files if file.split('.')[-1] in c_file_suffixes]

        if not files:
            cli.log.info('No C files in changeset: %s', ', '.join(all_changed_files))
            exit(0)

    elif cli.args.files:
        files = cli.args.files

        if cli.args.all_files:
            cli.log.warning('Filenames passed with -a, only formatting: %s', ','.join(map(str, files)))

    elif cli.args.all_files:
        all_files = c_source_files(core_dirs)
        # The following statement checks each file to see if the file path is in the ignored directories.
        files = [file for file in all_files if not any(i in str(file) for i in ignored)]

    else:
        git_diff_cmd = ['git', 'diff', '--name-only', cli.args.base_branch, *core_dirs]
        git_diff = cli.run(git_diff_cmd)

        if git_diff.returncode != 0:
            cli.log.error("Error running %s", git_diff_cmd)
            print(git_diff.stderr)
            return git_diff.returncode

        files = []

        for file in git_diff.stdout.strip().split('\n'):
            if not any([file.startswith(ignore) for ignore in ignored]):
                if path.exists(file) and file.split('.')[-1] in c_file_suffixes:
                    files.append(file)

    # Sanity check
    if not files:
        cli.log.error('No changed files detected. Use "qmk cformat -a" to format all files')
        return False

    # Run clang-format on the files we've found
    if cli.args.dry_run:
        return not find_diffs(files)
    else:
        return cformat_run(files)
