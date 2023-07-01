#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    QtCore.Signal = QtCore.pyqtSignal
except ImportError:
    from PyQt4 import QtCore, QtGui
    from PyQt4 import QtGui as QtWidgets
    QtCore.Signal = QtCore.pyqtSignal

import os,re,html
import math
import traceback
from ast import literal_eval
from six import text_type, itervalues, iteritems, reraise
from six.moves import range
from functools import partial
from collections import namedtuple
from wrapper import KNOWN_ARCHIVES, WrapperIOError
from wrapper.archive import ArchiveWrapper
from wrapper.pdf import PdfWrapper
from wrapper.web import WebWrapper
from movers import known_movers
from pathlib import Path
import PIL.Image as Image
import PIL.ImageQt as ImageQt


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


class WebProfileSettings(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # setGeometry(x_pos, y_pos, width, height)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        #self.setGeometry(300, 200, 570, 450)
        #self.setWindowTitle(self.tr("Parser"))
        self.setFixedWidth(400)

        profile = QtWidgets.QComboBox(self,editable=True)
        page_url = QtWidgets.QLineEdit(self)
        img_url = QtWidgets.QLineEdit(self)
        next_url = QtWidgets.QLineEdit(self)

        profile.activated.connect(self.load_profile)
        profile.addItems(list(WebWrapper.profiles.keys()))
        page_url.editingFinished.connect(self.update_profile)
        img_url.editingFinished.connect(self.update_profile)
        next_url.editingFinished.connect(self.update_profile)

        page_url.setToolTip(self.tr("A regular expresion."))
        img_url.setToolTip(self.tr("CSS Selector for image element."))
        next_url.setToolTip(self.tr("CSS Selector for next page link."))

        cancel_btn = QtWidgets.QPushButton(self.tr("&Cancel"),self)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QtWidgets.QPushButton(self.tr("&OK"),self)
        ok_btn.clicked.connect(self.accept)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(ok_btn)
        hbox.addWidget(cancel_btn)

        layout = QtWidgets.QFormLayout()
        layout.addRow(self.tr("&Profile:"),profile)
        layout.addRow(self.tr("&Url:"),page_url)
        layout.addRow(self.tr("&Image filter:"),img_url)
        layout.addRow(self.tr("&Next url filter:"),next_url)

        if 'bs4' not in sys.modules:
            label = QtWidgets.QLabel(self.tr("Could not load BeautifulSoup4. "\
                                         "'Only defaut webparser available."))
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
            if profile not in self.profiles:
                self.profile.addItem(profile)
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


class Settings(QtWidgets.QDialog):
    settings = {'shorttimeout':1000,'longtimeout':2000, 'requiredoverlap':50,
                'preload':5,'buffernumber':10,
                'bgcolor': QtGui.QColor(QtCore.Qt.white),
                'saveposition':0,'overlap':20,'maxscale':200,
                'minscale':20, 'write_quality': 80, 'write_optimize':1,
                'write_progressive':1,
                'merge_threshold':50,
                'scaling':'1000x1600=>0x1600\n1000x2200=>900x0',
                'webcache': ''}
    Tuple = namedtuple('Settings', settings.keys())
    settings = Tuple(**settings)

    def __init__(self, settings, parent=None):
        super().__init__(parent=parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        #self.resize(640, 80)

        self.mergethreshold = QtWidgets.QLineEdit(self)
        self.preload = QtWidgets.QLineEdit(self)
        self.buffernumber = QtWidgets.QLineEdit(self)
        self.scaling = QtWidgets.QTextEdit(self)
        self.maxscale = QtWidgets.QLineEdit(self)
        self.minscale = QtWidgets.QLineEdit(self)
        self.shorttimeout = QtWidgets.QLineEdit(self)
        self.longtimeout = QtWidgets.QLineEdit(self)
        self.requiredoverlap = QtWidgets.QLineEdit(self)
        self.overlap = QtWidgets.QLineEdit(self)
        self.saveposition = QtWidgets.QCheckBox(self.tr("S&ave Position"),self)
        self.webcache = QtWidgets.QLineEdit(self)

        self.mergethreshold.setValidator(QtGui.QIntValidator())
        self.preload.setValidator(QtGui.QIntValidator())
        self.buffernumber.setValidator(QtGui.QIntValidator())
        self.shorttimeout.setValidator(QtGui.QIntValidator())
        self.longtimeout.setValidator(QtGui.QIntValidator())
        self.maxscale.setValidator(QtGui.QIntValidator())
        self.minscale.setValidator(QtGui.QIntValidator())
        self.requiredoverlap.setValidator(QtGui.QIntValidator())
        self.overlap.setValidator(QtGui.QIntValidator())

        self.mergethreshold.setToolTip(self.tr("Defines the maximal pixel "\
             "under which images are merged to remove diplicate sections"))
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
        self.webcache.setToolTip(self.tr("The folder into which all downloaded "
             "images will be stored. If the path is empty or does not exist "
             "the downloaded images will not be stored on the hard drive."))

        self.cancelbuttom = QtWidgets.QPushButton(self.tr("Cancel"), self)
        self.cancelbuttom.clicked.connect(self.reject)
        self.okbuttom = QtWidgets.QPushButton(self.tr("OK"), self)
        self.okbuttom.clicked.connect(self.accept)
        self.bgcolor_btm = QtWidgets.QPushButton('', self)
        self.bgcolor_btm.clicked.connect(self.select_color)
        self.webcache_btm = QtWidgets.QPushButton('Web Cache', self)
        self.webcache_btm.clicked.connect(self.select_webcache)

        self.setTabOrder(self.saveposition,self.scaling)
        self.setTabOrder(self.scaling,self.minscale)
        self.setTabOrder(self.minscale,self.maxscale)
        self.setTabOrder(self.maxscale,self.mergethreshold)
        self.setTabOrder(self.mergethreshold,self.overlap)
        self.setTabOrder(self.overlap,self.requiredoverlap)
        self.setTabOrder(self.requiredoverlap,self.preload)
        self.setTabOrder(self.preload,self.buffernumber)
        self.setTabOrder(self.buffernumber,self.shorttimeout)
        self.setTabOrder(self.shorttimeout,self.longtimeout)
        self.setTabOrder(self.longtimeout,self.bgcolor_btm)
        self.setTabOrder(self.bgcolor_btm,self.webcache_btm)
        self.setTabOrder(self.webcache_btm,self.webcache)
        self.setTabOrder(self.webcache,self.okbuttom)
        self.setTabOrder(self.okbuttom,self.cancelbuttom)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(self.okbuttom)
        hbox.addWidget(self.cancelbuttom)

        layout = QtWidgets.QFormLayout()
        layout.addRow(self.saveposition)
        layout.addRow(self.tr("Scalin&g:"),self.scaling)
        layout.addRow(self.tr("M&in. Scale (%):"),self.minscale)
        layout.addRow(self.tr("M&an. Scale (%):"),self.maxscale)
        layout.addRow(self.tr("Merge &Threshold:"),self.mergethreshold)
        layout.addRow(self.tr("Movement &Overlap (%):"),self.overlap)
        layout.addRow(self.tr("&Optimzed Overlap (%):"),self.requiredoverlap)
        layout.addRow(self.tr("&Preload Number:"),self.preload)
        layout.addRow(self.tr("&Buffer Number:"),self.buffernumber)
        layout.addRow(self.tr("&Short Timeout (ms):"),self.shorttimeout)
        layout.addRow(self.tr("&Long Timeout (ms):"),self.longtimeout)
        layout.addRow(self.tr("Background &Colorr:"),self.bgcolor_btm)
        layout.addRow(self.webcache_btm, self.webcache)
        layout.addRow(hbox)

        self.setLayout(layout)

        self.mergethreshold.setText(text_type(settings.merge_threshold))
        self.preload.setText(text_type(settings.preload))
        self.buffernumber.setText(text_type(settings.buffernumber))
        self.scaling.setText(text_type(settings.scaling))
        self.maxscale.setText(text_type(settings.maxscale))
        self.minscale.setText(text_type(settings.minscale))
        self.shorttimeout.setText(text_type(settings.shorttimeout))
        self.longtimeout.setText(text_type(settings.longtimeout))
        self.overlap.setText(text_type(settings.overlap))
        self.requiredoverlap.setText(text_type(settings.requiredoverlap))
        self.webcache.setText(text_type(settings.webcache))
        if settings.saveposition:
            self.saveposition.setCheckState(QtCore.Qt.Checked)

        self.bgcolor = settings.bgcolor or QtGui.QColor(QtCore.Qt.white)
        fmt = "QPushButton { background-color : rgba(%d,%d,%d,%d)}"
        style = fmt % self.bgcolor.getRgb()
        self.bgcolor_btm.setStyleSheet(style)

    def accept(self):
        settings = {}
        settings['merge_threshold'] = int(self.mergethreshold.text())
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
        settings['webcache'] = self.webcache.text()
        self.settings = self.dict2tuple(settings)
        super(Settings,self).accept()

    def select_color(self):
        self.bgcolor = QtWidgets.QColorDialog.getColor(self.bgcolor,self)
        fmt = "QPushButton { background-color : rgba(%d,%d,%d,%d)}"
        style = fmt % self.bgcolor.getRgb()
        self.bgcolor_btm.setStyleSheet(style)

    def select_webcache(self):
        dialog = QtWidgets.QFileDialog(self)
        dialog.setFileMode(dialog.Directory)
        dialog.setViewMode(dialog.Detail)
        if dialog.exec_():
            self.webcache.setText(dialog.directory().path())

    @classmethod
    def dict2tuple(cls, settings):
        cdict = cls.settings._asdict()
        cdict.update(settings)
        return cls.Tuple(**cdict)

class PageSelect(QtWidgets.QDialog):
    def __init__(self,parent=None):
        super().__init__(parent=parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(QtCore.Qt.Dialog|QtCore.Qt.FramelessWindowHint)
        self.resize(640, 80)
        self.imagelist = []

        self.page = QtWidgets.QLineEdit(self)
        self.page.setMaximumWidth(50)
        self.page.setValidator(QtGui.QIntValidator())
        self.page.setAlignment(QtCore.Qt.AlignCenter)
        self.page.textChanged.connect(self.set_value)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal,self)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(self.slider.TicksBelow)
        self.slider.setMinimum(1)
        self.slider.valueChanged.connect(self.set_value)
        self.okbuttom = QtWidgets.QPushButton(self.tr("OK"),self)
        self.okbuttom.clicked.connect(self.accept)
        self.cancelbuttom = QtWidgets.QPushButton(self.tr("Cancel"),self)
        self.cancelbuttom.clicked.connect(self.reject)

        self.label = QtWidgets.QLabel(self)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.slider)
        layout.addWidget(self.page)

        mlayout = QtWidgets.QGridLayout()
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
            elided = metric.elidedText(text,QtCore.Qt.ElideLeft,
                                       self.label.width())
            self.label.setText(elided)
        except ValueError:
            pass

        self.value = self.slider.value()-1

class WorkerThread(QtCore.QThread):
    loaded = QtCore.Signal(int)

    def __init__(self, manager, pos):
        super().__init__(manager.viewer)
        self.manager = manager
        self.fileinfo = manager.imagelist[pos]
        self.pos = pos
        self.error = ''
        self.img = None
        self.origsize = None
        self.tops = []
        self.bottoms = []
        # necessary to remove handle in viewer
        self.finished.connect(self.removeParent)

    def run(self):
        try:
            data = self.manager.prepare_image(self.fileinfo, self.pos)
            for k, v in data.items():
                setattr(self, k, v)
        except WrapperIOError as err:
            self.error = str(err)
        except IOError as err:
            self.error = str(err) or 'Unknown Image Loading Error'
        except Exception:
            self.error = traceback.format_exception(*sys.exc_info())

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
        if isinstance(self.errmsg, tuple):
            reraise(*self.errmsg)
        elif self.farch is None:
            raise WrapperIOError(self.errmsg or 'Unknown Error')

        farch = self.farch
        self.farch = None
        self.errmsg = ''
        return farch

    def run(self):
        try:
            self.farch = open_wrapper(self.path)
            self.errmsg = None
        except WrapperIOError as err:
            self.farch = None
            self.errmsg = str(err) or "Unknown Error"
        except Exception:
            self.farch = None
            self.errmsg = sys.exc_info()

        self.loaded_archive.emit()


class InfoBox(QtWidgets.QLabel):
    HIDDEN = 0
    PAGE = 1
    INFO = 2
    ERROR = 3

    empty_label_str = 'Nothing to show. Open an image archive'
    label_css = """
QLabel {
    background-color : black;
    color : white;
    padding: 5px 5px 5px 5px;
    border-radius: 5px;
}
"""
    def __init__(self, parent):
        super().__init__(self.empty_label_str, parent)
        self.setStyleSheet(self.label_css)
        self.setOpenExternalLinks(True)
        self.setTextFormat(QtCore.Qt.RichText)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.hide)
        self.type = self.HIDDEN

    def setInfo(self, info):
        self.setText(self._format(info))
        self.resize(self.sizeHint())

    def show(self, type, info, timeout=None):
        self.type = type
        self.setInfo(info)
        super().show()
        if timeout is not None:
            self.timer.start(timeout)
        else:
            self.timer.stop()

    def hide(self):
        super().hide()
        self.type = self.HIDDEN

    @classmethod
    def _format(cls, infos):
        if isinstance(infos, str):
            return infos
        labels = []
        if 'page' in infos and 'page_count' in infos:
            labels.append(f'{infos["page"]+1}/{infos["page_count"]}')

        if 'size' in infos and 'origsize' in infos:
            ow, oh = infos['origsize']
            nw, nh = infos['size']
            labels.append(f'{ow} \u2715 {oh} \u21D2 {nw} \u2715 {nh}')

        if 'image_url' in infos:
            url = html.escape(infos['image_url'])
            fn = html.escape(infos['filename'])
            txt = f'<a href="{url}"><span style="color:white;">{fn}</span></a>'
            labels.append(txt)
        elif 'filename' in infos:
            labels.append(infos['filename'])

        if 'page_url' in infos:
            url = html.escape(infos['page_url'])
            txt = f'<a href="{url}"><span style="color:white;">{url}</span></a>'
            labels.append(txt)
        elif 'archname' in infos:
            labels.append(html.escape(infos['archname']))

        if 'status' in infos:
            labels.append(html.escape(infos['status']))

        if 'error' in infos and infos['error']:
            # if the status was empty drop it again when errors are there
            # take its place
            if not labels[-1]:
                labels.pop()
            error = infos['error']
            if isinstance(error, list):
                errmsg = html.escape('\n'.join(error))
                labels.append(f'<pre>{errmsg}</pre>')
            else:
                labels.append(html.escape(error))

        return '<br />'.join(labels)


