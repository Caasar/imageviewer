#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function

import sys

try: 
    import PySide
    sys.modules['PyQt4'] = PySide # HACK for ImageQt
    from PySide import QtCore, QtGui
except ImportError:
    from PyQt4 import QtCore, QtGui
    QtCore.Signal = QtCore.pyqtSignal
    
import os,re,cgi
import math
#import htmllib,formatter
from ast import literal_eval
from six import text_type, itervalues, iteritems
from functools import partial
from collections import namedtuple
from wrapper import KNOWN_ARCHIVES, WrapperIOError
from wrapper.archive import ArchiveWrapper
from wrapper.pdf import PdfWrapper
from wrapper.web import WebWrapper
#from six.moves import cStringIO as StringIO
import PIL.Image as Image
import PIL.ImageQt as ImageQt

INF_POINT = 100000

def open_wrapper(path):
    """
    Open the the correct Wrapper for the provided path.
    """
    dummy, ext = os.path.splitext(path)
    if path.startswith('http'):
        farch = WebWrapper(path)
    elif ext.lower() == '.pdf' and '.pdf' in KNOWN_ARCHIVES:
        farch = PdfWrapper(path)
    else:
        farch = ArchiveWrapper(path,'r')
    
    return farch
    

class WebProfileSettings(QtGui.QDialog):
    def __init__(self, *args):
        super(WebProfileSettings,self).__init__(*args)
        # setGeometry(x_pos, y_pos, width, height)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        #self.setGeometry(300, 200, 570, 450)
        #self.setWindowTitle(self.tr("Parser"))
        self.setFixedWidth(400)

        profile = QtGui.QComboBox(self,editable=True)
        page_url = QtGui.QLineEdit(self)
        img_url = QtGui.QLineEdit(self)
        next_url = QtGui.QLineEdit(self)

        profile.activated.connect(self.load_profile)
        profile.addItems(list(WebWrapper.profiles.keys()))
        page_url.editingFinished.connect(self.update_profile)
        img_url.editingFinished.connect(self.update_profile)
        next_url.editingFinished.connect(self.update_profile)
        
        page_url.setToolTip(self.tr("A regular expresion."))
        img_url.setToolTip(self.tr("CSS Selector for image element."))
        next_url.setToolTip(self.tr("CSS Selector for next page link."))

        cancel_btn = QtGui.QPushButton(self.tr("&Cancel"),self)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QtGui.QPushButton(self.tr("&OK"),self)
        ok_btn.clicked.connect(self.accept)
        
        hbox = QtGui.QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(ok_btn)
        hbox.addWidget(cancel_btn)

        layout = QtGui.QFormLayout()
        layout.addRow(self.tr("&Profile:"),profile)
        layout.addRow(self.tr("&Url:"),page_url)
        layout.addRow(self.tr("&Image filter:"),img_url)
        layout.addRow(self.tr("&Next url filter:"),next_url)
        
        if 'bs4' not in sys.modules:
            label = QtGui.QLabel(self.tr("Could not load BeautifulSoup4. Only defaut webparser available."))
            label.setStyleSheet("QLabel { color : red; }")
            profile.setDisabled(True)
            page_url.setDisabled(True)
            img_url.setDisabled(True)
            next_url.setDisabled(True)
            layout.addRow(label)
        
        layout.addRow(hbox)

        self.setLayout(layout)
        self.profile = profile
        self.page_url = page_url
        self.img_url = img_url
        self.next_url = next_url
        self.profiles = dict(WebWrapper.profiles)
        self.load_profile(0)
        
        self.setTabOrder(profile,page_url)
        self.setTabOrder(page_url,img_url)
        self.setTabOrder(img_url,next_url)
        self.setTabOrder(next_url,ok_btn)
        self.setTabOrder(ok_btn,cancel_btn)

    def load_profile(self,index):
        profile = self.profile.currentText()
        prof = self.profiles.get(profile,None)
        if prof:
            self.page_url.setText(prof['url']) 
            self.img_url.setText(prof['img']) 
            self.next_url.setText(prof['next']) 
        
    def update_profile(self):
        profile = self.profile.currentText()
        if profile:
            prof = self.profiles.setdefault(profile, {})
            prof['url'] = self.page_url.text()
            prof['img'] = self.img_url.text()
            prof['next'] = self.next_url.text()
        
    def accept(self):
        for key, prof in self.profiles.items():
            WebWrapper.profiles.pop(key, None)
            if prof['url'] or prof['img'] or prof['next']:
                WebWrapper.profiles[key] = prof
        super(WebProfileSettings,self).accept()
        

