# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:50:02 2017

@author: Caasar
"""

import sys
import zipfile, os, re
from collections import namedtuple
from subprocess import run, CREATE_NO_WINDOW
from io import BytesIO
from six import text_type
from .base import WrapperIOError, BaseWrapper, KNOWN_ARCHIVES

KNOWN_ARCHIVES.update({'.zip','.cbz'})


class Handle7z(object):
    FileType = namedtuple('FileType', ('filename', ))
    re_row = re.compile(r'^\d+-\d+-\d+ \d+:\d+:\d+\s+\.\.\.\.A\s+\d+\s+\d+')
    filelist_cmd = '7z.exe', '-ba', 'l', '--'
    fileread_cmd = '7z.exe', '-so', 'e', '--'
    formats = {'.7z', '.ar', '.arj', '.bzip2', '.cab', '.chm', '.cpio',
               '.cramfs', '.dmg', '.ext', '.fat', '.gpt', '.gzip', '.hfs',
               '.ihex', '.iso', '.lzh', '.lzma', '.mbr', '.msi', '.nsis',
               '.ntfs', '.qcow2', '.rar', '.rpm', '.squashfs', '.tar',
               '.udf', '.uefi', '.vdi', '.vhd', '.vmdk', '.wim', '.xar',
               '.xz', '.z', '.zip', '.cbr'}

    def __init__(self, path, mode, encoding=None):
        if mode[0] != 'r':
            raise ArchiveIOError("Unsupported file mode '%s' for Handle7z" % mode)
        if encoding is None:
            encoding = sys.getfilesystemencoding()
        cmd = self.filelist_cmd + (path, )
        output = run(cmd, capture_output=True, encoding=encoding,
                     creationflags=CREATE_NO_WINDOW)
        if output.stderr:
            raise ArchiveIOError(output.stderr)
        filelist = []
        for row in output.stdout.split('\n'):
            m = self.re_row.match(row)
            if m is not None:
                cfn = row[m.end():].strip()
                filelist.append(self.FileType(cfn))
        self.path = path
        self._filelist = filelist
        self.encoding = encoding

    def read(self, fileinfo):
        cmd = self.fileread_cmd + (self.path, fileinfo.filename)
        output = run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
        err = output.stderr.decode(self.encoding)
        if err:
            raise ArchiveIOError(err)
        return output.stdout

    def close(self):
        pass

    @property
    def filelist(self):
        return list(self._filelist)

KNOWN_ARCHIVES.update(Handle7z.formats)


class ArchiveIOError(WrapperIOError):
    pass


class ArchiveIO(BytesIO):
    def __init__(self,fileinfo,mode,parent=None):
        if mode[0] == 'r':
            init = parent.handle.read(fileinfo)
        elif mode[0] == 'a':
            try:
                init = parent.handle.read(fileinfo)
            except KeyError:
                init = ''
        else:
            init = ''
        super().__init__(init)
        self._parent = parent
        self._mode = mode
        self._fileinfo = fileinfo
        self._opened = True

    def close(self):
        if self._opened and self._mode[0] in {'a','w'} and self._parent.handle:
            self._parent.handle.writestr(self._fileinfo,self.getvalue())
        self._opened = False
        super().close()


class ArchiveWrapper(BaseWrapper):
    def __init__(self, path, mode='r'):
        self.path = path
        self.mode = mode
        name, ext = os.path.splitext(path)
        if os.path.isdir(path):
            self.handle = None
        elif ext.lower() in {'.zip','.cbz'}:
            try:
                self.handle = zipfile.ZipFile(path,mode)
            except zipfile.BadZipfile as err:
                raise ArchiveIOError(text_type(err))
        elif ext.lower() in self.formats:
            self.handle = Handle7z(path,mode)
        else:
            raise ArchiveIOError('"%s" is not a supported archive' % path)

    @property
    def filelist(self):
        if self.handle is None and self.path:
            filelist = self.folderlist(self.path)
        elif isinstance(self.handle, (zipfile.ZipFile, Handle7z)):
            filelist = self.handle.filelist
        else:
            filelist = []

        return sorted(filelist,key=ArchiveWrapper.split_filename)

    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise ArchiveIOError('Child mode does not fit to mode of Archive')

        if self.handle:
            return ArchiveIO(fileinfo,mode,self)
        else:
            fullpath = os.path.join(self.path,fileinfo.filename)
            return open(fullpath,mode)

    def close(self):
        self.path = None
        self.mode = None
        if self.handle is not None:
            self.handle.close()

