# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:50:02 2017

@author: Caasar
"""

import zipfile,os,re,time
#import htmllib,formatter
from io import BytesIO
from six import text_type, next
from .base import WrapperIOError, BaseWrapper, KNOWN_ARCHIVES
#from six.moves import cStringIO as StringIO

KNOWN_ARCHIVES.update({'.zip','.cbz'})

try:
    import rarfile
    KNOWN_ARCHIVES.update({'.rar','.cbr'})
except ImportError:
    pass

def pull(*args):
    """
    Returns an iterator which takes interleaved elements from the provided
    iterators
    """
    iters = [iter(e) for e in args]
    niters = []
    while iters:
        for cur in iters:
            try:
                yield next(cur)
                niters.append(cur)
            except StopIteration:
                pass
            
        iters = niters
        niters = []
        
        
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
            
        BytesIO.__init__(self,init)
        self._parent = parent
        self._mode = mode
        self._fileinfo = fileinfo
        self._opened = True
        
    def close(self):
        if self._opened and self._mode[0] in {'a','w'} and self._parent.handle:
            self._parent.handle.writestr(self._fileinfo,self.getvalue())
            
        self._opened = False
        BytesIO.close(self)

    def __exit__(self, type, value, traceback):
        BytesIO.__exit__(self, type, value, traceback)


class ArchiveWrapper(BaseWrapper):
    def __init__(self, path, mode='r'):
        self.path = path
        self.mode = mode
        name, ext = os.path.splitext(path)
        if ext.lower() in {'.zip','.cbz'}:
            try:
                self.handle = zipfile.ZipFile(path,mode)
            except zipfile.BadZipfile as err:
                raise ArchiveIOError(text_type(err))
        elif ext.lower() in {'.rar','.cbr'} and '.rar' in self.formats:
            try:
                self.handle = rarfile.RarFile(path,mode)
            except rarfile.BadRarFile as err:
                raise ArchiveIOError(text_type(err))
            except rarfile.RarCannotExec as err:
                raise ArchiveIOError(text_type(err))
            except rarfile.NotRarFile as err:
                raise ArchiveIOError(text_type(err))
            except TypeError as err:
                raise ArchiveIOError(text_type(err))
        elif os.path.isdir(path):
            self.handle = None
        else:
            raise ArchiveIOError('"%s" is not a supported archive' % path)
        
    @property
    def filelist(self):
        if self.handle is None and self.path:
            filelist = self.folderlist(self.path)
        elif isinstance(self.handle, zipfile.ZipFile):
            filelist = self.handle.filelist
        elif isinstance(self.handle, rarfile.RarFile):
            filelist = self.handle.infolist()
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
            
    
    @staticmethod
    def folderlist(path,base='',recursive=True):
        filelist = []
        try:
            dirlist = os.listdir(path)
        except:
            dirlist = []
            
        for f in dirlist:
            fullpath = os.path.join(path,f)
            filename = os.path.join(base,f)
            if os.path.isfile(fullpath):
                date_time = time.gmtime(os.path.getmtime(fullpath))
                date_time = (date_time.tm_year, date_time.tm_mon, 
                             date_time.tm_mday, date_time.tm_hour, 
                             date_time.tm_min, date_time.tm_sec)
                filelist.append(zipfile.ZipInfo(filename,date_time))
            elif os.path.isdir(fullpath) and recursive:
                filelist.extend(ArchiveWrapper.folderlist(fullpath,filename))
                
        return filelist

    @staticmethod        
    def split_filename(fileinfo):
        """
        splits the given filename into a tuple of strings and number to allow
        for a simple alphanumber sorting.
        """
        isnumber = re.compile(r'\d+')
        if hasattr(fileinfo,'filename'):
            filename = fileinfo.filename
        else:
            filename = text_type(fileinfo)
        text = isnumber.split(filename)
        numbers = isnumber.findall(filename)
        return tuple(pull((t.lower() for t in text),(int(n) for n in numbers)))
        