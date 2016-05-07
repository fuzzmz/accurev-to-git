#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import argparse
import tempfile
import subprocess
import xml.etree.ElementTree as ElemTree
import datetime
import os
import sys
import re
import getpass

# constants
GIT_MIGRATE_STREAM = 'git_migrate'
GIT_MIGRATE_WORKSPACE = 'git_migrate_work'


class FullPaths(argparse.Action):
    """Expand user- and relative-paths"""

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, os.path.abspath(os.path.expanduser(values)))


def is_stream(stream):
    """Check if stream is an AccuRev stream

    :param stream: string to be checked if an AccuRev stream
    :return: return the stream name
    :raise argparse.ArgumentTypeError: raise error if not AccuRev stream
    """
    accurevcheck = subprocess.call(['accurev', 'hist', '-t', 'now', '-s', stream], stderr=subprocess.STDOUT,
                                   stdout=open(os.devnull, 'w'))
    if accurevcheck:
        if accurevcheck == 52:
            msg = 'Expired or invalid AccuRev session token. Please enter your credentials.\n'
            print msg
            username = raw_input('AccuRev username: ')
            password = getpass.getpass()
            loggedin = accurev_login(username, password)
            if loggedin:
                return stream
            else:
                sys.exit('The username or password were incorrect.\nPlease manually log in to AccuRev and try again.')
        elif accurevcheck == 1:
            msg = '{0} is not an AccuRev stream'.format(stream)
            raise argparse.ArgumentTypeError(msg)
        else:
            msg = 'AccuRev error: {0}'.format(accurevcheck)
            raise argparse.ArgumentTypeError(msg)
    else:
        return stream


def is_used_dest(dirname, depot):
    """Check to see if the location is already associated with an AccuRev wksp different than the one used by
    the current migration workspace as this prevents creating new workspaces with that destination.

    :param dirname: folder to check if associated with existing AccuRev workspace
    :param depot: AccuRev depot
    """
    wkspfile = tempfile.gettempdir() + '/accWksp.xml'
    with open(wkspfile, 'w') as f:
        f.write(exec_cmd(['accurev', 'show', 'wspaces', '-fx']))
    tree = ElemTree.parse(wkspfile)
    root = tree.getroot()
    wksps = []
    for wksp in root.iter('Element'):
        wksps.append([wksp.attrib['Name'], wksp.attrib['Storage']])
    for wksp in wksps:
        if dirname.replace('\\', '/').lower() in wksp[1].lower():
            if (depot + '_' + GIT_MIGRATE_WORKSPACE).lower() in wksp[0].lower():
                break
            else:
                msg = 'ERROR: folder "{}" is already used by {} workspace\nChoose another destination folder'.format(
                    wksp[1], wksp[0])
                sys.exit(msg)


def is_valid_dest(dirname):
    """Checks if path is a valid destination (folder and git repo)

    :param dirname: folder to check if directory and git repo
    :return: return the folder path
    :raise argparse.ArgumentTypeError: raise error if not an actual folder
    """
    if not os.path.isdir(dirname):
        msg = '{0} is not a directory'.format(dirname)
        raise argparse.ArgumentTypeError(msg)
    return dirname


def get_history(branch):
    """Return all history of specified AccuRev branch

    :param branch: AccuRev branch for which history will be created
    :return: location of history xml file
    """
    print 'Reading AccuRev history...'
    logfile = tempfile.gettempdir() + '/accHist.xml'
    with open(logfile, 'w') as f:
        f.write(exec_cmd(['accurev', 'hist', '-a', '-s', branch, '-fx']))
    return logfile


def get_args():
    """Get CLI arguments and options

    :return: AccuRev branch, git repository location, append option boolean
    """
    parser = argparse.ArgumentParser(description='Migrate AccuRev branch history to git')
    parser.add_argument('accurevBranch', help='The AccuRev branch which will be migrated', type=is_stream)
    parser.add_argument('repoLocation', help='The location of the git repository in which the clone will happen',
                        action=FullPaths, type=is_valid_dest)
    parser.add_argument('-a', '--append', help='Append new AccuRev branch history to an existing git repository',
                        action='store_true')
    args = parser.parse_args()
    source = args.accurevBranch
    dest = args.repoLocation
    append = args.append
    return source, dest, append


def get_position(transactions, tr_id):
    """Returns the position in transaction list of the transaction corresponding to the given id

    :param transactions: a list of lists
    :param tr_id: transaction id for which the position needs to be determined
    :return: index of the transaction corresponding to trans_id
    """
    for item in transactions:
        if tr_id == item[0]:
            return transactions.index(item)