class ImageManager(QtCore.QObject):
    DATA_IND = 0
    DATA_SIZE = 1
    DATA_ORIGSIZE = 2
    DATA_TOPS = 3
    DATA_BOTTOMS = 4
    Scaling = namedtuple('Scaling', ['ratio', 'width', 'height'])
    re_scaling = re.compile(r'(?P<iwidth>\d+)\s*x\s*(?P<iheight>\d+)\s*'\
                            r'=\>\s*(?P<width>\d+)\s*x\s*(?P<height>\d+)')
    page_changed = QtCore.Signal(int, int, str)
    info_changed = QtCore.Signal(int)
    view_changed = QtCore.Signal()

    def __init__(self, viewer, settings):
        super().__init__()
        movers = [m(viewer) for m in known_movers()]
        self.viewer = viewer
        self._scaling_list = []
        self.wrapper = None
        self.workers = {}
        self.imagelist = []
        self._images = dict()
        self._errors = dict()
        self._last_page = None
        self._booktimer = QtCore.QTimer(viewer)
        self._booktimer.timeout.connect(self._update_bookkeeping)
        self._booktimer.setSingleShot(True)

        self._movers = dict((m.name, m) for m in movers)
        self._mover = None
        self._to_show = None

        # set the first mover as the default one
        self.mover = self.movers[0]
        self.settings = settings
        self.set_settings(settings)

        viewer.horizontalScrollBar().valueChanged.connect(self._view_changed)
        viewer.horizontalScrollBar().rangeChanged.connect(self._view_changed)
        viewer.verticalScrollBar().valueChanged.connect(self._view_changed)
        viewer.verticalScrollBar().rangeChanged.connect(self._view_changed)

    def show_page(self, page, anchor='Start'):
        """
        Show the given page of the loaded archive.

        Parameters
        ----------
        page : int
            The zero based index of the page to show.
        anchor : str
            Defines what part of the page to show. Options are 'Start' and
            'End'
        """
        item = self._get_pixmap(page)
        if item is not None :
            if not item.isVisible():
                self._to_show = page
                self._reoder_items()
            self._to_show = None
            if anchor == 'End':
                view_rect = self._mover.last_view(item)
            else:
                view_rect = self._mover.first_view(item)
            self.viewer.centerOn(view_rect.center())
            self.page_changed.emit(page, self.page_count,
                                   self._errors.get(page, ''))
        elif page >= 0 and page < self.page_count:
            self._to_show = page
            self._load_page(page)

    def set_settings(self, settings, continuous=None):
        if continuous is None:
            continuous = self._mover.continuous
        refresh = continuous != self._mover.continuous or \
                  settings.scaling != self.settings.scaling or \
                  settings.minscale != self.settings.minscale or \
                  settings.maxscale != self.settings.maxscale or \
                  settings.overlap != self.settings.overlap or \
                  settings.requiredoverlap != self.settings.requiredoverlap or \
                  settings.merge_threshold != self.settings.merge_threshold

        scaling_list = []
        for line in settings.scaling.split('\n'):
            line = line.strip()
            match = self.re_scaling.match(line)
            if match:
                iw, ih, w, h = match.groups()
                nscaling = self.Scaling(float(iw)/float(ih), int(w), int(h))
                scaling_list.append(nscaling)

        self.settings = settings
        self.scaling_list = sorted(scaling_list)
        self._mover.continuous = continuous
        self._mover.merge_threshold = settings.merge_threshold
        if refresh:
            self.refresh()

    def open_archive(self, wrapper, page=0):
        imagelist = wrapper.filter_images()
        path, name = os.path.split(wrapper.path)

        if len(imagelist) == 0:
            raise WrapperIOError(f'No images found in "{name}"')

        # close old wrapper if one is opened
        self.close()
        self.wrapper = wrapper
        self.imagelist = imagelist
        self.rectlist = [None for zi in self.imagelist]
        self._to_show = page
        self._load_page(page)

    def prepare_image(self, fileinfo, pos):
        """
        Open the image referenced in fileinfo and scale it to the correct
        size. It will also store the image to a cache path if it was downloaded
        from the web and caching is active.

        Parameters
        ----------
        fileinfo : FileInfo
            A fileinfo object of the currently loaded wrapper
        pos : int
            The position of the image in the image list of the current archive.
        """

        with self.wrapper.open(fileinfo, 'rb') as fin:
            if isinstance(self.wrapper, WebWrapper):
                filename = f'{pos + 1:03d}_{fileinfo.filename}'
                self._store_image(filename, fin.getvalue())
            img = Image.open(fin)
            origsize = img.size
            img = self._fit_image(img)
            tops, bottoms = self._mover.segment_image(img)

        return {'img': img, 'origsize': origsize,
                'tops': tops, 'bottoms': bottoms}

    def refresh(self):
        if self:
            page = self._to_show or self.page
            self.clearBuffers()
            self._to_show = page
            self._load_page(page)

    def close(self):
        self.clearBuffers()
        self._last_page = None
        if self.wrapper is not None:
            self.wrapper.close()
            self.wrapper = None
            self.imagelist = []

    def clearBuffers(self):
        for worker in itervalues(self.workers):
            worker.terminate()
        self.workers.clear()
        self.viewer.scene().clear()
        self._images = dict()
        self._errors = dict()
        self._to_show = None

    def get_buffered_image(self, page):
        """
        Return the buffered PIL image of the given page, if availible
        """
        if page in self._images:
            return self._images[page][1]

    def action_first_image(self):
        self.show_page(0, 'Start')

    def action_last_image(self):
        self.show_page(self.page_count-1, 'End')

    def action_next_image(self):
        next_page = self.page + 1
        if next_page < self.page_count:
            self.show_page(next_page, 'Start')
        else:
            self.action_last_image()

    def action_prev_image(self):
        next_page = self.page - 1
        if next_page >= 0:
            self.show_page(next_page, 'End')
        else:
            self.action_first_image()

    def action_next(self):
        next_view, changed = self._mover.next_view(self.settings.overlap)
        self.viewer.centerOn(next_view.center())
        if not changed and not self._mover.continuous:
            self.action_next_image()
        else:
            self.view_changed.emit()

    def action_prev(self):
        next_view, changed = self._mover.prev_view(self.settings.overlap)
        self.viewer.centerOn(next_view.center())
        if not changed and not self._mover.continuous:
            self.action_prev_image()
        else:
            self.view_changed.emit()

    @property
    def movers(self):
        return sorted(self._movers)

    @property
    def mover(self):
        return self._mover.name

    @mover.setter
    def mover(self, name):
        self._mover = self._movers.get(name, self._mover)
        self._reoder_items()

    @property
    def pixmap_item(self):
        view_rect = self.viewer.viewport().rect()
        view_rect = self.viewer.mapToScene(view_rect).boundingRect()
        return self._view_page(view_rect)

    @property
    def page(self):
        item = self.pixmap_item
        if item is None:
            return None
        else:
            return item.data(self.DATA_IND)

    @property
    def page_count(self):
        return len(self.imagelist)

    @property
    def continuous(self):
        return self._mover.continuous

    @property
    def page_description(self):
        infos = {}
        item = self.pixmap_item
        if item is not None:
            page = item.data(self.DATA_IND)
            zi = self.imagelist[page]
            infos['page'] = page
            infos['page_count'] = self.page_count
            infos['error'] = self._errors.get(page, '')
            size = item.data(self.DATA_SIZE)
            if size is not None:
                infos['size'] = tuple(size)
            origsize = item.data(self.DATA_ORIGSIZE)
            if origsize is not None:
                infos['origsize'] = tuple(origsize)

            if hasattr(zi, 'image_url'):
                infos['image_url'] = zi.image_url
            infos['filename'] = zi.filename

            if hasattr(zi, 'page_url'):
                infos['page_url'] = zi.page_url
        elif isinstance(self.wrapper, WebWrapper):
            infos['page_url'] = self.wrapper.path

        if self.wrapper is not None and not isinstance(self.wrapper, WebWrapper):
            infos['archpath'] = self.wrapper.path
            _, infos['archname'] = os.path.split(self.wrapper.path)

        return infos

    @property
    def status_info(self):
        infos = self.page_description
        if self.workers:
            loading = ','.join(text_type(p+1) for p in sorted(self.workers))
            cinfo = f'Loading {loading}'
            infos['status'] = cinfo
        elif self.wrapper is None:
            infos['status'] = InfoBox.empty_label_str
        else:
            infos['status'] = ''
        return infos

    @property
    def loaded_pages(self):
        scene = self.viewer.scene()
        return dict((item.data(self.DATA_IND), item) for item in scene.items())

    @property
    def path(self):
        return self.wrapper.path if self.wrapper is not None else ''

    def _view_changed(self):
        self._booktimer.start(100)

    def _get_pixmap(self, page):
        for item in self.viewer.scene().items():
            if item.data(self.DATA_IND) == page:
                return item

    def _view_page(self, view_rect):
        # search for the item at the center of the provided view_rect
        center_item = None
        center = view_rect.center()
        # no item at the center search for the item with the largest
        # overlap with the view_rect
        max_item = None
        max_surf = 0.0
        for item in self.viewer.scene().items():
            if item.isVisible():
                cur_bb = item.boundingRect()
                intersection = cur_bb & view_rect
                cur_surf = intersection.height() * intersection.width()
                if cur_surf > max_surf:
                    max_item = item
                    max_surf = cur_surf
                if item.contains(center):
                    center_item = item

        return center_item or max_item

    def _fit_image(self, img):
        width, height = img.size
        ratio = width/height
        view_rect = self.viewer.viewport().rect()
        swidth, sheight = view_rect.width(), view_rect.height()
        move_h = int(swidth*(100-self.settings.overlap)/100)
        move_v = int(sheight*(100-self.settings.overlap)/100)
        origsize = width, height

        defwidth, defheight = 0, 0
        best_match = float('inf')
        for cratio, cwidth, cheight in self.scaling_list:
            # do not use all scallings in continues viewer mode
            if cheight == 0 and self._mover.continuous_width:
                continue
            elif cwidth == 0 and self._mover.continuous_height:
                continue

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

        if not self._mover.continuous:
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
            img = img.convert('RGB').resize(csize,Image.LANCZOS)
        else:
            img.thumbnail(csize,Image.LANCZOS)
            img = img.convert('RGB')

        return img

    def _load_page(self, page):
        toload = page+1
        vis_page = self.page
        if vis_page is None:
            vis_page = toload

        if page not in self.loaded_pages and page not in self.workers and \
          page >= 0 and page < len(self.imagelist):
            self.workers[page] = worker = WorkerThread(self, page)
            worker.loaded.connect(self._insert_page)
            worker.start()

        self.info_changed.emit(0)

    def _insert_page(self, page):
        worker = self.workers.pop(page)
        scene = self.viewer.scene()
        error = worker.error
        tops = worker.tops
        bottoms = worker.bottoms

        if worker.img is None:
            size = 10, 10
            image = None
            pixmap = QtGui.QPixmap(*size)
        else:
            try:
                size = worker.img.size
                prevImg = self.get_buffered_image(page - 1)
                worker.img = self._mover.crop_image(worker.img, prevImg)
                image = ImageQt.ImageQt(worker.img)
                pixmap = QtGui.QPixmap.fromImage(image)
                dheight = worker.img.size[1] - size[1]
                tops = [t + dheight for t in tops]
                bottoms = [t + dheight for t in bottoms]
            except MemoryError:
                size = worker.img.size
                image = None
                pixmap = QtGui.QPixmap(*size)
                error = error or ''
                error = f'{error} MemoryError'.strip()

        item = scene.addPixmap(pixmap)
        item.setData(self.DATA_IND, page)
        item.setData(self.DATA_ORIGSIZE, worker.origsize)
        item.setData(self.DATA_SIZE, size)
        item.setData(self.DATA_TOPS, tops)
        item.setData(self.DATA_BOTTOMS, bottoms)
        item.hide()
        self._images[page] = image, worker.img
        self._errors[page] = error
        self._reoder_items()

        if self._to_show == page:
            self._to_show = None
            self.show_page(page)

        self._update_bookkeeping()

    def _update_bookkeeping(self):
        vis_page = self._to_show or self.page
        if vis_page is None:
            return

        loaded_pages = self.loaded_pages
        existing = set(loaded_pages) | set(self.workers)
        preloading = set(range(vis_page+1, vis_page+self.settings.preload+1))
        preloading &= set(range(self.page_count))
        loadcandidate = preloading-existing

        if loadcandidate:
            self._load_page(min(loadcandidate))

        if len(loaded_pages) > self.settings.buffernumber:
            # .25 makes sure images before the current one get removed first
            # if they have the same distance to the image
            scene = self.viewer.scene()
            key = lambda x: abs(vis_page-x+.25)
            srtpos = sorted(set(loaded_pages)-preloading,key=key)
            for pos in srtpos[self.settings.buffernumber:]:
                item = loaded_pages.pop(pos)
                scene.removeItem(item)
                del self._images[pos]

            self._reoder_items()

        if self._last_page is None:
            self.info_changed.emit(1)
        elif self._last_page != vis_page:
            self.page_changed.emit(vis_page, self.page_count,
                                   self._errors.get(vis_page, ''))
        else:
            self.info_changed.emit(0)
        self._last_page = vis_page

    def _reoder_items(self):
        scene = self.viewer.scene()
        view_rect = self.viewer.viewport().rect()
        view_rect = self.viewer.mapToScene(view_rect).boundingRect()
        items = self.loaded_pages
        if self._to_show is not None and self._to_show in items:
            view_page = self._to_show
        else:
            view_page = self.page
        view_item = self.pixmap_item
        if view_item is not None:
            view_shift = view_rect.center() - view_item.boundingRect().center()

        # show all pages directly connected to the currently page in focues
        pages = sorted(items)
        show_pages = {view_page}
        if self._mover.continuous:
            try:
                view_pos = pages.index(view_page)
            except ValueError:
                view_pos = 0
            for cind in pages[view_pos+1:]:
                if (cind-1) in show_pages:
                    show_pages.add(cind)
            for cind in pages[:view_pos][::-1]:
                if (cind+1) in show_pages:
                    show_pages.add(cind)

        scene_rect = QtCore.QRectF(0, 0, 0, 0)
        tops = []
        bottoms = []
        for cind, item in sorted(iteritems(items)):
            if cind in show_pages:
                item_rect = item.boundingRect()
                scene_rect = self._mover.append_item(scene_rect, item_rect)
                item.setOffset(item_rect.topLeft())
                offset = int(item_rect.top())
                for c in item.data(self.DATA_TOPS):
                    tops.append(c + offset)
                for c in item.data(self.DATA_BOTTOMS):
                    bottoms.append(c + offset)

        scene.setSceneRect(scene_rect)
        self._mover.set_segments(tops, bottoms)
        # shift view to show the same section as before the reorder
        if view_item is not None:
            ncenter = view_item.boundingRect().center() + view_shift
            self.viewer.centerOn(ncenter)

        for cind, item in iteritems(items):
            item.setVisible(cind in show_pages)

    def _store_image(self, filename, data):
        base = Path(self.settings.webcache)
        path = Path(base, self.wrapper.filename, filename)
        if self.settings.webcache and base.is_dir() and not path.exists():
            path.parent.mkdir(exist_ok=True)
            with path.open('wb') as f:
                f.write(data)

    def __bool__(self):
        return self.wrapper is not None and self.page is not None

    __nonzero__ = __bool__


