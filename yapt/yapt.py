#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Tools
"""

import argparse
import time
import threading
import os
import re
import sys
import humanize

__author__ = 'cdc'
__email__ = 'cdc@decumont.be'
__version__ = '0.0.1'

YAPT_Action_list = 'list'
YAPT_Action_ren2date = 'ren2date'
YAPT_Action_flatcp = 'flatcp'
YAPT_Action_optimize = 'optimize'
YAPT_Action_checknames = 'checknames'
YAPT_Action_correctnames = 'correctnames'

YAPT_Actions = (
    YAPT_Action_list,
    YAPT_Action_ren2date,
    YAPT_Action_flatcp,
    YAPT_Action_optimize,
    YAPT_Action_checknames,
    YAPT_Action_checknames,
    )

PIL_FORMATS = [
    'bmp', 'eps', 'gif', 'j2c', 'j2k', 'jp2', 'jpc', 'jpe', 'jpeg', 'jpf', 'jpg', 'jpx', 'mpo', 'pbm',
    'pcx', 'pgm', 'png', 'ppm', 'tga',
    ]

BORDER_Chars = '┌┐┘└─│┴├┬┤╷┼'


# ......................................................................................................................
class YaptError:
    def __init__(self, file, error):
        """
        Yqpt Error Class
        """
        self.file = file
        self.type = error.__class__.__name__ if isinstance(error, Exception) else 'YaptError'
        self.message = str(error)

    def __str__(self):
        return '%s [%s: %s]' % (self.file, self.type, self.message)


# ......................................................................................................................
class YaptClass(object):
    """
    Class to Execute wanted actions. Yes a class just to learn python class
    """

    def __init__(self, target: object = '', onlytest: bool = True, recursive: bool = True, threads: int = 5):
        self.target = target
        self.onlytest = onlytest
        self.recursive = recursive
        self.threads = threads if threads else 0

        # reset Counters
        self.files = []
        self.filesCount = 0
        self.filesSize = 0

    def resetCounters(self):
        self.files = []
        self.filesCount = 0
        self.filesSize = 0

    def printTitle(self, title: str) -> None:
        print(title)
        print('-' * 1 * (len(title)))

    def printActionStart(self, title: str) -> None:
        if self.onlytest:
            title += ' OnlyTest'
        title += ' %d File(s)' % self.filesCount
        print(title)
        print('-' * 1 * (len(title)))

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

    def processFiles(self, action: str) -> None:
        self.printActionStart(action)
        elapsed_time = time.time()
        actions = {
            YAPT_Action_list: self.listFile,
            YAPT_Action_ren2date: self.listFile,
            YAPT_Action_flatcp: self.listFile,
            YAPT_Action_optimize: self.listFile,
            YAPT_Action_checknames: self.checkFileName,
            YAPT_Action_correctnames: self.correctFileName,
            }
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

    def thread_processFiles(self, fct):
        while True:
            try:
                f = self.files.pop(0)
                fct(f)
            except IndexError:
                # Ok as expected . No items left
                break

    # ...................................................................................................................
    def listFile(self, file: str):
        print(file)
        pass

    # ...................................................................................................................
    def checkFileName(self, file: str):
        f = os.path.basename(file)
        ILLEGAL_NTFS_CHARS = "[<>:/\\|?*\"]|[\0-\31]"
        n = re.sub(ILLEGAL_NTFS_CHARS,'',f)

        # res = re.match('^\d{4}-\d{2}-\d{2} \d{2}h\d{2}', f)
        # if res:
        #     print(n, res)
        #     return
        res = re.search('(\d{4})-(\d{2})-(\d{2}) ', f)
        if res:
            print(file, res.groups())
        pass

    # ...................................................................................................................
    def correctFileName(self, file: str):
        f = os.path.basename(file)
        ILLEGAL_NTFS_CHARS = "[<>:/\\|?*\"]|[\0-\31]"
        res = re.match(ILLEGAL_NTFS_CHARS, f)
        if res:
            print(file, '  << ILLEGAL_NTFS_CHARS')
            return
        res = re.search('(\d{4})-(\d{2})-(\d{2}) ', f)
        if res:
            print(file, res.groups())
            return
        pass

        # else:
        #     print(file)
                # //            res = re.match('^\d{4}', f)
                # res
            # f = os.path.basename(file)
            # def __removeIllegalChars(name):
            #     # removes characters that are invalid for NTFS
            #     return re.sub(ILLEGAL_NTFS_CHARS, "", name)
            # 2016-07-09 19h29   >>>  20160708_1730
            # if '-' in f:
            #     print(self.source, f)
        pass

    def ren2date(self, file: str) -> None:
        print(self.source, file)

    def flatcp(self, file: str) -> None:
        print(self.source, file)

    def optimize(self, file: str) -> None:
        print(self.source, file)


def main():
    parser = argparse.ArgumentParser(
        prog="yapt.py",
        description=__doc__,
        epilog="\nbe carefull and good lock !\n",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80)
    )
    parser.add_argument('-y', '--onlytest', dest='onlytest', help='dry run', action='store_true')
    parser.add_argument('-r', '--recursive', dest='recursive', action='store_true', default=True, help='recursive scan subfolders')
    parser.add_argument('-x', '--threads', dest='threads', type=int, default=5, help='set threads count')
    parser.add_argument('-s', '--source', type=str, default='~/Images/', help='Root Dir to process')
    parser.add_argument('-t', '--target', type=str, default='~/Tempo/yapt', help='Destination Folder')
    parser.add_argument('-a', '--action', dest='action', choices=YAPT_Actions, default=YAPT_Action_checknames, help='action to perform')
    args = parser.parse_args()

    yatp = YaptClass(target=args.target, onlytest=args.onlytest, recursive=args.recursive, threads=args.threads)
    if not yatp.loadSource(args.source):
        print('ByeBye')
        exit(-1)
    yatp.processFiles(args.action)


if __name__ == "__main__":
    main()
