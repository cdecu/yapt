#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Tools
"""

import argparse
import shutil
import time
import threading
import os
import re
import sys
import humanize
from PIL import Image

__author__ = 'cdc'
__email__ = 'cdc@decumont.be'
__version__ = '0.0.1'

YAPT_Action_count = 'count'
YAPT_Action_list = 'list'
YAPT_Action_ren2date = 'ren2date'
YAPT_Action_flatcp = 'flatcp'
YAPT_Action_optimize = 'optimize'
YAPT_Action_checknames = 'checknames'
YAPT_Action_correctnames = 'correctnames'
YAPT_Action_thumbnails = 'thumbnails'

YAPT_Actions = (
    YAPT_Action_list,
    YAPT_Action_ren2date,
    YAPT_Action_flatcp,
    YAPT_Action_optimize,
    YAPT_Action_checknames,
    YAPT_Action_correctnames,
    YAPT_Action_thumbnails,
)

PIL_FORMATS = [
    'bmp', 'eps', 'gif', 'j2c', 'j2k', 'jp2', 'jpc', 'jpe', 'jpeg', 'jpf', 'jpg', 'jpx', 'mpo', 'pbm',
    'pcx', 'pgm', 'png', 'ppm', 'tga',
]

BORDER_Chars = '┌┐┘└─│┴├┬┤╷┼'

ILLEGAL_NTFS_CHARS = "[<>:/\\|?*\"]|[\0-\31]"


# ......................................................................................................................
class YaptError:
    """
    Class to store error
    """
    def __init__(self, file, error):
        """
        Yqpt Error Class
        """
        self.file = file
        self.type = error.__class__.__name__ if isinstance(error, Exception) else 'YaptError'
        self.message = str(error)

    def __str__(self):
        return '%s [%s: %s]' % (self.file, self.type, self.message)


def decode(path: str) -> str:
    """
    utility fct to encode/decode
    """
    return path.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)


# ......................................................................................................................
class YaptClass(object):
    """
    Class to Execute wanted actions. Yes a class just to learn python class
    """

    def __init__(self, target: str = '', onlytest: bool = True, recursive: bool = True, threads: int = 5):
        self.target = target
        self.onlytest = onlytest
        self.recursive = recursive
        self.threads = threads if threads else 0

        # Prepare regex
        self.validNTFSCharsRegEx = re.compile(ILLEGAL_NTFS_CHARS)
        self.yyymmddRegEx = re.compile('(\d{4})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})[-_ ]*(.*)')

        # default thumbnailSize (width, height)
        self.thumbnailSize = (800, 600,)

        # reset Counters
        self.files = []
        self.filesCount = 0
        self.filesSize = 0
        self.success = []
        self.errors = []
        self.fileRenamed = 0
        self.fileDeleted = 0
        self.newfilesCount = 0
        self.newfilesSize = 0

    # ..................................................................................................................
    def resetCounters(self):
        self.files = []
        self.filesCount = 0
        self.filesSize = 0
        self.success = []
        self.errors = []
        self.fileRenamed = 0
        self.fileDeleted = 0
        self.newfilesCount = 0
        self.newfilesSize = 0

    def printTitle(self, title: str) -> None:
        print(title)
        print('-' * 1 * (len(title)))

    def printActionStart(self, action: str) -> None:
        title = action
        if self.onlytest:
            title += ' OnlyTest'
        title += ' %d File(s)' % self.filesCount
        print(title)
        print('-' * 1 * (len(title)))

    def printActionEnd(self, action: str):
        if self.errors:
            print('\n%s Errors:' % action)
            for e in self.errors:
                print('\t' + decode(str(e)))

        if self.success:
            print('\n%s Success:' % action)
            for s in self.success:
                print('\t' + decode(s))

        print('\nResult\n------')
        print('- File(s) : %d Size %s' % (self.newfilesCount, humanize.naturalsize(self.newfilesSize)))
        if self.fileRenamed:
            print('- Renamed : %d' % self.fileRenamed)
        if self.fileDeleted:
            print('- Deleted : %d' % self.fileDeleted)
        print()

    def noCheck(self, action: str) -> None:
        pass

    def checkTarget(self, action: str) -> None:
        if not self.target:
            raise ValueError('Please select a valid target')

        if os.path.exists(self.target):
            if not os.path.isdir(self.target):
                raise ValueError('Please select a valid target dir')
        else:
            os.mkdir(self.target)

        errs = os.path.join(self.target, 'errors')
        if not os.path.exists(errs):
            os.mkdir(errs)

        pass

    def getCorrectFileName(self, file: str) -> str:
        # 20160712_1600_IMG_1692.jpg
        res = self.yyymmddRegEx.search(file)
        if res:
            p = res.group(1) + res.group(2) + res.group(3) + '_' + res.group(4) + res.group(5)
            s = res.group(6)
            s = re.sub(p, '', s)
            n = p + '_' + s
        else:
            n = file
        n = self.validNTFSCharsRegEx.sub('_', n)
        return n

    # ..................................................................................................................
    def loadSource(self, source: str) -> bool:
        self.printTitle('loading %s ...' % source)
        elapsed_time = time.time()
        self.resetCounters()
        if source:
            if os.path.exists(source):
                if os.path.isfile(source):
                    self.files.append(source)
                elif os.path.isdir(source):
                    if self.recursive:
                        for r, d, f in os.walk(source):
                            for file in f:
                                name, ext = os.path.splitext(file)
                                if ext and ext.lower()[1:] in PIL_FORMATS:
                                    ff = os.path.join(r, file)
                                    self.filesSize += os.path.getsize(ff)
                                    self.files.append(ff)
                                    self.filesCount += 1
                    else:
                        for file in os.listdir(source):
                            name, ext = os.path.splitext(file)
                            if ext and ext.lower()[1:] in PIL_FORMATS:
                                ff = os.path.join(source, file)
                                self.filesSize += os.path.getsize(ff)
                                self.files.append(ff)
                                self.filesCount += 1
            else:
                print('Error: Path %s not exists!' % source, file=sys.stderr)
                exit(-1)

        if not self.files:
            print('Error: No images found', file=sys.stderr)
            exit(-1)

        print('%d files %s' % (self.filesCount, humanize.naturalsize(self.filesSize)))
        elapsed_time = time.time() - elapsed_time
        print('in %.3f sec\n' % elapsed_time)
        return True

    # ..................................................................................................................
    def processFiles(self, action: str) -> None:
        self.printActionStart(action)
        elapsed_time = time.time()
        before_action = {
            YAPT_Action_count: self.checkTarget,
            YAPT_Action_list: self.checkTarget,
            YAPT_Action_ren2date: self.checkTarget,
            YAPT_Action_optimize: self.checkTarget,
            YAPT_Action_checknames: self.checkTarget,
            YAPT_Action_correctnames: self.checkTarget,
            YAPT_Action_flatcp: self.checkTarget,
            YAPT_Action_thumbnails: self.checkTarget,
        }
        actions = {
            YAPT_Action_count: self.countFile,
            YAPT_Action_list: self.listFile,
            YAPT_Action_ren2date: self.ren2date,
            YAPT_Action_optimize: self.listFile,
            YAPT_Action_checknames: self.checkFileName,
            YAPT_Action_correctnames: self.correctFileName,
            YAPT_Action_flatcp: self.flatcp,
            YAPT_Action_thumbnails: self.createThumbnail,
        }
        self.newfilesCount = self.filesCount
        self.newfilesSize = self.filesSize
        before_action[action](action)
        fct = actions[action]
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(fct,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(fct)
        elapsed_time = time.time() - elapsed_time
        print('in %.3f sec\n' % elapsed_time)
        self.printActionEnd(action)
        pass

    def thread_processFiles(self, fct):
        while True:
            try:
                f = self.files.pop(0)
                fct(f)
            except IndexError:
                # Ok as expected . No items left
                break
        pass

    # ...................................................................................................................
    def countFile(self, file: str):
        pass

    # ...................................................................................................................
    def listFile(self, file: str):
        self.success.append(file)
        pass

    # ...................................................................................................................
    def checkFileName(self, file: str):
        f = os.path.basename(file)
        n = self.getCorrectFileName(f)
        if n != f:
            self.errors.append(YaptError(file, 'should be renamed to ' + n))
        pass

    # ...................................................................................................................
    def correctFileName(self, file: str):
        d = os.path.dirname(file)
        f = os.path.basename(file)
        n = self.getCorrectFileName(f)
        if n != f:
            n = os.path.join(d, n)
            if os.path.exists(n):
                # Delete Duplicate !
                try:
                    if not self.onlytest:
                        os.remove(file)
                        self.success.append('%s >> Deleted' % file)
                    else:
                        self.success.append('%s >> to be deleted' % file)
                    self.fileDeleted += 1
                    pass
                except IOError as Err:
                    self.errors.append(YaptError(file, 'Delete I/O error({0}): {1}' % (Err.errno, Err.strerror)))
            else:
                # Rename to yyyymm...
                try:
                    if not self.onlytest:
                        os.rename(file, n)
                        self.success.append('%s >> Renamed' % file)
                    else:
                        self.success.append('%s >> to be renamed' % file)
                    self.newfilesSize += os.path.getsize(n)
                    self.newfilesCount += 1
                    self.fileRenamed += 1
                except IOError as Err:
                    self.errors.append(YaptError(file, 'Rename I/O error({0}): {1}' % (Err.errno, Err.strerror)))
        else:
            self.newfilesSize += os.path.getsize(file)
            self.newfilesCount += 1
        pass

    # ...................................................................................................................
    def ren2date(self, file: str) -> None:
        f = os.path.basename(file)
        res = self.yyymmddRegEx.search(f)
        if not res:
            self.errors.append(YaptError(file, 'should be renamed'))
        pass

    # ...................................................................................................................
    def flatcp(self, file: str) -> None:
        f = os.path.basename(file)
        n = os.path.join(self.target, f)
        try:
            with Image.open(file) as img:
                img.save(n, optimize=True)
            self.newfilesSize -= os.path.getsize(file)
            self.newfilesSize += os.path.getsize(n)
        except Exception as ex:
            self.errors.append(YaptError(file, ex))

    # ...................................................................................................................
    def createThumbnail(self, file: str) -> None:
        f = os.path.basename(file)
        n = os.path.join(self.target, f)
        try:
            with Image.open(file) as img:
                if (img.width > self.thumbnailSize[0]) or (img.height > self.thumbnailSize[1]):
                    # Resize
                    img_format = img.format
                    newimg = img.copy()
                    newimg.thumbnail(self.thumbnailSize, Image.LANCZOS)
                    newimg.format = img_format
                    newimg.save(n, optimize=True)
                else:
                    # keep as is
                    img.save(n, optimize=True)
            self.newfilesSize -= os.path.getsize(file)
            self.newfilesSize += os.path.getsize(n)
        except Exception as ex:
            self.errors.append(YaptError(file, ex))
            n = os.path.join(self.target, 'errors', f)
            shutil.copy(file, n)
            self.newfilesCount -= 1


# ......................................................................................................................
def main():
    parser = argparse.ArgumentParser(
        prog="yapt.py",
        description=__doc__,
        epilog="\nbe carefull and good lock !\n",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80)
    )
    parser.add_argument('-y', '--onlytest', dest='onlytest', help='dry run', action='store_true')
    parser.add_argument('-r', '--recursive', dest='recursive', action='store_true', default=True,
                        help='recursive scan subfolders')
    parser.add_argument('-x', '--threads', dest='threads', type=int, default=5, help='set threads count')
    parser.add_argument('-s', '--source', type=str, default='/home/cdc/Images/', help='Root Dir to process')
    parser.add_argument('-t', '--target', type=str, default='/home/cdc/yapt', help='Destination Folder')
    parser.add_argument('-a', '--action', dest='action', choices=YAPT_Actions, default=YAPT_Action_count,
                        help='action to perform')
    args = parser.parse_args()

    yatp = YaptClass(target=args.target, onlytest=args.onlytest, recursive=args.recursive, threads=args.threads)
    if not yatp.loadSource(args.source):
        print('ByeBye')
        exit(-1)
    yatp.processFiles(args.action)


if __name__ == "__main__":
    main()
