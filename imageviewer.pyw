#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division

import sys

try: 
    import PySide
    sys.modules['PyQt4'] = PySide # HACK for ImageQt
    from PySide import QtCore, QtGui
except ImportError:
    from PyQt4 import QtCore, QtGui
    QtCore.Signal = QtCore.pyqtSignal
    
import zipfile,os,re,time,gzip,cgi
#import htmllib,formatter
from ctypes import cdll,c_char_p
from io import BytesIO
from six import text_type, itervalues, iteritems, next, b
from six.moves.html_parser import HTMLParser, HTMLParseError
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError, URLError
from six.moves.BaseHTTPServer import BaseHTTPRequestHandler
from six.moves.urllib.parse import urlparse, ParseResult
#from six.moves import cStringIO as StringIO
import PIL.Image as Image
import PIL.ImageQt as ImageQt

KNOWN_ARCHIVES = {'.zip'}

try:
    import rarfile
    KNOWN_ARCHIVES.add('.rar')
except ImportError:
    pass
    
try:
    LIBMUPDF = cdll.libmupdf
    KNOWN_ARCHIVES.add('.pdf')
except:
    pass
    
Image.init()

INF_POINT = 100000
 
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
        
    def close(self):
        if self._mode[0] in {'a','w'} and self._parent.handle:
            self._parent.handle.writestr(self._fileinfo,self.getvalue())
            
        BytesIO.close(self)

    def __exit__(self, type, value, traceback):
        if type is None and self._mode[0] in {'a','w'} and self._parent.handle:
            self._parent.handle.writestr(self._fileinfo,self.getvalue())
        BytesIO.__exit__(self, type, value, traceback)

class WebIOError(ArchiveIOError):
    pass

class WebIO(BytesIO):
    re_charset = re.compile(r'charset=([\w-]+)')
    
    def __init__(self,url,data=None):
        request = Request(url)
        request.add_header('Accept-encoding', 'gzip')
        if data:
            request.add_data(data)
        
        try:
            response  = urlopen(request)
            if response.headers.get('Content-Encoding',''):
                zipped = BytesIO(response.read())
                with gzip.GzipFile(fileobj=zipped) as gzip_handle:
                    raw = gzip_handle.read()
            else:
                raw = response.read()

            m = self.re_charset.search(response.headers.get('Content-Type',''))
            if m:
                self.charset = m.group(1)
            else:
                self.charset = 'utf8'
                
            response.close()
            
        except HTTPError as err:
            if not str(err):
                dummy, msg = BaseHTTPRequestHandler.responses[err.code]
                msg = '%d - %s' % (err.code, msg)
                raise WebIOError(msg)
            else:
                raise WebIOError(str(err))
        except URLError as err:
            raise WebIOError(str(err))
        except ValueError as err:
            raise WebIOError(str(err))

        BytesIO.__init__(self,raw)
        

class WebImage(object):
    def __init__(self,image_url,page_url,next_page=''):
        dummy, filename = os.path.split(image_url)
        self.image_url = image_url
        self.page_url = page_url
        self.next_page = next_page
        self.filename = filename or image_url
        
    def __hash__(self):
        return hash(self.image_url)
        
class ImageParser(HTMLParser):
    filtered = {'.gif'}
    minlength = 50000
    
    def __init__(self,url):
        HTMLParser.__init__(self)
        self.saved_link = None
        self.imgs_lists = [list() for dummy in range(8)]
                           
        purl = list(urlparse(url)[:3])
        purl[2] = '/'.join(p for p in purl[2].split('/')[:-1] if p)
        if purl[2]:
            self.base_url = '%s://%s/%s/' % tuple(purl)
        else:
            self.base_url = '%s://%s/' % (purl[0],purl[1])
        self.base_netloc = purl[1]
        self.page_url = url
        
        with WebIO(url) as furl:
            try:
                self.feed(furl.read().decode(furl.charset))
            except HTMLParseError as err:
                WebIOError(str(err))
                
    def handle_starttag(self,tag,attrs):
        if tag == 'a':
            self.start_a(attrs)
        elif tag == 'img':
            self.do_img(attrs)

    def handle_endtag(self,tag):
        if tag == 'a':
            self.end_a()
            
    def start_a(self,info=None):
        elements = dict(info)
        try:
            purl = urlparse(elements['href'])
            if purl.netloc == self.base_netloc:
                self.saved_link = elements['href']
            elif not purl.netloc and not purl.path:
                ourl = urlparse(self.page_url)
                nurl = ParseResult(*(ourl[:3]+purl[3:]))
                self.saved_link = nurl.geturl()
            elif not purl.netloc:
                self.saved_link = self.base_url+elements['href']
                
            if self.saved_link == self.page_url:
                self.saved_link = None
        except KeyError:
            pass
        
    def end_a(self):
        self.saved_link = None
        
    def do_img(self,info):
        elements = dict(info)
        if 'src' in elements:
            src = elements['src']
            purl = urlparse(elements['src'])
            if not purl.netloc:
                src = self.base_url+src.lstrip('/')
                
            name, ext = os.path.splitext(purl.path)
            filtered = ext.lower() in self.filtered
            unknown_ext = ext.lower() not in Image.EXTENSION
            priority = unknown_ext*4 + (not self.saved_link)*2 + filtered
            self.imgs_lists[priority].append((src,self.saved_link))

    def find_image(self):
        image_url = None
        maxsize = -1
        
        for img_list in self.imgs_lists:
            for c_url, c_next in img_list:
                c_size = int(ImageParser.get_content_length(c_url))
                if maxsize < c_size:
                    image_url, next_page = c_url, c_next
                    maxsize = c_size
                
            if maxsize > self.minlength:
                break
            
        if image_url is None:
            raise WebIOError('No Image found at "%s"' % self.page_url)
            
        return WebImage(image_url,self.page_url,next_page)
        
    @staticmethod
    def get_content_length(url):
        request = Request(url)
        request.get_method = lambda: "HEAD"
        try:
            response = urlopen(request)
            length = response.headers.get("content-length",0)
            response.close()
        except HTTPError:
            length = 0
        except ValueError:
            length = 0
            
        return length

