"""This module defines functions that will help you creating unique files."""
import os
import datetime
import random

try:
    import fcntl
except ImportError:
    fcntl = None


def flock(lockfilename):
    global fcntl
    if fcntl:
        lck = open(lockfilename, 'ab+')
        fcntl.flock(lck, fcntl.LOCK_EX)
        return lck
    else:
        while True:
            try:
                os.mkdir(lockfilename)
                break
            except IOError:
                time.sleep(0.1)
        return lockfilename


def funlock(lck):
    global fcntl
    if fcntl:
        fcntl.flock(lck, fcntl.LOCK_UN)
        lck.close()
    else:
        os.rmdir(lck)


def datestampname():
    """Returns a short name containing the current date and time.

    The returned string is similar to the iso 8601 format but it can be used as part of a filename."""
    return datetime.date.today().isoformat().replace(':', '_').replace('.', '_')


def timestampname():
    """Returns a short name containing the current date and time.

    The returned string is similar to the iso 8601 format but it can be used as part of a filename."""
    return datetime.datetime.now().isoformat().replace(':', '_').replace('.', '_')


def randomdigits():
    """Return a short name (4 characters) containing random numbers."""
    return str(random.randint(0, 10000)).rjust(4, '0')


def randomname():
    """Returns a name that will form a (probably) unique filename even if you add things to it.

    NOTE: This function is based on the current timestamp and some randomity, it is not too safe."""
    return timestampname() + "_" + randomdigits()


def uniquefile(directory, prefix='', basename=None, postfix='', mode='wb+'):
    """Returns an uniquely named file object.

    The main differences between this function and the standard tempfile.mkstemp function:

        1.  The file created by uniquefile is a regular file, it is visible to other processes.
        1.  Successive calls to uniquefile() will create files with ascending filenames (when sorted as strings).

    @param directory:  The directory name where the file should be created.
    @param prefix: This will be appended to the beginning of the filename.
    @param basename: This will be used for the middle part of the filename. When not given,  timestampname() will be used.
    @param postix: This will be appended to the end of the filename. (You will most probably place the extension here.)
    @param mode: mode parameter passed to file() when creating the file.

    @return: When 'directory' present, this function creates the given file and returns the opened file object.

    """
    directory = os.path.abspath(directory)
    lockfilename = os.path.join(directory, '.uniquename')
    lck = flock(lockfilename)
    try:
        basename = os.path.join(directory, prefix + timestampname())
        idx = 0
        while True:
            fpath = basename + '_' + str(idx).rjust(4, '0') + postfix
            if not os.path.isfile(fpath):
                fd = open(fpath, mode)
                return fd
            idx += 1
    finally:
        funlock(lck)


def uniquedir(directory, prefix='', basename=None, postfix=''):
    """Creates an uniquely named directory and returns its name.

    This function is similar to "uniquefile" except that it creates a directory instead of a file object,
    and returns a name instead of a file object.
    """
    directory = os.path.abspath(directory)
    lockfilename = os.path.join(directory, '.uniquename')
    lck = flock(lockfilename)
    try:
        basename = os.path.join(directory, prefix + timestampname())
        idx = 0
        while True:
            fpath = basename + '_' + str(idx).rjust(4, '0') + postfix
            if not os.path.isfile(fpath):
                os.mkdir(fpath)
                return fpath
            idx += 1
    finally:
        funlock(lck)


if __name__ == '__main__':
    print(datestampname())
    print(randomname())
    print(uniquefile('.', prefix='zeusd1_', postfix='.xml'))
    print(uniquedir('.', prefix='zeusd1_'))