class Settings(QtGui.QDialog):
    settings = {'shorttimeout':1000,'longtimeout':2000, 'requiredoverlap':50,
                'preload':5,'buffernumber':10,
                'bgcolor': QtGui.QColor(QtCore.Qt.white),
                'saveposition':0,'overlap':20,'maxscale':200,
                'minscale':20, 'write_quality': 80, 'write_optimize':1,
                'write_progressive':1, 'scaling':'1000x1600=>0x1600'}
    Tuple = namedtuple('Settings', settings.keys())
    settings = Tuple(**settings)
    
    def __init__(self, settings, parent=None):
        super(Settings,self).__init__(parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        #self.resize(640, 80)
        
        self.preload = QtGui.QLineEdit(self)
        self.buffernumber = QtGui.QLineEdit(self)
        self.scaling = QtGui.QTextEdit(self)
        self.maxscale = QtGui.QLineEdit(self)
        self.minscale = QtGui.QLineEdit(self)
        self.shorttimeout = QtGui.QLineEdit(self)
        self.longtimeout = QtGui.QLineEdit(self)
        self.requiredoverlap = QtGui.QLineEdit(self)
        self.overlap = QtGui.QLineEdit(self)
        self.saveposition = QtGui.QCheckBox(self.tr("S&ave Position"),self)

        self.preload.setValidator(QtGui.QIntValidator())
        self.buffernumber.setValidator(QtGui.QIntValidator())
        self.shorttimeout.setValidator(QtGui.QIntValidator())
        self.longtimeout.setValidator(QtGui.QIntValidator())
        self.maxscale.setValidator(QtGui.QIntValidator())
        self.minscale.setValidator(QtGui.QIntValidator())
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
        self.scaling.setToolTip(self.tr("Defines a list of scalings to apply. "\
             "Each line defines a scaling to use. The scaling with the closest "\
             "matching ingong ratio will be used"))
        self.maxscale.setToolTip(self.tr("The maxiamal possible scale value in percent"))
        self.minscale.setToolTip(self.tr("The minimal possible scale value in percent"))
        self.requiredoverlap.setToolTip(self.tr("Defines how close the width "\
             "or height has to be to be optimized to the viewer."))
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

        self.setTabOrder(self.saveposition,self.scaling)
        self.setTabOrder(self.scaling,self.minscale)
        self.setTabOrder(self.minscale,self.maxscale)
        self.setTabOrder(self.maxscale,self.overlap)
        self.setTabOrder(self.overlap,self.requiredoverlap)
        self.setTabOrder(self.requiredoverlap,self.preload)
        self.setTabOrder(self.preload,self.buffernumber)
        self.setTabOrder(self.buffernumber,self.shorttimeout)
        self.setTabOrder(self.shorttimeout,self.longtimeout)
        self.setTabOrder(self.longtimeout,self.bgcolor_btm)
        self.setTabOrder(self.bgcolor_btm,self.okbuttom)
        self.setTabOrder(self.okbuttom,self.cancelbuttom)

        hbox = QtGui.QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(self.okbuttom)
        hbox.addWidget(self.cancelbuttom)

        layout = QtGui.QFormLayout()
        layout.addRow(self.saveposition)
        layout.addRow(self.tr("Scalin&g:"),self.scaling)
        layout.addRow(self.tr("M&in. Scale (%):"),self.minscale)
        layout.addRow(self.tr("M&an. Scale (%):"),self.maxscale)
        layout.addRow(self.tr("Movement &Overlap (%):"),self.overlap)
        layout.addRow(self.tr("&Optimzed Overlap (%):"),self.requiredoverlap)
        layout.addRow(self.tr("&Preload Number:"),self.preload)
        layout.addRow(self.tr("&Buffer Number:"),self.buffernumber)
        layout.addRow(self.tr("&Short Timeout (ms):"),self.shorttimeout)
        layout.addRow(self.tr("&Long Timeout (ms):"),self.longtimeout)
        layout.addRow(self.tr("Background &Colorr:"),self.bgcolor_btm)
        layout.addRow(hbox)

        self.setLayout(layout)
        
        self.preload.setText(text_type(settings.preload))
        self.buffernumber.setText(text_type(settings.buffernumber))
        self.scaling.setText(text_type(settings.scaling))
        self.maxscale.setText(text_type(settings.maxscale))
        self.minscale.setText(text_type(settings.minscale))
        self.shorttimeout.setText(text_type(settings.shorttimeout))
        self.longtimeout.setText(text_type(settings.longtimeout))
        self.overlap.setText(text_type(settings.overlap))
        self.requiredoverlap.setText(text_type(settings.requiredoverlap))
        if settings.saveposition:
            self.saveposition.setCheckState(QtCore.Qt.Checked)
            
        self.bgcolor = settings.bgcolor or QtGui.QColor(QtCore.Qt.white)
        style = "QPushButton { background-color : rgba(%d,%d,%d,%d)}" % self.bgcolor.getRgb()
        self.bgcolor_btm.setStyleSheet(style)

        
    def accept(self):
        settings = {}
        settings['preload'] = int(self.preload.text())
        settings['buffernumber'] = int(self.buffernumber.text())
        settings['scaling'] = text_type(self.scaling.toPlainText())
        settings['maxscale'] = int(self.maxscale.text())
        settings['minscale'] = int(self.minscale.text())
        settings['shorttimeout'] = int(self.shorttimeout.text())
        settings['longtimeout'] = int(self.longtimeout.text())
        settings['requiredoverlap'] = int(self.requiredoverlap.text())
        settings['overlap'] = int(self.overlap.text())
        # convert bool to int so QSettings will not save it as a string
        settings['saveposition'] = int(self.saveposition.isChecked())
        settings['bgcolor'] = self.bgcolor
        self.settings = self.dict2tuple(settings)
        super(Settings,self).accept()
        
    def select_color(self):
        self.bgcolor = QtGui.QColorDialog.getColor(self.bgcolor,self)
        style = "QPushButton { background-color : rgb(%d,%d,%d,%d)}" % self.bgcolor.getRgb()
        self.bgcolor_btm.setStyleSheet(style)
        
    @classmethod
    def dict2tuple(cls, settings):
        cdict = cls.settings._asdict()
        cdict.update(settings)
        return cls.Tuple(**cdict)

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
        
class DroppingThread(QtCore.QThread):
    loaded_archive = QtCore.Signal()
    
    def __init__(self,*args):
        super(DroppingThread,self).__init__(*args)
        self.path = None
        self.farch = None
        self.errmsg = ''

    def set_path(self,path):
        self.path = path
        return self
        
    def pop_archive(self):
        tpl = self.farch, self.errmsg
        self.farch = None
        self.errmsg = None
        return tpl
        
    def run(self):
        try:
            self.farch = open_wrapper(self.path)
            self.errmsg = None
        except WrapperIOError as err:
            self.farch = None
            self.errmsg = text_type(err) or "Unknown Error"
            
        self.loaded_archive.emit()

class ImageViewer(QtGui.QGraphicsView):
    Scaling = namedtuple('Scaling', ['ratio', 'width', 'height'])
    re_scaling = re.compile(r'(?P<iwidth>\d+)\s*x\s*(?P<iheight>\d+)\s*'\
                            r'=\>\s*(?P<width>\d+)\s*x\s*(?P<height>\d+)')
    label_css = """
QLabel { 
    background-color : black; 
    color : white; 
    padding: 5px 5px 5px 5px;
    border-radius: 5px; 
}
"""
    
    def __init__(self,scene=None):
        super(ImageViewer,self).__init__(scene)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setWindowTitle(self.tr("Image Viewer"))
        self.setWindowIcon(APP_ICON)
        self.setFrameShape(self.NoFrame)
        scene.setBackgroundBrush(QtCore.Qt.black)
        
        self.dropping = DroppingThread(self)
        self.dropping.loaded_archive.connect(self.load_dropped_archive)
 
        self.label = QtGui.QLabel(self.tr('Nothing to show<br \>Open an image archive'),self)
        self.label.setStyleSheet(self.label_css)
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
        self.imgQ = None
        self.settings = Settings.settings
        self._build_scaling_list()
                        
        actions = {}
        actions['open'] = QtGui.QAction(self.tr("&Open"), self,
                        shortcut=QtGui.QKeySequence.Open,
                        statusTip=self.tr("Open a new file"), 
                        triggered=self.action_open)
        actions['settings'] = QtGui.QAction(self.tr("&Settings"), self,
                        shortcut=QtGui.QKeySequence(QtCore.Qt.Key_S),
                        statusTip=self.tr("Open Settings"), 
                        triggered=self.action_settings)
        actions['webparser'] = QtGui.QAction(self.tr("&Web Parser"), self,
                        shortcut=QtGui.QKeySequence(QtCore.Qt.Key_W),
                        statusTip=self.tr("Settings for web parser"), 
                        triggered=self.action_web_profile)
        actions['reload'] = QtGui.QAction(self.tr("Reload Archive"), self,
                         shortcut=QtGui.QKeySequence.Refresh,
                         statusTip=self.tr("Reload the current Archive"), 
                         triggered=self.action_reload)
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
                         
        self.writing = []
        self.auto_writing = set()
        self.last_farchinfo = None
        actions['save'] = QtGui.QAction(self.tr("Save as..."), self,
                         shortcut=QtGui.QKeySequence.Save,
                         statusTip=self.tr("Close Viewer"), 
                         triggered=self.action_save)
        for i in xrange(1, 10):
            ckey = getattr(QtCore.Qt, 'Key_%d' % i)
            caction = QtGui.QAction(self.tr("Append current image"), self,
                      shortcut=QtGui.QKeySequence(ckey),
                      triggered=partial(self.action_save_current, i-1))
            actions['append_to_%d' % i] = caction
            caction = QtGui.QAction(self.tr("Automatically append current image"), self,
                      checkable=True,
                      triggered=partial(self.action_save_auto, i-1))
            actions['auto_%d' % i] = caction
            caction = QtGui.QAction(self.tr("Close"), self,
                      triggered=partial(self.action_save_close, i-1))
            actions['close_%d' % i] = caction


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
        
    def load_dropped_archive(self):
        farch, errmsg = self.dropping.pop_archive()
        self.open_archive(farch,errmsg)
            
    def load_archive(self, path, page=0):
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
            farch = open_wrapper(path)
            errormsg = None
        except WrapperIOError as err:
            farch = None
            errormsg = text_type(err) or "Unknown Error"
        
        return self.open_archive(farch, errormsg, page)
            
    def open_archive(self, farch, errormsg,page=0):
        try:
            if farch is None:
                raise WrapperIOError(errormsg)
                
            imagelist = farch.filter_images()
            path, name = os.path.split(farch.path)

            if len(imagelist) == 0:
                raise WrapperIOError('No images found in "%s"') % name
                    
            self.clearBuffers()
            self.farch = farch
            self.imagelist = imagelist
            if page < len(imagelist):
                self.cur = page
            else:
                self.cur = 0
            scene = self.scene()
            scene.clear()
            scene.setSceneRect(0,0,10,10)
            self.setWindowTitle('%s - %s' % (name, self.tr("Image Viewer")))
            self.action_queued_image(self.cur,self._mv_start)
                
        except WrapperIOError as err:
            errormsg = text_type(err) or self.tr("Unknown Error")
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.settings.longtimeout)

    def prepare_image(self,fileinfo):
        try:
            with self.farch.open(fileinfo,'rb') as fin:
                img = Image.open(fin)
                width, height = img.size
                ratio = width/height
                view_rect = self.viewport().rect()
                swidth, sheight = view_rect.width(), view_rect.height()
                move_h = int(swidth*(100-self.settings.overlap)/100)
                move_v = int(sheight*(100-self.settings.overlap)/100)
                origsize = width, height
                
                cratio, defwidth, defheight = self.scaling_list[0]
                best_match = abs(math.log(ratio/cratio))
                for cratio, cwidth, cheight in self.scaling_list[1:]:
                    cmatch = abs(math.log(ratio/cratio))
                    if cmatch < best_match:
                        defwidth = cwidth
                        defheight = cheight
                        best_match = cmatch
                
                if defwidth > 0:
                    width_scale = defwidth / width
                else:
                    width_scale = float('inf')
                
                if defheight > 0:
                    height_scale = defheight / height
                else:
                    height_scale = float('inf')
                
                if abs(math.log(height_scale)) < abs(math.log(width_scale)):
                    scale = height_scale
                else:
                    scale = width_scale
                
                if scale > (self.settings.maxscale/100):
                    scale = self.settings.maxscale/100
                elif scale < (self.settings.minscale/100):
                    scale = self.settings.minscale/100
                    
                width = int(width*scale)
                height = int(height*scale)
                
                requiredperc = self.settings.requiredoverlap/100.0
                wdiff = width-swidth
                hdiff = height-sheight
                if wdiff > 0 and (wdiff%move_h) < requiredperc*swidth:
                    width = int(swidth+int(wdiff/move_h)*move_h)
                    height = int(width/ratio)
                elif hdiff > 0 and (hdiff%move_v) < requiredperc*sheight:
                    height = int(sheight+int(hdiff/move_v)*move_v)
                    width  = int(height*ratio)
                
                csize = width, height
                if csize == origsize:
                    img = img.convert('RGB')
                elif csize[0] > .5*origsize[0]:
                    img = img.convert('RGB').resize(csize,Image.ANTIALIAS)
                else:
                    img.thumbnail(csize,Image.ANTIALIAS)
                    img = img.convert('RGB')
                    
            img.origsize = origsize
            err_msg = ''
        except IOError as err:
            img, err_msg = None, text_type(err) or 'Unkown Error'
            
        return img, err_msg
            
        
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
            
            for farch in self.auto_writing:
                self.action_save_current(self.writing.index(farch))
            
            if was_empty:
                self.label.hide()
                self.action_info()
                self.labeltimer.start(self.settings.longtimeout)
            else:
                self.label.setText("%d/%d" % (self.cur+1,len(self.imagelist)))
                self.label.resize(self.label.sizeHint())
                self.label.show()
                self.labeltimer.start(self.settings.shorttimeout)
        else:
            img = cgi.escape(img)
            text = "%d/%d<br />%s" % (self.cur+1,len(self.imagelist),img)
            self.imgQ = None
            self.label.setText(text)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            scene.setSceneRect(0,0,10,10)
        
    def hide_label(self):
        self.actions['info'].setChecked(QtCore.Qt.Unchecked)
        self.label.hide()
        self.labeltimer.stop()
        
    def resize_view(self):
        self.resizetimer.stop()
        self.clearBuffers()
        if self.imagelist:
            self.action_queued_image(self.cur,self._mv_start)
        
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        menu.addAction(self.actions['open'])

        sv_menu = menu.addMenu(self.tr('Save'))
        for i, farch in enumerate(self.writing):
            base, filename = os.path.split(farch.path)
            c_menu = sv_menu.addMenu(filename)
            c_append = self.actions['append_to_%d' % (i+1)]
            c_auto = self.actions['auto_%d' % (i+1)]
            c_auto.setChecked(farch in self.auto_writing)
            c_close = self.actions['close_%d' % (i+1)]
            c_menu.addAction(c_append)
            c_menu.addAction(c_auto)
            c_menu.addAction(c_close)
        sv_menu.addAction(self.actions['save'])
            
        menu.addAction(self.actions['prev_file'])
        menu.addAction(self.actions['reload'])
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
        menu.addAction(self.actions['webparser'])
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
            path = text_type(url.toLocalFile() or url.toString())
            self.dropping.set_path(path).start()
            
            labelstr = u'Loading "%s"' % path
            self.label.setText(labelstr)
            self.label.resize(self.label.sizeHint())
            self.label.show()

        else:
            super(ImageViewer,self).dropEvent(event)

    def mouseDoubleClickEvent(self,e):
        self.action_next()
        
    def resizeEvent(self,e):
        if e.oldSize().isValid():
            self.resizetimer.start(100)
        super(ImageViewer,self).resizeEvent(e)
        
    def clearBuffers(self):
        for worker in itervalues(self.workers):
            worker.terminate()
        self.workers.clear()
        self.buffer.clear()
        
    def closeEvent(self,e):
        self.save_settings()
        if self.farch:
            self.farch.close()
            
        for farch in self.writing:
            farch.close()
        
        self.clearBuffers()
        super(ImageViewer,self).closeEvent(e)
        
    def action_queued_image(self,pos,center=None):
        existing = set(self.workers)|set(self.buffer)
        preloading = set(range(self.cur+1,self.cur+self.settings.preload+1))
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
            loading = ','.join(text_type(p+1) for p in sorted(self.workers))
            params = self.cur+1, len(self.imagelist), loading
            text = self.tr('%d/%d<br />Loading %s ...') % params
            self.label.setText(text)
            self.label.resize(self.label.sizeHint())
            self.label.show()

        if pos == self.cur and pos in self.buffer:
            self.display_image(self.buffer[pos],center)
            
        if len(self.buffer) > self.settings.buffernumber:
            # .25 makes sure images before the current one get removed first
            # if they have the same distance to the image
            key = lambda x: abs(self.cur-x+.25)
            srtpos = sorted(set(self.buffer)-preloading,key=key)
            for pos in srtpos[self.settings.buffernumber:]:
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
            
    def action_save(self):
        if len(self.writing) >= 9:
            return
        archives = '*.zip'
        auto_add = False
        fpath = '/'
        if self.last_farchinfo is not None:
            fpath, auto_add = self.last_farchinfo
        elif self.farch:
            fpath, name = os.path.split(self.farch.path)

        path, dummy = QtGui.QFileDialog.getSaveFileName(self,
                                                        dir=fpath,
                                                        filter=archives)
        if path:
            try:
                farch = ArchiveWrapper(path, 'w')
                self.writing.append(farch)
                if auto_add:
                    self.auto_writing.add(farch)
            except WrapperIOError as err:
                errormsg = text_type(err) or self.tr("Unkown Error")
                errormsg = cgi.escape(errormsg)
                self.label.setText(errormsg)
                self.label.resize(self.label.sizeHint())
                self.label.show()
                self.labeltimer.start(self.settings.longtimeout)

    def action_save_current(self, archive_ind):
        if archive_ind >= self.writing:
            return
        elif (not self.imagelist) or (self.cur >= len(self.imagelist)):
            return
        
        base, filename = os.path.split(self.imagelist[self.cur].filename)
        #remove trailing part seperated by ?
        filename = filename.split('?')[0].strip()
        img = self.buffer.get(self.cur, None)
        farch = self.writing[archive_ind]
        if isinstance(img, Image.Image) and filename not in farch:
            with farch.open(filename, 'w') as fout:
                img.save(fout,'jpeg',quality=self.settings.write_quality,
                                     optimize=self.settings.write_optimize,
                                     progressive=self.settings.write_progressive)
            self.label.setText('Save %r to %r' % (filename, farch.path))
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.settings.longtimeout)
            
    def action_save_auto(self, archive_ind):
        if archive_ind >= self.writing:
            return
            
        farch = self.writing[archive_ind]
        
        if farch in self.auto_writing:
            self.auto_writing.remove(farch)
        else:
            self.auto_writing.add(farch)

    def action_save_close(self, archive_ind):
        if archive_ind >= self.writing:
            return
            
        farch = self.writing.pop(archive_ind)

        if farch in self.auto_writing:
            self.auto_writing.remove(farch)
            self.last_farchinfo = farch.path, True
        else:
            self.last_farchinfo = farch.path, False

        farch.close()

    def action_web_profile(self):
        dialog = WebProfileSettings(self)
        dialog.exec_()

    def action_settings(self):
        dialog = Settings(self.settings, self)
        if dialog.exec_():
            osettings = self.settings
            self.settings = dialog.settings
            self._build_scaling_list()
                
            if osettings.bgcolor != self.settings.bgcolor:
                self.scene().setBackgroundBrush(self.settings.bgcolor)
                
            if osettings.scaling != self.settings.scaling or \
               osettings.minscale != self.settings.minscale or \
               osettings.maxscale != self.settings.maxscale or \
               osettings.overlap != self.settings.overlap or \
               osettings.requiredoverlap != self.settings.requiredoverlap:
                self.clearBuffers()
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
            a_tag = '<br \><a href="%s"><span style="color:white;">%s</span></a>'
            labelstr = u'%d/%d' % (self.cur+1,len(self.imagelist))
            if self.imgQ:
                size = self.imgQ.size()
                tpl = self.imgQ.origsize + (size.width(), size.height())
                fmt = u'<br />%d \u2715 %d \u21D2 %d \u2715 %d'
                labelstr += fmt % tpl
            if hasattr(zi, 'image_url'):
                labelstr += a_tag % (zi.image_url, zi.filename)
            else:
                labelstr += u'<br />%s' % zi.filename

            if hasattr(zi, 'page_url'):
                labelstr += a_tag % (zi.page_url,zi.page_url)
            else:
                path, archname = os.path.split(self.farch.path)
                labelstr += '<br \>%s' % archname
                
            if self.workers:
                loading = ','.join(text_type(p+1) for p in sorted(self.workers))
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
            
    def action_reload(self):
        if isinstance(self.farch,WebWrapper):
            path = self.imagelist[self.cur].page_url
            self.dropping.set_path(path).start()
            labelstr = u'Loading "%s"' % path
            self.label.setText(labelstr)
            self.label.resize(self.label.sizeHint())
            self.label.show()
        elif self.farch:
            self.load_archive(self.farch.path,self.cur)

    def action_next_file(self):
        errormsg = ''
        if self.farch:
            archlist,loadindex = self.farch.list_archives()
            folder, name = os.path.split(self.farch.path)
                
            loadindex += 1
            while loadindex < len(archlist) and \
              not self.load_archive(archlist[loadindex]):
                loadindex += 1  
                    
            if loadindex >= len(archlist):
                errormsg = self.tr('No further archives in "%s"') % folder 

        if errormsg:
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.settings.longtimeout)
            
    
    def action_prev_file(self):
        errormsg = ''
        if self.farch:
            archlist,loadindex = self.farch.list_archives()
            folder, name = os.path.split(self.farch.path)
                
            loadindex -= 1
            while loadindex >= 0 and not self.load_archive(archlist[loadindex]):
                loadindex -= 1  
                    
            if loadindex < 0:
                errormsg = self.tr('No previous archives in "%s"') % folder

        if errormsg:
            errormsg = cgi.escape(errormsg)
            self.label.setText(errormsg)
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.settings.longtimeout)
            
        
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
            self.labeltimer.start(self.settings.longtimeout)
        
    def action_prev_image(self):
        if self.imagelist and self.cur > 0:
            self.cur -= 1
            self.action_queued_image(self.cur,self._mv_end)
        elif self.imagelist:
            self.label.setText(self.tr("No previous images in this archive"))
            self.label.resize(self.label.sizeHint())
            self.label.show()
            self.labeltimer.start(self.settings.longtimeout)
            
    def action_next(self):
        view_rect = self.viewport().rect()
        view_rect = self.mapToScene(view_rect).boundingRect()
        scene_rect = self.sceneRect()
        move_h = int(view_rect.width()*(100-self.settings.overlap)/100)
        move_v = int(view_rect.height()*(100-self.settings.overlap)/100)
        
        step = self._mv_next(scene_rect,view_rect,move_h,move_v)
        if step:
            self.centerOn(view_rect.center()+step)
        else:
            self.action_next_image()

    def action_prev(self):
        view_rect = self.viewport().rect()
        view_rect = self.mapToScene(view_rect).boundingRect()
        scene_rect = self.sceneRect()
        move_h = int(view_rect.width()*(100-self.settings.overlap)/100)
        move_v = int(view_rect.height()*(100-self.settings.overlap)/100)
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
        csettings = self.settings._asdict()
        for key, value in iteritems(csettings):
            settings.setValue(key, value)
        settings.endGroup()
        settings.beginGroup("WebProfiles")
        for key,val in WebWrapper.profiles.items():
            values = repr(tuple(val[key] for key in WebWrapper.profile_keys))
            settings.setValue(key,values)
        settings.endGroup()        

        if self.settings.saveposition and self.imagelist:
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
        csettings = self.settings._asdict()
        for key, defvalue in iteritems(csettings):
            value = settings.value(key, defvalue)
            if defvalue is not None:
                value = type(defvalue)(value)
            csettings[key] = value
        self.settings = Settings.dict2tuple(csettings)
        self._build_scaling_list()
        settings.endGroup()

        self.scene().setBackgroundBrush(self.settings.bgcolor)
        
        for key,(s,e,n,p) in iteritems(self.movement):
            if n.__name__ == movement:
                self.action_movement(key)
                break
        
        settings.beginGroup("WebProfiles")
        for profile in settings.childKeys():
            values = literal_eval(settings.value(profile))
            prof = dict(zip(WebWrapper.profile_keys, values))
            if len(values) == len(WebWrapper.profile_keys):
                WebWrapper.profiles[profile] = prof
        settings.endGroup()        

        if self.settings.saveposition:
            settings.beginGroup("History")
            path = settings.value("lastpath",'')
            pos = settings.value("lastpage",0)
            if path:
                self.load_archive(path,pos)
            
        if isFullscreen:
            self.actions['fullscreen'].setChecked(QtCore.Qt.Checked)
        return isFullscreen
        
    def _build_scaling_list(self):
        scaling_list = []
        for line in self.settings.scaling.split('\n'):
            line = line.strip()
            match = self.re_scaling.match(line)
            if match:
                iw, ih, w, h = match.groups()
                nscaling = self.Scaling(float(iw)/float(ih), int(w), int(h))
                scaling_list.append(nscaling)
        self.scaling_list = sorted(scaling_list)
    

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
    