class ImageViewer(QtWidgets.QGraphicsView):
    def __init__(self,scene=None):
        super().__init__(scene)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setWindowTitle(self.tr("Image Viewer"))
        self.setWindowIcon(APP_ICON)
        self.setFrameShape(self.NoFrame)
        scene.setBackgroundBrush(QtCore.Qt.black)

        self.dropping = DroppingThread(self)
        self.dropping.loaded_archive.connect(self.load_dropped_archive)

        self.label = InfoBox(self)
        self.label.move(10,10)
        self.label.timer.timeout.connect(self.hide_label)

        self.resizetimer = QtCore.QTimer(self)
        self.resizetimer.timeout.connect(self.resize_view)

        self.pageselect = PageSelect(self)

        self.setAcceptDrops(True)
        self.settings = Settings.settings
        self.manager = ImageManager(self, Settings.settings)
        self.manager.scaling_list = self.settings.scaling
        self.manager.page_changed.connect(self.action_page_info)
        self.manager.info_changed.connect(self.action_status_info)
        # automatically hide the status if it is only a timeout when
        # the view is advanced
        self.manager.view_changed.connect(self.action_autohide)

        actions = {}
        actions = {}
        actions['open'] = QtWidgets.QAction(self.tr("&Open"), self,
                        shortcut=QtGui.QKeySequence.Open,
                        statusTip=self.tr("Open a new file"),
                        triggered=self.action_open)
        actions['settings'] = QtWidgets.QAction(self.tr("&Settings"), self,
                        shortcut=QtGui.QKeySequence(QtCore.Qt.Key_S),
                        statusTip=self.tr("Open Settings"),
                        triggered=self.action_settings)
        actions['webparser'] = QtWidgets.QAction(self.tr("&Web Parser"), self,
                        shortcut=QtGui.QKeySequence(QtCore.Qt.Key_W),
                        statusTip=self.tr("Settings for web parser"),
                        triggered=self.action_web_profile)
        actions['reload'] = QtWidgets.QAction(self.tr("Reload Archive"), self,
                         shortcut=QtGui.QKeySequence.Refresh,
                         statusTip=self.tr("Reload the current Archive"),
                         triggered=self.action_reload)
        actions['next_file'] = QtWidgets.QAction(self.tr("Next Archive"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_L),
                         statusTip=self.tr("Load the next archive in the folder"),
                         triggered=self.action_next_file)
        actions['prev_file'] = QtWidgets.QAction(self.tr("Previous Archive"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_K),
                         statusTip=self.tr("Load the previous archive in the folder"),
                         triggered=self.action_prev_file)
        actions['next'] = QtWidgets.QAction(self.tr("Next View"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_Space),
                         statusTip=self.tr("Show next image part"),
                         triggered=self.manager.action_next)
        actions['prev'] = QtWidgets.QAction(self.tr("Previous View"), self,
                         shortcut=QtGui.QKeySequence("Shift+Space"),
                         statusTip=self.tr("Show previous image part"),
                         triggered=self.manager.action_prev)
        actions['page'] = QtWidgets.QAction(self.tr("Select Page"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_P),
                         statusTip=self.tr("Select the an image"),
                         triggered=self.action_page)
        actions['info'] = QtWidgets.QAction(self.tr("Information"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_I),
                         checkable=True,
                         statusTip=self.tr("Show informaion about image"),
                         triggered=self.action_info)
        actions['first_image'] = QtWidgets.QAction(self.tr("First Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToStartOfLine,
                         statusTip=self.tr("Show first image"),
                         triggered=self.manager.action_first_image)
        actions['last_image'] = QtWidgets.QAction(self.tr("Last Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToEndOfLine,
                         statusTip=self.tr("Show last image"),
                         triggered=self.manager.action_last_image)
        actions['next_image'] = QtWidgets.QAction(self.tr("Next Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToNextPage,
                         statusTip=self.tr("Show next image"),
                         triggered=self.manager.action_next_image)
        actions['prev_image'] = QtWidgets.QAction(self.tr("Previous Image"), self,
                         shortcut=QtGui.QKeySequence.MoveToPreviousPage,
                         statusTip=self.tr("Show previous image"),
                         triggered=self.manager.action_prev_image)
        actions['continuous'] = QtWidgets.QAction(self.tr("Continuous"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_C),
                         checkable=True,
                         statusTip=self.tr("Continuous Flow"),
                         triggered=self.action_toggle_continuous)
        actions['fullscreen'] = QtWidgets.QAction(self.tr("Fullscreen"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_F),
                         checkable=True,
                         statusTip=self.tr("Toggle Fullscreen"),
                         triggered=self.action_toggle_fullscreen)
        actions['minimize'] = QtWidgets.QAction(self.tr("Minimize"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_M),
                         statusTip=self.tr("Minimize Window"),
                         triggered=self.showMinimized)
        actions['close'] = QtWidgets.QAction(self.tr("Close"), self,
                         shortcut=QtGui.QKeySequence(QtCore.Qt.Key_Escape),
                         statusTip=self.tr("Close Viewer"),
                         triggered=self.close)

        self.writing = []
        self.auto_writing = set()
        self.last_farchinfo = None
        actions['save'] = QtWidgets.QAction(self.tr("Save as..."), self,
                         shortcut=QtGui.QKeySequence.Save,
                         statusTip=self.tr("Close Viewer"),
                         triggered=self.action_save)
        for i in range(1, 10):
            ckey = getattr(QtCore.Qt, f'Key_{i}')
            caction = QtWidgets.QAction(self.tr("Append current image"), self,
                      shortcut=QtGui.QKeySequence(ckey),
                      triggered=partial(self.action_save_current, i-1))
            actions[f'append_to_{i}'] = caction
            caction = QtWidgets.QAction(self.tr("Automatically append current image"),
                      self,
                      checkable=True,
                      triggered=partial(self.action_save_auto, i-1))
            actions[f'auto_{i}'] = caction
            caction = QtWidgets.QAction(self.tr("Close"), self,
                      triggered=partial(self.action_save_close, i-1))
            actions[f'close_{i}'] = caction


        actions['movement'] = QtWidgets.QActionGroup(self)
        actions['movement'].triggered.connect(self.action_movement)
        for mover in self.manager.movers:
            act = QtWidgets.QAction(self.tr(mover), actions['movement'],
                                checkable=True)
            if mover == self.manager.mover:
                act.setChecked(True)

        for act in itervalues(actions):
            if isinstance(act, QtWidgets.QAction):
                self.addAction(act)
        self.actions = actions

    def load_dropped_archive(self):
        try:
            farch = self.dropping.pop_archive()
            _, name = os.path.split(farch.path)
            ntitle = f'{name} - Image Viewer'
            self.manager.open_archive(farch)
            self.setWindowTitle(ntitle)

        except WrapperIOError as err:
            errormsg = html.escape(str(err)) or "Unknown Error"
            errormsg = '<br/>'.join(s.strip() for s in errormsg.split('\n'))
            self.label.show(InfoBox.ERROR, errormsg, self.settings.longtimeout)
        except Exception:
            trace = traceback.format_exception(*sys.exc_info())
            errmsg = html.escape('\n'.join(trace))
            errmsg = f'Unexpected Error:<br/><pre>{errmsg}</pre>'
            self.label.show(InfoBox.ERROR, errmsg, self.settings.longtimeout)


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
            _, name = os.path.split(path)
            ntitle = f'{name} - Image Viewer'
            self.manager.open_archive(farch, page)
            self.setWindowTitle(ntitle)
            return True

        except WrapperIOError as err:
            errormsg = text_type(err) or self.tr("Unknown Error")
            errormsg = html.escape(errormsg)
            self.label.show(InfoBox.ERROR, errormsg, self.settings.longtimeout)
            return False

    def hide_label(self):
        self.actions['info'].setChecked(QtCore.Qt.Unchecked)

    def resize_view(self):
        self.resizetimer.stop()
        self.manager.refresh()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.actions['open'])

        sv_menu = menu.addMenu(self.tr('Save'))
        for i, farch in enumerate(self.writing):
            base, filename = os.path.split(farch.path)
            c_menu = sv_menu.addMenu(filename)
            c_append = self.actions[f'append_to_{i+1}']
            c_auto = self.actions[f'auto_{i+1}']
            c_auto.setChecked(farch in self.auto_writing)
            c_close = self.actions[f'close_{i+1}']
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
        menu.addAction(self.actions['continuous'])
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

            labelstr = f'Loading "{path}"'
            self.label.show(InfoBox.INFO, labelstr)

        else:
            super(ImageViewer,self).dropEvent(event)

    def mouseDoubleClickEvent(self,e):
        self.manager.action_next()

    def resizeEvent(self,e):
        if e.oldSize().isValid():
            self.resizetimer.start(100)
        super(ImageViewer,self).resizeEvent(e)

    def closeEvent(self,e):
        self.save_settings()
        self.manager.close()
        for farch in self.writing:
            farch.close()

        super(ImageViewer,self).closeEvent(e)

    def action_open(self):
        archives = ' '.join(f'*{ext}' for ext in ArchiveWrapper.formats)
        dialog = QtWidgets.QFileDialog(self)
        dialog.setFileMode(dialog.ExistingFile)
        dialog.setNameFilter(f"Archives ({archives})")
        dialog.setViewMode(dialog.Detail)
        infos = self.manager.page_description
        if 'archpath' in infos:
            path, name = os.path.split(infos['archpath'])
            dialog.setDirectory(path)
        if dialog.exec_():
            self.load_archive(dialog.selectedFiles()[0])

    def action_save(self):
        if len(self.writing) >= 9:
            return
        archives = '*.zip'
        auto_add = False
        fpath = '/'
        infos = self.manager.page_description
        if self.last_farchinfo is not None:
            fpath, auto_add = self.last_farchinfo
        elif 'archpath' in infos:
            fpath, name = os.path.split(infos['archpath'])

        path, dummy = QtWidgets.QFileDialog.getSaveFileName(self,
                                                            directory=fpath,
                                                            filter=archives)
        if path:
            try:
                farch = ArchiveWrapper(path, 'w')
                self.writing.append(farch)
                if auto_add:
                    self.auto_writing.add(farch)
            except WrapperIOError as err:
                errormsg = text_type(err) or self.tr("Unkown Error")
                errormsg = html.escape(errormsg)
                self.label.show(InfoBox.ERROR, errormsg, self.settings.longtimeout)

    def action_save_current(self, archive_ind):
        infos = self.manager.page_description
        if archive_ind >= len(self.writing) or 'filename' not in infos:
            return

        base, filename = os.path.split(infos['filename'])
        #remove trailing part seperated by ?
        filename = filename.split('?')[0].strip()
        #prepend the page number to ensure correct ordering of images
        filename = f'{infos["page"]:03}_{filename}'
        img = self.manager.get_buffered_image(infos['page'])
        farch = self.writing[archive_ind]

        if isinstance(img, Image.Image) and filename not in farch:
            with farch.open(filename, 'w') as fout:
                img.save(fout,'jpeg',quality=self.settings.write_quality,
                                     optimize=self.settings.write_optimize,
                                     progressive=self.settings.write_progressive)
            text = f'Save "{filename}" to "{farch.path}"'
            self.label.show(InfoBox.INFO, text, self.settings.shorttimeout)

    def action_save_auto(self, archive_ind):
        if archive_ind >= len(self.writing):
            return

        farch = self.writing[archive_ind]

        if farch in self.auto_writing:
            self.auto_writing.remove(farch)
        else:
            self.auto_writing.add(farch)

    def action_save_close(self, archive_ind):
        if archive_ind >= len(self.writing):
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
            self.manager.set_settings(dialog.settings)

            if osettings.bgcolor != self.settings.bgcolor:
                self.scene().setBackgroundBrush(self.settings.bgcolor)

    def action_page(self):
        manager = self.manager
        if manager.imagelist:
            self.pageselect.set_range(manager.page, manager.imagelist)
            if self.pageselect.exec_():
                manager.show_page(self.pageselect.value)

    def action_page_info(self, cur, count, error):
        if self.label.type == InfoBox.INFO:
            self.label.setInfo(self.manager.status_info)
        elif not self.manager.continuous:
            info = f'{cur+1}/{count}'
            if error:
                info = f'{info}<br />{html.escape(error)}'
            self.label.show(InfoBox.PAGE, info, self.settings.shorttimeout)

        for farch in self.auto_writing:
            self.action_save_current(self.writing.index(farch))

    def action_status_info(self, priority):
        # if we have a non zero proority the label has to be shown
        # even if it was invisible before
        if priority > 0:
            isChecked = self.actions['info'].isChecked()
            t = None if isChecked else self.settings.longtimeout
            self.label.show(InfoBox.INFO, self.manager.status_info, timeout=t)
        elif self.label.type == InfoBox.INFO:
            self.label.setInfo(self.manager.status_info)

        for farch in self.auto_writing:
            self.action_save_current(self.writing.index(farch))

    def action_autohide(self):
        if not self.actions['info'].isChecked():
            self.label.hide()

    def action_info(self):
        #show the label when info is active or no data is loaded
        if not self.manager:
            self.label.show(InfoBox.INFO, self.manager.status_info)
        elif self.actions['info'].isChecked():
            self.label.show(InfoBox.INFO, self.manager.status_info)
        else:
            self.label.hide()

    def action_movement(self,action):
        action.setChecked(True)
        self.manager.mover = action.text()

    def action_toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def action_toggle_continuous(self):
        continuous = self.actions['continuous'].isChecked()
        self.manager.set_settings(self.settings, continuous)

    def action_reload(self):
        infos = self.manager.page_description
        if 'page_url' in infos:
            purl = infos['page_url']
            self.dropping.set_path(purl).start()
            self.label.show(InfoBox.INFO, f'Loading "{purl}"')
        elif 'archpath' in infos:
            page = infos.get('page', None)
            path = infos['archpath']
            self.load_archive(path, page)

    def action_next_file(self):
        errormsg = ''
        farch = self.manager.wrapper
        if farch:
            archlist,loadindex = farch.list_archives()
            folder, name = os.path.split(farch.path)

            loadindex += 1
            while loadindex < len(archlist) and \
              not self.load_archive(archlist[loadindex]):
                loadindex += 1

            if loadindex >= len(archlist):
                errormsg = f'No further archives in "{folder}"'

        if errormsg:
            errormsg = html.escape(errormsg)
            self.label.show(InfoBox.ERROR, errormsg, self.settings.longtimeout)


    def action_prev_file(self):
        errormsg = ''
        farch = self.manager.wrapper
        if farch:
            archlist,loadindex = farch.list_archives()
            folder, name = os.path.split(farch.path)

            loadindex -= 1
            while loadindex >= 0 and not self.load_archive(archlist[loadindex]):
                loadindex -= 1

            if loadindex < 0:
                errormsg = f'No previous archives in "{folder}"'

        if errormsg:
            errormsg = html.escape(errormsg)
            self.label.show(InfoBox.ERROR, errormsg, self.settings.longtimeout)

    def save_settings(self):
        isContinuous = self.actions['continuous'].isChecked()

        settings = QtCore.QSettings("Caasar", "Image Viewer")
        settings.beginGroup("MainWindow")
        settings.setValue("fullscreen", self.isFullScreen())
        settings.setValue("continuous", isContinuous)
        if not self.isFullScreen():
            settings.setValue("pos", self.pos())
            settings.setValue("size", self.size())
        settings.setValue("movement", self.manager.mover)
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

        if self.settings.saveposition and self.manager:
            infos = self.manager.page_description
            settings.beginGroup("History")
            if 'page_url' in infos:
                settings.setValue("lastpath", infos['page_url'])
                settings.setValue("lastpage", 0)
            else:
                settings.setValue("lastpath", infos['archpath'])
                settings.setValue("lastpage", infos['page'])
            settings.endGroup()

    def load_settings(self):
        settings = QtCore.QSettings("Caasar", "Image Viewer")
        settings.beginGroup("MainWindow")
        self.resize(settings.value("size",QtCore.QSize(640, 480)))
        self.move(settings.value("pos", QtCore.QPoint(100, 100)))
        isFullscreen = settings.value("fullscreen", 'false') == 'true'
        isContinuous = settings.value("continuous", 'false') == 'true'
        self.manager.mover = settings.value("movement", "")
        for act in self.actions['movement'].actions():
            if act.text() == self.manager.mover:
                act.setChecked(True)
        settings.endGroup()
        settings.beginGroup("Settings")
        csettings = self.settings._asdict()
        for key, defvalue in iteritems(csettings):
            value = settings.value(key, defvalue)
            if defvalue is not None:
                value = type(defvalue)(value)
            csettings[key] = value
        self.settings = Settings.dict2tuple(csettings)
        self.manager.set_settings(self.settings, isContinuous)
        settings.endGroup()

        self.scene().setBackgroundBrush(self.settings.bgcolor)

        settings.beginGroup("WebProfiles")
        for profile in settings.allKeys():
            values = literal_eval(settings.value(profile))
            prof = dict(zip(WebWrapper.profile_keys, values))
            if len(values) == len(WebWrapper.profile_keys):
                WebWrapper.profiles[profile] = prof
        settings.endGroup()

        if self.settings.saveposition:
            settings.beginGroup("History")
            path = settings.value("lastpath",'')
            page = settings.value("lastpage", 0) or 0
            if path:
                self.load_archive(path, page)

        if isFullscreen:
            self.actions['fullscreen'].setChecked(QtCore.Qt.Checked)
        if isContinuous:
            self.actions['continuous'].setChecked(QtCore.Qt.Checked)
        return isFullscreen

    def _update_info(self):
        a_tag = u'<a href="%s"><span style="color:white;">%s</span></a>'
        infos = self.manager.status_info
        labels = []
        if 'page' in infos and 'page_count' in infos:
            data = infos['page']+1, infos['page_count']
            labels.append('%d/%d' % data)

        if 'size' in infos and 'origsize' in infos:
            tpl = infos['origsize'] + infos['size']
            fmt = u'%d \u2715 %d \u21D2 %d \u2715 %d'
            labels.append(fmt % tuple(tpl))

        if 'image_url' in infos:
            url = html.escape(infos['image_url'])
            filename = html.escape(infos['filename'])
            labels.append(a_tag % (url, filename))
        elif 'filename' in infos:
            labels.append(infos['filename'])

        if 'page_url' in infos:
            url = html.escape(infos['page_url'])
            labels.append(a_tag % (url, url))
        elif 'archname' in infos:
            labels.append(html.escape(infos['archname']))

        if 'status' in infos:
            labels.append(html.escape(infos['status']))

        if 'error' in infos and infos['error']:
            # if the status was empty drop it again when errors are there
            # take its place
            if not labels[-1]:
                labels.pop()
            error = infos['error']
            if isinstance(error, list):
                errmsg = html.escape('\n'.join(error))
                labels.append('<pre>%s</pre>' % errmsg)
            else:
                labels.append(html.escape(error))

        self.label.setText('<br />'.join(labels))
        self.label.resize(self.label.sizeHint())


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv[:1])
    APP_ICON = QtGui.QIcon('res/image.png')
    scene = QtWidgets.QGraphicsScene()
    view = ImageViewer(scene)
    if view.load_settings():
        view.showFullScreen()
    else:
        view.show()

    if len(sys.argv) > 1:
        view.load_archive(sys.argv[1])
    sys.exit(app.exec_())