class ArchiveWrapper(object):
    isnumber = re.compile(r'\d+')
    formats = KNOWN_ARCHIVES
    
    def __init__(self,path,mode):
        self.path = path
        self.mode = mode
        name, ext = os.path.splitext(path)
        if ext.lower() == '.zip':
            try:
                self.handle = zipfile.ZipFile(path,mode)
            except zipfile.BadZipfile as err:
                raise ArchiveIOError(str(err))
            self.filelist = self.handle.filelist
        elif ext.lower() == '.rar' and '.rar' in self.formats:
            try:
                self.handle = rarfile.RarFile(path,mode)
                self.filelist = self.handle.infolist()
                if self.filelist:
                    # test if unrar works, i.e. can find unrar in path
                    with self.handle.open(self.filelist[0]):
                        pass
            except rarfile.BadRarFile as err:
                raise ArchiveIOError(str(err))
            except rarfile.RarCannotExec as err:
                raise ArchiveIOError(str(err))
        elif os.path.isdir(path):
            self.handle = None
            self.filelist = self.folderlist(path)
        else:
            raise ArchiveIOError('"%s" is not a supported archive' % path)
        
        self.filelist = sorted(self.filelist,key=ArchiveWrapper.split_filename)
    
    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise ArchiveIOError('Child mode does not fit to mode of Archive')
            
        if self.handle:
            return ArchiveIO(fileinfo,mode,self)
        else:
            fullpath = os.path.join(self.path,fileinfo.filename)
            return open(fullpath,mode)
    
    def close(self):
        self.filelist = []
        self.path = None
        self.mode = None
        if self.handle is not None:
            self.handle.close()
            
    def isdir(self):
        return self.handle is None and self.path
        
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
        text = isnumber.split(fileinfo.filename)
        numbers = isnumber.findall(fileinfo.filename)
        return tuple(pull(text,(int(n) for n in numbers)))
        
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.close()    

class PdfIOError(ArchiveIOError):
    pass

class PdfImage(object):
    def __init__(self,objid):
        self.objid = objid
        self.filename = text_type(objid)
        
    def __hash__(self):
        return hash(self.objid)

class PdfWrapper(ArchiveWrapper):
    def __init__(self,path,minsize=5120,bufferlen=1048576):
        self.path = path
        self.minsize = minsize
        self.mode = 'r'
        self.handle = None
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
                
        self.filelist = filelist[::-1]
        
            
    def filter_images(self):
        return self.filelist

    def close(self):
        super(PdfWrapper,self).close()
        self.dll.pdf_close_document(self.doc)
        self.dll.fz_free_context(self.context)
        
    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise WebIOError('Child mode does not fit to mode of Archive')
        
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
        

class WebWrapper(ArchiveWrapper):
    def __init__(self,url):
        self.path = ''
        self.mode = 'r'
        self.handle = None
        
        fileinfo = ImageParser(url).find_image()
        self.filelist = [fileinfo]
    
    def filter_images(self):
        return self.filelist
        
    def load_next(self):
        lastinfo = self.filelist[-1]
        if lastinfo.next_page:
            try:
                nextinfo = ImageParser(lastinfo.next_page).find_image()
            except WebIOError:
                nextinfo = None
                
            if nextinfo is not None:
                self.filelist.append(nextinfo)
                
    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise WebIOError('Child mode does not fit to mode of Archive')
        
        if fileinfo == self.filelist[-1]:
            self.load_next()
            
        return WebIO(fileinfo.image_url)
    
def list_archives(folder,recursive=False):
    filelist = ArchiveWrapper.folderlist(folder,'',recursive)
    filelist = sorted(filelist,key=ArchiveWrapper.split_filename)
    archlist = []
    for zi in filelist:
        base, ext = os.path.splitext(zi.filename)
        if ext.lower() in ArchiveWrapper.formats:
            archlist.append(zi.filename)
            
    return archlist

