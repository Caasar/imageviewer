# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:49:52 2017

@author: Caasar
"""

KNOWN_ARCHIVES = set()

class WrapperIOError(IOError):
    pass

# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:50:02 2017

@author: Caasar
"""

import os
import re
#import htmllib,formatter
from six import text_type, next
#from six.moves import cStringIO as StringIO
import PIL.Image as Image
import PIL.ImageFile as ImageFile

Image.init()
ImageFile.MAXBLOCK = 2**25

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
        
        
class ArchiveIOError(IOError):
    pass

class BaseFileInfo(object):
    def __init__(self, filename):
        self.filename = filename

class BaseWrapper(object):
    formats = KNOWN_ARCHIVES
    
    @property
    def filelist(self):
        raise NotImplementedError()
    
    def open(self, fileinfo, mode):
        raise NotImplementedError()
    
    def close(self):
        raise NotImplementedError()
            
    def filter_file_extension(self,exts):
        """
        Return a filtered list of files.
        
        Parameters
        ----------
            exts : list or set containing the wanted file extensions.
        
        Returns
        ---------
            filelist : a list containing only filenames of the provided types.
        """
        filelist = []
        for zi  in self.filelist:
            name, ext = os.path.splitext(zi.filename)
            if ext.lower() in exts:
                filelist.append(zi)
                
        return filelist
                
    def filter_images(self):
        return self.filter_file_extension(Image.EXTENSION)

    def list_archives(self):
        folder, name = os.path.split(self.path)
        archlist = []
        index = 0
        if os.path.isdir(self.path):
            dirlist = os.listdir(folder)
            dirlist = sorted(dirlist,key=self.split_filename)
            for f in dirlist:
                fullpath = os.path.join(folder,f)
                if os.path.isdir(fullpath):
                    if f == name:
                        index = len(archlist)
                    archlist.append(fullpath)
        else:
            filelist = self.folderlist(folder,'',False)
            filelist = sorted(filelist,key=self.split_filename)
            for zi in filelist:
                base, ext = os.path.splitext(zi.filename)
                if ext.lower() in self.formats:
                    if zi.filename == name:
                        index = len(archlist)
                    fullpath = os.path.join(folder,zi.filename)
                    archlist.append(fullpath)
                
        return archlist,index
    
    @classmethod
    def folderlist(cls, path,base='',recursive=True):
        filelist = []
        try:
            dirlist = os.listdir(path)
        except:
            dirlist = []
            
        for f in dirlist:
            fullpath = os.path.join(path,f)
            filename = os.path.join(base,f)
            if os.path.isfile(fullpath):
                filelist.append(BaseFileInfo(filename))
            elif os.path.isdir(fullpath) and recursive:
                filelist.extend(cls.folderlist(fullpath,filename))
                
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
        
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.close()    
        
    def __contains__(self, filename):
        return filename in (fi.filename for fi in self.filelist)
