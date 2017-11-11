# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:55:52 2017

@author: Caasar
"""

from ctypes import cdll,c_char_p
from io import BytesIO
from six import text_type
from .base import WrapperIOError, BaseWrapper, KNOWN_ARCHIVES

try:
    LIBMUPDF = cdll.libmupdf
    KNOWN_ARCHIVES.add('.pdf')
except:
    pass

class PdfIOError(WrapperIOError):
    pass

class PdfImage(object):
    def __init__(self, objid):
        self.objid = objid
        self.filename = text_type(objid)
        
    def __hash__(self):
        return hash(self.objid)

class PdfWrapper(BaseWrapper):
    def __init__(self, path, minsize=5120, bufferlen=1048576):
        self.path = path
        self.minsize = minsize
        self.dll = LIBMUPDF
        self.dll.pdf_to_name.restype = c_char_p
        self.bufferlen = bufferlen
        try:
            self.context = self.dll.fz_new_context(None, None, 0)
        except:
            self.context = None

        if not self.context:
            raise PdfIOError('Could not build MuPDF context')

        try:
            self.doc = self.dll.pdf_open_document(self.context, path.encode())
        except:
            self.dll.fz_free_context(self.context)
            self.context = None
            self.doc = None

        if not self.doc:
            raise PdfIOError('Could not open "%s"' % path)
            
        cnt_obj = self.dll.pdf_count_objects(self.doc)
        filelist = []
        for cur in range(cnt_obj):
            obj = self.dll.pdf_load_object(self.doc, cur, 0)
            if self._isimage(obj):
                filelist.append(PdfImage(cur))
            self.dll.pdf_drop_obj(obj)
                
        self._filelist = filelist[::-1]
        
    @property
    def filelist(self):
        return self._filelist
        
    def filter_images(self):
        return self.filelist

    def close(self):
        self.dll.pdf_close_document(self.doc)
        self.dll.fz_free_context(self.context)
        
    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise PdfIOError('Child mode does not fit to mode of Archive')
        
        raw = ''
        stream = self.dll.pdf_open_raw_stream(self.doc,fileinfo.objid,0)
        buf = ' ' * self.bufferlen
        read = self.dll.fz_read(stream,buf,self.bufferlen)
        while read:
            raw += buf[:read]
            buf = ' ' * self.bufferlen
            read = self.dll.fz_read(stream,buf,self.bufferlen)

        return BytesIO(raw)

    def _isimage(self,obj):
        t = self.dll.pdf_dict_gets(obj, b"Subtype")
        if self.dll.pdf_is_name(t) and self.dll.pdf_to_name(t)== b"Image":
            t = self.dll.pdf_dict_gets(obj, b"Length")
            return self.dll.pdf_is_int(t) and self.dll.pdf_to_int(t)>self.minsize
        else:
            return False
        