def sanitize_message(message):
    """Remove all characters which might break a commit message

    :param message: string containing the AccuRev promote message
    :return: the string without any non-ascii characters
    """
    if not message:
        message = 'empty AccuRev promote message'
    else:
        message = message.strip('"').lstrip('\n')
        # remove non-ascii characters
        message = ''.join(i for i in message if ord(i) < 128)
    return message


def exec_cmd(cmd, fail=True):
    """
    Execute shell command

    :param cmd: list containing command and its parameters
    :param fail: whether to fail with exit in case or command error or not
    :return: the command output or the command error if fail is False
    """
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return output
    except subprocess.CalledProcessError as exc:
        msg = 'ERROR: command "{}" failed with return code {} \nCommand output:\n{}'.format(' '.join(cmd),
                                                                                            exc.returncode, exc.output)
        if fail:
            sys.exit(msg)
        else:
            return msg


def accurev_login(username, password):
    """
    Login in accurev as accuBuild
    :param username: AccuRev username
    :param password: AccuRev password
    """
    loggedin = subprocess.call(['accurev', 'login', username, password])
    if loggedin == 0:
        return True
    else:
        return False


def accurev_init(depot, stream, destination):
    """
    Create stream and workspace for migration to Git
    :param depot: AccuRev depot name
    :param stream: AccuRev stream to migrate sources from
    :param destination: folder to migrate sources to
    """
    # create migration stream
    output = exec_cmd(['accurev', 'mkstream', '-s', depot + '_' + GIT_MIGRATE_STREAM, '-b', stream], fail=False)
    if 'already exists' in output:
        move = exec_cmd(['accurev', 'chstream', '-s', depot + '_' + GIT_MIGRATE_STREAM, '-b', stream], fail=False)
        if 'Unknown stream or ver spec' in move:
            sys.exit(move)
    # create migration workspace
    output = exec_cmd(
        ['accurev', 'mkws', '-w', depot + '_' + GIT_MIGRATE_WORKSPACE, '-b', depot + '_' + GIT_MIGRATE_STREAM, '-l',
         destination],
        fail=False)
    # if location already in use then move the workspace instead of creating it
    if 'Existing workspace/ref tree' or 'already exists' in output:
        move = exec_cmd(
            ['accurev', 'chws', '-w', depot + '_' + GIT_MIGRATE_WORKSPACE, '-l', destination, '-b',
             depot + '_' + GIT_MIGRATE_STREAM],
            fail=False)
        if 'ERROR:' in move:
            sys.exit(move)
    # ignore workspace already exists error
    elif 'ERROR:' in output and ('Existing workspace/ref tree' or 'already exists') not in output:
        sys.exit(output)


def git_init(destination):
    """
    Init git repository
    :param destination: git repository folder
    """
    os.chdir(destination)
    # create empty git repo
    exec_cmd(['git', 'init'])

    # config user and email that will appear in Git history as the committer
    exec_cmd(['git', 'config', 'user.name', 'Git migration script'])
    exec_cmd(['git', 'config', 'user.email', 'migration@git.accurev'])

    # create .gitignore file to exclude .accure vfufolder from git repo
    with open('.gitignore', 'w+') as f:
        f.write('.accurev')


def accurev_pop(depot, transaction_id):
    """
    Get accurev source tree based on a transaction id

    :param depot: AccuRev depot name
    :param transaction_id: transaction ID at which to perform the update
    """
    # move temporary stream to specified transaction
    print '[AccuRev] get transaction: {}...'.format(transaction_id)

    output = exec_cmd(['accurev', 'chstream', '-s', depot + '_' + GIT_MIGRATE_STREAM, '-t', transaction_id], fail=False)
    # check for network error and retry
    if 'ERROR:' in output:
        if 'network error' or 'Communications failure' in output:
            print 'Retry "accurev chstream" for transaction: {}'.format(transaction_id)
            exec_cmd(['accurev', 'update'])
        else:
            sys.exit(output)

            # perform update to retrieve changes (modified, new, deleted)
    output = exec_cmd(['accurev', 'update'], fail=False)
    # check for update failed due to some delayed file locks and retry
    if 'ERROR:' in output:
        if 'Some files could not be updated' or 'network error' or 'Communications failure' in output:
            print 'Retry "accurev update" for transaction: {}'.format(transaction_id)
            exec_cmd(['accurev', 'update'])
        else:
            sys.exit(output)