class Settings(QtGui.QDialog):
    settings = {'defheight':1600,'shorttimeout':1000,'longtimeout':2000,
                'optimizeview':1,'requiredoverlap':50,'preload':5,
                'buffernumber':10,'defwidth':0,'bgcolor':None,
                'saveposition':0,'overlap':20}
                
    def __init__(self,settings,parent=None):
        super(Settings,self).__init__(parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        #self.resize(640, 80)
        
        self.preload = QtGui.QLineEdit(self)
        self.buffernumber = QtGui.QLineEdit(self)
        self.defheight = QtGui.QLineEdit(self)
        self.defwidth = QtGui.QLineEdit(self)
        self.optview = QtGui.QCheckBox(self.tr("&Optimize Size"),self)
        self.shorttimeout = QtGui.QLineEdit(self)
        self.longtimeout = QtGui.QLineEdit(self)
        self.requiredoverlap = QtGui.QLineEdit(self)
        self.overlap = QtGui.QLineEdit(self)
        self.saveposition = QtGui.QCheckBox(self.tr("S&ave Position"),self)

        self.preload.setValidator(QtGui.QIntValidator())
        self.buffernumber.setValidator(QtGui.QIntValidator())
        self.shorttimeout.setValidator(QtGui.QIntValidator())
        self.longtimeout.setValidator(QtGui.QIntValidator())
        self.defheight.setValidator(QtGui.QIntValidator())
        self.defwidth.setValidator(QtGui.QIntValidator())
        self.requiredoverlap.setValidator(QtGui.QIntValidator())
        self.overlap.setValidator(QtGui.QIntValidator())

        self.preload.setToolTip(self.tr("Defines how many images after the "\
             "current one will be loaded in the background."))
        self.buffernumber.setToolTip(self.tr("Defines how many images will be "\
             "held in memory for a faster display.\nShould be larger than preload."))
        self.shorttimeout.setToolTip(self.tr("Number of miliseconds the "\
             "status display appears after a page change."))
        self.longtimeout.setToolTip(self.tr("Number of miliseconds the status "\
             "display appears after an archive is loaded or an error occurs."))
        self.defheight.setToolTip(self.tr("The default height an image should "\
             "be scaled to if the aspect ratio of width to height is smaller "\
             "than 2.\nHas priority over the default width, set to 0 to deactivate."))
        self.defwidth.setToolTip(self.tr("The default width an image should "\
             "be scaled to if the aspect ratio of height to width is smaller "\
             "than 2.\nThe default height has the priority, set to 0 to deactivate."))
        self.optview.setToolTip(self.tr("If active the width will be adapted "\
             "so it will be a multiple of the viewer width if it is already "\
             "close to it."))
        self.requiredoverlap.setToolTip(self.tr("Defines how close the width "\
             "has to be to be optimized to the viewer width."))
        self.overlap.setToolTip(self.tr("Defines how much of the old image "\
             "part is visible after advancing to the next one."))
        self.saveposition.setToolTip(self.tr("Save the position in the archive"\
             " on exit and loads it at the next start"))
        
        self.cancelbuttom = QtGui.QPushButton(self.tr("Cancel"),self)
        self.cancelbuttom.clicked.connect(self.reject)
        self.okbuttom = QtGui.QPushButton(self.tr("OK"),self)
        self.okbuttom.clicked.connect(self.accept)
        self.bgcolor_btm = QtGui.QPushButton('',self)
        self.bgcolor_btm.clicked.connect(self.select_color)

        self.setTabOrder(self.saveposition,self.defheight)
        self.setTabOrder(self.defheight,self.defwidth)
        self.setTabOrder(self.defwidth,self.overlap)
        self.setTabOrder(self.overlap,self.optview)
        self.setTabOrder(self.optview,self.requiredoverlap)
        self.setTabOrder(self.requiredoverlap,self.preload)
        self.setTabOrder(self.preload,self.buffernumber)
        self.setTabOrder(self.buffernumber,self.shorttimeout)
        self.setTabOrder(self.shorttimeout,self.longtimeout)
        self.setTabOrder(self.longtimeout,self.bgcolor_btm)
        self.setTabOrder(self.bgcolor_btm,self.okbuttom)
        self.setTabOrder(self.okbuttom,self.cancelbuttom)

        layout = QtGui.QFormLayout()
        layout.addRow(self.saveposition)
        layout.addRow(self.tr("Defaut &Height (px):"),self.defheight)
        layout.addRow(self.tr("Defaut &Width (px):"),self.defwidth)
        layout.addRow(self.tr("&Movement Overlap (%):"),self.overlap)
        layout.addRow(self.optview)
        layout.addRow(self.tr("&Required Overlap (%):"),self.requiredoverlap)
        layout.addRow(self.tr("&Preload Number:"),self.preload)
        layout.addRow(self.tr("&Buffer Number:"),self.buffernumber)
        layout.addRow(self.tr("&Short Timeout (ms):"),self.shorttimeout)
        layout.addRow(self.tr("&Long Timeout (ms):"),self.longtimeout)
        layout.addRow(self.tr("Background &Colorr:"),self.bgcolor_btm)
        layout.addRow(self.cancelbuttom,self.okbuttom)

        self.setLayout(layout)
        
        self.preload.setText(text_type(settings['preload']))
        self.buffernumber.setText(text_type(settings['buffernumber']))
        self.defheight.setText(text_type(settings['defheight']))
        self.defwidth.setText(text_type(settings['defwidth']))
        self.shorttimeout.setText(text_type(settings['shorttimeout']))
        self.longtimeout.setText(text_type(settings['longtimeout']))
        self.overlap.setText(text_type(settings['overlap']))
        self.requiredoverlap.setText(text_type(settings['requiredoverlap']))
        if settings['optimizeview']:
            self.optview.setCheckState(QtCore.Qt.Checked)
        if settings['saveposition']:
            self.saveposition.setCheckState(QtCore.Qt.Checked)
            
        self.bgcolor = settings['bgcolor']
        style = "QPushButton { background-color : rgb(%d,%d,%d)}" % self.bgcolor.getRgb()[:3]
        self.bgcolor_btm.setStyleSheet(style)

        
    def accept(self):
        settings = {}
        settings['preload'] = int(self.preload.text())
        settings['buffernumber'] = int(self.buffernumber.text())
        settings['defheight'] = int(self.defheight.text())
        settings['defwidth'] = int(self.defwidth.text())
        settings['shorttimeout'] = int(self.shorttimeout.text())
        settings['longtimeout'] = int(self.longtimeout.text())
        settings['requiredoverlap'] = int(self.requiredoverlap.text())
        settings['overlap'] = int(self.overlap.text())
        # convert bool to int so QSettings will not save it as a string
        settings['optimizeview'] = int(self.optview.isChecked())
        settings['saveposition'] = int(self.saveposition.isChecked())
        settings['bgcolor'] = self.bgcolor
        self.settings = settings
        super(Settings,self).accept()
        
    def select_color(self):
        self.bgcolor = QtGui.QColorDialog.getColor(self.bgcolor,self)
        style = "QPushButton { background-color : rgb(%d,%d,%d)}" % self.bgcolor.getRgb()[:3]
        self.bgcolor_btm.setStyleSheet(style)

class PageSelect(QtGui.QDialog):
    def __init__(self,parent=None):
        super(PageSelect,self).__init__(parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        self.resize(640, 80)
        self.imagelist = []
        
        self.page = QtGui.QLineEdit(self)
        self.page.setMaximumWidth(50)
        self.page.setValidator(QtGui.QIntValidator())
        self.page.setAlignment(QtCore.Qt.AlignCenter)
        self.page.textChanged.connect(self.set_value)
        self.slider = QtGui.QSlider(QtCore.Qt.Horizontal,self)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(self.slider.TicksBelow)
        self.slider.setMinimum(1)
        self.slider.valueChanged.connect(self.set_value)
        self.okbuttom = QtGui.QPushButton(self.tr("OK"),self)
        self.okbuttom.clicked.connect(self.accept)
        self.cancelbuttom = QtGui.QPushButton(self.tr("Cancel"),self)
        self.cancelbuttom.clicked.connect(self.reject)

        self.label = QtGui.QLabel(self)

        layout = QtGui.QHBoxLayout()
        layout.addWidget(self.slider)
        layout.addWidget(self.page)
        
        mlayout = QtGui.QGridLayout()
        mlayout.setVerticalSpacing(0)
        mlayout.addLayout(layout,0,0)
        mlayout.addWidget(self.okbuttom,0,1)
        mlayout.addWidget(self.label,1,0)
        mlayout.addWidget(self.cancelbuttom,1,1)
        
        self.setTabOrder(self.slider,self.page)
        self.setTabOrder(self.page,self.okbuttom)
        self.setTabOrder(self.okbuttom,self.cancelbuttom)
        
        self.setLayout(mlayout)
        
    def set_range(self,cur,imagelist):
        self.imagelist = imagelist
        self.slider.setMaximum(len(imagelist))
        self.set_value(cur+1)
        
    def set_value(self,value):
        try:
            value = int(value)
            if value > len(self.imagelist):
                value = len(self.imagelist)
            self.slider.setValue(value)
            self.page.setText(text_type(value))
            
            metric = QtGui.QFontMetrics(self.label.font())
            text = self.imagelist[value-1].filename
            elided = metric.elidedText(text,QtCore.Qt.ElideLeft, self.label.width())
            self.label.setText(elided)
        except ValueError:
            pass
        
        self.value = self.slider.value()-1

class WorkerThread(QtCore.QThread):
    loaded = QtCore.Signal(int)
    
    def __init__(self,viewer,pos,center=None):
        super(WorkerThread,self).__init__(viewer)
        self.viewer = viewer
        self.fileinfo = viewer.imagelist[pos]
        self.pos = pos
        self.center = center
        self.error = ''
        self.img = None
        self.finished.connect(self.removeParent) # necessary to remove handle in viewer
        
    def run(self):
        self.img, self.error = self.viewer.prepare_image(self.fileinfo)
        self.loaded.emit(self.pos)
        
    def removeParent(self):
        self.setParent(None)

class ImageViewer(QtGui.QGraphicsView):
    def __init__(self,scene=None):
        super(ImageViewer,self).__init__(scene)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setWindowTitle(self.tr("Image Viewer"))
        self.setWindowIcon(APP_ICON)
        self.setFrameShape(self.NoFrame)
        scene.setBackgroundBrush(QtCore.Qt.black)
 
        self.label = QtGui.QLabel(self.tr('Nothing to show<br \>Open an image archive'),self)
        self.label.setStyleSheet("QLabel { background-color : black; color : white; padding: 5px 5px 5px 5px;border-radius: 5px; }")
        self.label.setOpenExternalLinks(True)
        self.label.setTextFormat(QtCore.Qt.RichText)
        self.label.move(10,10)
        self.labeltimer = QtCore.QTimer(self)
        self.labeltimer.timeout.connect(self.hide_label)
        
        self.resizetimer = QtCore.QTimer(self)
        self.resizetimer.timeout.connect(self.resize_view)
        
        self.pageselect = PageSelect(self)
        
        self.workers = {}
        self.buffer = {}

        self.setAcceptDrops(True)
        self.imagelist = []
        self.farch = None
        for key,value in iteritems(Settings.settings):
            setattr(self,key,value)
                        
        actions = {}
        actions['open'] = QtGui.QAction(self.tr("&Open"), self,
                        shortcut=QtGui.QKeySequence.Open,
                        statusTip=self.tr("Open a new file"), 
                        triggered=self.action_open)
        actions['settings'] = QtGui.QAction(self.tr("&Settings"), self,
                        shortcut=QtGui.QKeySequence(QtCore.Qt.Key_S),
                        statusTip=self.tr("Open Settings"), 
                        triggered=self.action_settings)
        actions['next_file'] = QtGui.QAction(self.tr("Next Archive"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_L),
                         statusTip=self.tr("Load the next archive in the folder"), 
                         triggered=self.action_next_file)
        actions['prev_file'] = QtGui.QAction(self.tr("Previous Archive"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_K),
                         statusTip=self.tr("Load the previous archive in the folder"), 
                         triggered=self.action_prev_file)
        actions['next'] = QtGui.QAction(self.tr("Next View"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_Space),
                         statusTip=self.tr("Show next image part"), 
                         triggered=self.action_next)
        actions['prev'] = QtGui.QAction(self.tr("Previous View"), self,
                         shortcut=QtGui.QKeySequence("Shift+Space"),
                         statusTip=self.tr("Show previous image part"), 
                         triggered=self.action_prev)
        actions['page'] = QtGui.QAction(self.tr("Select Page"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_P),
                         statusTip=self.tr("Select the an image"), 
                         triggered=self.action_page)
        actions['info'] = QtGui.QAction(self.tr("Information"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_I),
                         checkable=True,
                         statusTip=self.tr("Show informaion about image"), 
                         triggered=self.action_info)
        actions['first_image'] = QtGui.QAction(self.tr("First Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToStartOfLine,
                         statusTip=self.tr("Show first image"), 
                         triggered=self.action_first_image)
        actions['last_image'] = QtGui.QAction(self.tr("Last Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToEndOfLine,
                         statusTip=self.tr("Show last image"), 
                         triggered=self.action_last_image)
        actions['next_image'] = QtGui.QAction(self.tr("Next Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToNextPage,
                         statusTip=self.tr("Show next image"), 
                         triggered=self.action_next_image)
        actions['prev_image'] = QtGui.QAction(self.tr("Previous Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToPreviousPage,
                         statusTip=self.tr("Show previous image"), 
                         triggered=self.action_prev_image)
        actions['fullscreen'] = QtGui.QAction(self.tr("Fullscreen"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_F),
                         checkable=True,
                         statusTip=self.tr("Toggle Fullscreen"), 
                         triggered=self.action_toggle_fullscreen)
        actions['minimize'] = QtGui.QAction(self.tr("Minimize"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_M),
                         statusTip=self.tr("Minimize Window"), 
                         triggered=self.showMinimized)
        actions['close'] = QtGui.QAction(self.tr("Close"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_Escape),
                         statusTip=self.tr("Close Viewer"), 
                         triggered=self.close)
                         
        actions['movement'] = QtGui.QActionGroup(self)
        actions['movement'].triggered.connect(self.action_movement)
        rd = QtGui.QAction(self.tr("Right Down"),actions['movement'],checkable=True)
        ld = QtGui.QAction(self.tr("Left Down"),actions['movement'],checkable=True)
        dr = QtGui.QAction(self.tr("Down Right"),actions['movement'],checkable=True)
        dl = QtGui.QAction(self.tr("Down Left"),actions['movement'],checkable=True)
        
        lt = QtCore.QPointF(0,0)
        rt = QtCore.QPointF(INF_POINT,0)
        lb = QtCore.QPointF(0,INF_POINT)
        rb = QtCore.QPointF(INF_POINT,INF_POINT)
        movements = {}
        movements[rd] = lt, rb, self.move_right_down, self.move_left_up
        movements[dr] = lt, rb, self.move_down_right, self.move_up_left
        movements[ld] = rt, lb, self.move_left_down, self.move_right_up
        movements[dl] = rt, lb, self.move_down_left, self.move_up_right
        self.movement = movements
        self.action_movement(rd)
        
        for act in itervalues(actions):
            if isinstance(act,QtGui.QAction):
                self.addAction(act)
        self.actions = actions
        
    def load_archive(self,path,page=0):
        """
        load the images in the archive given py path and show the first one.
        
        Parameters
        ----------
            path : the path to the archive to load
            page : the page to open in the archive, default 0.
            
        
        Returns
        ----------
            success : returns ``True`` if images could be loaded and ``False``
                      if no images could be found in the archive.
        """
        try:
            errormsg = ''
            dummy, ext = os.path.splitext(path)
            if path.startswith('http'):
                farch = WebWrapper(path)
            elif ext.lower() == '.pdf' and '.pdf' in KNOWN_ARCHIVES:
                farch = PdfWrapper(path)
            else:
                farch = ArchiveWrapper(path,'r')
            imagelist = farch.filter_images()
                    
            if imagelist:
                self.buffer = {}
                self.workers = {}
                self.farch = farch
                self.imagelist = imagelist
                if page < len(imagelist):
                    self.cur = page
                else:
                    self.cur = 0
                scene = self.scene()
                scene.clear()
                scene.setSceneRect(0,0,10,10)
                self.action_queued_image(self.cur,self._mv_start)
            else:
                path, name = os.path.split(path)
                errormsg = self.tr('No images found in "%s"') % name
                
        except ArchiveIOError as err:
            errormsg = str(err) or self.tr("Unkown Error")
        
        if errormsg:
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.longtimeout)
            return False
        else:
            return True
    
    def prepare_image(self,fileinfo):
        try:
            with self.farch.open(fileinfo,'rb') as fin:
                    img = Image.open(fin).convert('RGB')
        except IOError as err:
            return None, str(err) or 'Unkown Error'
        
        csize = None
        width, height = img.size
        ratio = width/height
        view_rect = self.viewport().rect()
        swidth, sheight = view_rect.width(), view_rect.height()
        move_h = int(swidth*(100-self.overlap)/100)
        origsize = width, height
        
        if ratio < 2.0 and self.defheight:
            width = int(ratio*self.defheight)
            height = self.defheight
            csize = width, height
        elif ratio > 0.5 and self.defwidth:
            width = self.defwidth
            height = int(self.defwidth/ratio)
            csize = width, height
            
        requiredperc = self.requiredoverlap/100.0

        if self.optimizeview and width > swidth:
            diff = width-swidth
            if (diff%move_h) < requiredperc*swidth:
                width = int(swidth+int(diff/move_h)*move_h)
                height = int(width/ratio)
                csize = width, height
        
        if csize is not None:
            img = img.resize(csize,Image.ANTIALIAS)
            
        img.origsize = origsize
        return img, ''
        
    def display_image(self, img, center=None):
        scene = self.scene()
        was_empty = len(list(scene.items()))==0
        scene.clear()
        center = center or self._mv_start
        if isinstance(img,Image.Image):
            w, h = img.size
            scene.setSceneRect(0,0,w,h)
            self.imgQ = ImageQt.ImageQt(img)  # we need to hold reference to imgQ, or it will crash
            self.imgQ.origsize = img.origsize
            scene.addPixmap(QtGui.QPixmap.fromImage(self.imgQ))
            self.centerOn(center)
            if was_empty:
                self.label.hide()
                self.action_info()
                self.labeltimer.start(self.longtimeout)
            else:
                self.label.setText("%d/%d" % (self.cur+1,len(self.imagelist)))
                self.label.resize(self.label.sizeHint())
                self.label.show()
                self.labeltimer.start(self.shorttimeout)
        else:
            img = cgi.escape(img)
            text = "%d/%d<br />%s" % (self.cur+1,len(self.imagelist),img)
            self.label.setText(text)
            self.label.resize(self.label.sizeHint())
            scene.setSceneRect(0,0,10,10)
        
    def hide_label(self):
        self.actions['info'].setChecked(QtCore.Qt.Unchecked)
        self.label.hide()
        self.labeltimer.stop()
        
    def resize_view(self):
        self.resizetimer.stop()
        self.workers.clear()
        self.buffer.clear()
        if self.imagelist:
            self.action_queued_image(self.cur,self._mv_start)
        
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        menu.addAction(self.actions['open'])
        menu.addAction(self.actions['prev_file'])
        menu.addAction(self.actions['next_file'])
        menu.addSeparator()
        menu.addAction(self.actions['info'])
        menu.addAction(self.actions['page'])
        menu.addAction(self.actions['first_image'])
        menu.addAction(self.actions['last_image'])
        menu.addAction(self.actions['prev_image'])
        menu.addAction(self.actions['next_image'])
        menu.addAction(self.actions['prev'])
        menu.addAction(self.actions['next'])
        menu.addSeparator()
        mv_menu = menu.addMenu(self.tr('Movement'))
        for act in self.actions['movement'].actions():
            mv_menu.addAction(act)
        menu.addAction(self.actions['fullscreen'])
        menu.addAction(self.actions['minimize'])
        menu.addSeparator()
        menu.addAction(self.actions['settings'])
        menu.addAction(self.actions['close'])
        menu.exec_(event.globalPos())
 
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():
            e.accept()
        else:
            super(ImageViewer,self).dragEnterEvent(e)
            
            
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(QtCore.Qt.LinkAction)
            e.accept()
        else:
            super(ImageViewer,self).dragMoveEvent(e)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            url = event.mimeData().urls()[0]
            path = text_type(url.toLocalFile())
            if path:
                self.load_archive(path)
            else:
                self.load_archive(url.toString())
        else:
            super(ImageViewer,self).dropEvent(event)

    def mouseDoubleClickEvent(self,e):
        self.action_next()
        
    def resizeEvent(self,e):
        if e.oldSize().isValid():
            self.resizetimer.start(100)
        super(ImageViewer,self).resizeEvent(e)
        
    def closeEvent(self,e):
        self.save_settings()
        if self.farch:
            self.farch.close()
            
        if self.workers:
            for worker in itervalues(self.workers):
                worker.terminate()
            
        super(ImageViewer,self).closeEvent(e)
        
    def action_queued_image(self,pos,center=None):
        existing = set(self.workers)|set(self.buffer)
        preloading = set(range(self.cur+1,self.cur+self.preload+1))
        preloading &= set(range(len(self.imagelist)))
        loadcandidate = preloading-existing
        
        if pos in self.workers and center is None:
            worker = self.workers.pop(pos)
            center = center or worker.center
            if worker.img:
                self.buffer[pos] = worker.img
            else:
                self.buffer[pos] = worker.error
            
        if pos not in self.workers and pos not in self.buffer:
            toload = pos
        elif loadcandidate:
            toload = min(loadcandidate)
        else:
            toload = None
            
        if toload is not None and toload < len(self.imagelist):
            self.workers[toload] = worker = WorkerThread(self,toload,center)
            worker.loaded.connect(self.action_queued_image)
            worker.start()
        
        if self.cur in self.workers:
            loading = ','.join(str(p+1) for p in sorted(self.workers))
            params = self.cur+1, len(self.imagelist), loading
            text = self.tr('%d/%d<br />Loading %s ...') % params
            self.label.setText(text)
            self.label.resize(self.label.sizeHint())
            self.label.show()

        if pos == self.cur and pos in self.buffer:
            self.display_image(self.buffer[pos],center)
            
        if len(self.buffer) > self.buffernumber:
            # .25 makes sure images before the current one get removed first
            # if they have the same distance to the image
            key = lambda x: abs(self.cur-x+.25)
            srtpos = sorted(set(self.buffer)-preloading,key=key)
            for pos in srtpos[self.buffernumber:]:
                del self.buffer[pos]
    
    def action_open(self):
        archives = ' '.join('*%s' % ext for ext in ArchiveWrapper.formats)
        dialog = QtGui.QFileDialog(self)
        dialog.setFileMode(dialog.ExistingFile)
        dialog.setNameFilter(self.tr("Archives (%s)") % archives)
        dialog.setViewMode(dialog.Detail)
        if self.farch:
            path, name = os.path.split(self.farch.path)
            dialog.setDirectory(path)
        if dialog.exec_():
            self.load_archive(dialog.selectedFiles()[0])

    def action_settings(self):
        sdict = {}
        for s in Settings.settings:
            sdict[s] = getattr(self,s)

        dialog = Settings(sdict,self)
        if dialog.exec_():
            for key, value in iteritems(dialog.settings):
                setattr(self,key,value)
                
            if self.bgcolor != sdict['bgcolor']:
                self.scene().setBackgroundBrush(self.bgcolor)
                
            if sdict['defheight'] != self.defheight or \
               sdict['defwidth'] != self.defwidth or \
               sdict['overlap'] != self.overlap or \
               sdict['optimizeview'] != self.optimizeview or \
               sdict['requiredoverlap'] != self.requiredoverlap:
                self.buffer.clear()
                self.workers.clear()
                if self.imagelist:
                    self.action_queued_image(self.cur,self._mv_start)
                
        
    def action_page(self):
        if self.imagelist:
            self.pageselect.set_range(self.cur,self.imagelist)
            if self.pageselect.exec_():
                self.cur = self.pageselect.value
                self.action_queued_image(self.cur,self._mv_start)
        
    def action_info(self):
        if self.label.isHidden() and self.imagelist:
            zi = self.imagelist[self.cur]
            labelstr = u'%d/%d' % (self.cur+1,len(self.imagelist))
            labelstr += u'<br />%d \u2715 %d' % self.imgQ.origsize
            labelstr += u'<br />%s' % zi.filename
            if isinstance(self.farch,WebWrapper):
                labelstr += '<br \><a href="%s">%s</a>' % (zi.page_url,zi.page_url)
            else:
                path, archname = os.path.split(self.farch.path)
                labelstr += '<br \>%s' % archname
                
            if self.workers:
                loading = ','.join(str(p+1) for p in sorted(self.workers))
                labelstr += '<br \>' + self.tr('Loading %s') % loading
                
            self.label.setText(labelstr)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.actions['info'].setChecked(QtCore.Qt.Checked)
        elif self.imagelist:
            self.actions['info'].setChecked(QtCore.Qt.Unchecked)
            self.label.hide()
        
    def action_movement(self,action):
        action.setChecked(True)
        self._mv_start, self._mv_end, self._mv_next, self._mv_prev = self.movement[action]
    
    def action_toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def action_next_file(self):
        errormsg = ''
        if self.farch:
            folder, name = os.path.split(self.farch.path)
            archlist = list_archives(folder)
            try:
                loadindex = archlist.index(name)+1
            except ValueError:
                loadindex = 0
                
            while loadindex < len(archlist) and \
              not self.load_archive(os.path.join(folder,archlist[loadindex])):
                loadindex += 1  
                    
            if loadindex >= len(archlist):
                errormsg = self.tr('No further archives in "%s"') % folder 

        if errormsg:
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.longtimeout)
            
    
    def action_prev_file(self):
        errormsg = ''
        if self.farch:
            folder, name = os.path.split(self.farch.path)
            archlist = list_archives(folder)
            try:
                loadindex = archlist.index(name)-1
            except ValueError:
                loadindex = len(archlist)-1
                
            while loadindex >= 0 and \
              not self.load_archive(os.path.join(folder,archlist[loadindex])):
                loadindex -= 1  
                    
            if loadindex < 0:
                errormsg = self.tr('No previous archives in "%s"') % folder

        if errormsg:
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.longtimeout)
            
        
    def action_first_image(self):
        if self.imagelist:
            self.cur = 0
            self.action_queued_image(self.cur,self._mv_start)

    def action_last_image(self):
        if self.imagelist:
            self.cur = len(self.imagelist)-1
            self.action_queued_image(self.cur,self._mv_start)
            
    def action_next_image(self):
        if self.imagelist and (self.cur+1) < len(self.imagelist):
            self.cur += 1
            self.action_queued_image(self.cur,self._mv_start)
        elif self.imagelist:
            self.label.setText(self.tr("No further images in this archive"))
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.longtimeout)
        
    def action_prev_image(self):
        if self.imagelist and self.cur > 0:
            self.cur -= 1
            self.action_queued_image(self.cur,self._mv_end)
        elif self.imagelist:
            self.label.setText(self.tr("No previous images in this archive"))
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.longtimeout)
            
    def action_next(self):
        view_rect = self.viewport().rect()
        view_rect = self.mapToScene(view_rect).boundingRect()
        scene_rect = self.sceneRect()
        move_h = int(view_rect.width()*(100-self.overlap)/100)
        move_v = int(view_rect.height()*(100-self.overlap)/100)
        
        step = self._mv_next(scene_rect,view_rect,move_h,move_v)
        if step:
            self.centerOn(view_rect.center()+step)
        else:
            self.action_next_image()

    def action_prev(self):
        view_rect = self.viewport().rect()
        view_rect = self.mapToScene(view_rect).boundingRect()
        scene_rect = self.sceneRect()
        move_h = int(view_rect.width()*(100-self.overlap)/100)
        move_v = int(view_rect.height()*(100-self.overlap)/100)
        step = self._mv_prev(scene_rect,view_rect,move_h,move_v)
        if step:
            self.centerOn(view_rect.center()+step)
        else:
            self.action_prev_image()
            
    @staticmethod
    def move_down_right(scene,view,dx,dy):
        if scene.bottom() > view.bottom():
            return QtCore.QPointF(0.0,dy)
        elif scene.right() > view.right():
            return QtCore.QPointF(dx,-INF_POINT)

    @staticmethod
    def move_down_left(scene,view,dx,dy):
        if scene.bottom() > view.bottom():
            return QtCore.QPointF(0.0,dy)
        elif scene.left() < view.left():
            return QtCore.QPointF(-dx,-INF_POINT)

    @staticmethod
    def move_right_down(scene,view,dx,dy):
        if scene.right() > view.right():
            return QtCore.QPointF(dx,0.0)
        elif scene.bottom() > view.bottom():
            return QtCore.QPointF(-INF_POINT,dy)

    @staticmethod
    def move_left_down(scene,view,dx,dy):
        if scene.left() < view.left():
            return QtCore.QPointF(-dx,0.0)
        elif scene.bottom() > view.bottom():
            return QtCore.QPointF(INF_POINT,dy)

    @staticmethod
    def move_up_left(scene,view,dx,dy):
        if scene.top() < view.top():
            return QtCore.QPointF(0.0,-dy)
        elif scene.left() < view.left():
            return QtCore.QPointF(-dx,INF_POINT)
 
    @staticmethod
    def move_up_right(scene,view,dx,dy):
        if scene.top() < view.top():
            return QtCore.QPointF(0.0,-dy)
        elif scene.right() > view.right():
            return QtCore.QPointF(dx,INF_POINT)
            
    @staticmethod
    def move_left_up(scene,view,dx,dy):
        if scene.left() < view.left():
            return QtCore.QPointF(-dx,0.0)
        elif scene.top() < view.top():
            return QtCore.QPointF(INF_POINT,-dy)

    @staticmethod
    def move_right_up(scene,view,dx,dy):
        if scene.right() > view.right():
            return QtCore.QPointF(dx,0.0)
        elif scene.top() < view.top():
            return QtCore.QPointF(-INF_POINT,-dy)

    def save_settings(self):
        settings = QtCore.QSettings("Caasar", "Image Viewer")
        settings.beginGroup("MainWindow")
        settings.setValue("fullscreen", self.isFullScreen())
        if not self.isFullScreen():
            settings.setValue("pos", self.pos())
            settings.setValue("size", self.size())
        settings.setValue("movement", self._mv_next.__name__)
        settings.endGroup()        
        settings.beginGroup("Settings")
        for key in Settings.settings:
            settings.setValue(key,getattr(self,key))
        settings.endGroup()
        if self.saveposition and self.imagelist:
            settings.beginGroup("History")
            if isinstance(self.farch,WebWrapper):
                fileinfo = self.imagelist[self.cur]
                settings.setValue("lastpath", fileinfo.page_url)
                settings.setValue("lastpage", 0)
            else:
                settings.setValue("lastpath", self.farch.path)
                settings.setValue("lastpage", self.cur)
            settings.endGroup()
        
    def load_settings(self):
        settings = QtCore.QSettings("Caasar", "Image Viewer")
        settings.beginGroup("MainWindow")
        self.resize(settings.value("size",QtCore.QSize(640, 480)))
        self.move(settings.value("pos", QtCore.QPoint(100, 100)))
        isFullscreen = settings.value("fullscreen", 'false') == 'true'
        movement = settings.value("movement", 'move_right_down')
        settings.endGroup()        
        settings.beginGroup("Settings")
        for key,defvalue in iteritems(Settings.settings):
            setattr(self,key,settings.value(key,defvalue))
        settings.endGroup()
        
        self.bgcolor = QtGui.QColor(self.bgcolor)
        self.scene().setBackgroundBrush(self.bgcolor)
        
        for key,(s,e,n,p) in iteritems(self.movement):
            if n.__name__ == movement:
                self.action_movement(key)
                break
        
        if self.saveposition:
            settings.beginGroup("History")
            path = settings.value("lastpath",'')
            pos = settings.value("lastpage",0)
            if path:
                self.load_archive(path,pos)
            
        if isFullscreen:
            self.actions['fullscreen'].setChecked(QtCore.Qt.Checked)
        return isFullscreen
    

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv[:1])
    APP_ICON = QtGui.QIcon('res/image.png')
    scene = QtGui.QGraphicsScene()
    view = ImageViewer(scene)
    if view.load_settings():
        view.showFullScreen()
    else:
        view.show()
    
    if len(sys.argv) > 1:
        view.load_archive(sys.argv[1])
    sys.exit(app.exec_())
    