def git_commit(message, transaction_id, author, timestamp):
    """Add changes to index and commit them in Git

    :param message: git commit message
    :param transaction_id: AccuRev transaction ID
    :param author: AccuRev transaction author
    :param timestamp: timestamp at which the original AccuRev transaction was performed
    """

    # add all changes (modified, new, deleted) to Git index
    print '[Git] add changes to index...'
    exec_cmd(['git', 'add', '--all'])

    # temporary file used to format the commit message
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write('{} \n\n[AccuRev transaction: {}]'.format(message, transaction_id))

    print '[Git] commit changes...'
    output = exec_cmd(['git', 'commit', '--file={}'.format(f.name), '--author="AccuRev user {} <>"'.format(author),
                       '--date="{}"'.format(timestamp)], fail=False)
    # in case of error check if commit failed with 'nothing to commit' otherwise exit
    if 'ERROR:' in output:
        if 'nothing to commit' not in output:
            sys.exit(output)

    # remove temporary file
    os.remove(f.name)


def get_last_transaction_id():
    """Return the AccuRev transaction number associated to the latest git commit

    :return: last AccuRev transaction ID stored in the git repository
    """
    print 'Searching last migrated AccuRev transaction in Git commit logs...'
    log = exec_cmd(['git', 'log', '-1'])
    match = re.search(r'\[AccuRev transaction: (\d+)\]', log)
    count = 1
    while not match:
        log = exec_cmd(['git', 'log', 'HEAD~{}'.format(count), '-1'])
        match = re.search(r'\[AccuRev transaction: (\d+)\]', log)
        count += 1
        if count > 100:
            raise StandardError('ERROR: Unable to find AccuRev transaction in recent Git commit history')

    print 'Last migrated AccuRev transaction found: {}'.format(match.group(1))
    return match.group(1)


def pop_and_add(depot, transaction):
    """Get sources from AccuRev and commit them in git

    :param depot: AccuRev depot name
    :param transaction: AccuRev transaction used to retrieve the sources
    """
    tr_id = transaction[0]
    message = transaction[1]
    author = transaction[2]
    timestamp = datetime.datetime.fromtimestamp(int(transaction[3])).strftime('%Y-%m-%d %H:%M:%S')
    commit_msg = sanitize_message(message)

    # get sources corresponding to a transaction id
    accurev_pop(depot, tr_id)

    # commit changes to Git
    git_commit(commit_msg, tr_id, author, timestamp)


def get_depot(stream):
    """Get the depot name based on the AccuRev stream to be migrated

    :param stream: AccuRev stream to be migrated
    return: AccuRev depot associated with the stream
    """
    tomatch = str(stream).split('_')[0]
    depotfile = tempfile.gettempdir() + '/depotList.xml'
    with open(depotfile, 'w') as f:
        f.write(exec_cmd(['accurev', 'show', 'depots', '-fx']))
    tree = ElemTree.parse(depotfile)
    root = tree.getroot()
    depots = []
    for depot in root.iter('Element'):
        depots.append(depot.attrib['Name'])
    for depot in depots:
        if tomatch.lower() in depot.lower():
            return depot
    msg = 'ERROR: depot "{}" is not accessible by this user.'.format(tomatch)
    sys.exit(msg)


def git_migrate(logfile, stream, destination, append, depot):
    """Populate files from AccuRev based on history and commit them in git

    :param logfile: XML file containing the history of an AccuRev stream
    :param stream: AccuRev stream to be migrated
    :param destination: location of the git repository
    :param append: add only changes not already in git repository if prior migration was performed
    :param depot: AccuRev depot name
    """
    tree = ElemTree.parse(logfile)
    root = tree.getroot()
    transactions = []
    for transaction in root.iter('transaction'):
        if transaction[0].text:
            transactions.append(
                [transaction.attrib['id'], transaction[0].text, transaction.attrib['user'], transaction.attrib['time']])
    # accurev history is generated starting from the latest transaction so we need to reverse it
    transactions.reverse()

    # prepare for migration
    os.chdir(destination)
    if not append:
        print 'Prepare for migration...'
        accurev_init(depot, stream, destination)
        git_init(destination)

        # initial populate to get sources inherited from the parent streams
        print 'Perform first time AccuRev populate...'
        first_tr_id = transactions[0][0]
        exec_cmd(['accurev', 'chstream', '-s', depot + '_' + GIT_MIGRATE_STREAM, '-t', first_tr_id])
        exec_cmd(['accurev', 'pop', '-O', '-R', '-t', 'now', '.'])

    else:
        print 'Resume migration...'
        last_tr_id = get_last_transaction_id()
        position = get_position(transactions, last_tr_id)
        transactions = transactions[position + 1:]

    print 'Migrate AccuRev transactions...'
    for item in transactions:
        pop_and_add(depot, item)

    print 'Migration completed successfully.'


def main():
    """
    Script main function
    """
    args = get_args()
    # try and get the depot from the stream name (separate by first underscore)
    depot = get_depot(args[0])
    is_used_dest(args[1], depot)
    logfile = get_history(args[0])
    git_migrate(logfile, args[0], args[1], args[2], depot)


if __name__ == '__main__':
    main()
