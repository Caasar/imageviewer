# -*- coding: utf-8 -*-
"""
Created on Mon Nov 13 20:47:28 2017

@author: Caasar
"""
from __future__ import division

#try:
#    from PySide import QtCore
#except ImportError:
#    from PyQt4 import QtCore

INF_POINT = 1000000000

def crop_image(img, prevImg, thr=50.0, min_lines=25, stop_thr=150):
    try:
        import numpy as np
    except ImportError:
        return img

    if thr <= 0.0:
        return img

    assert img.size[0] == prevImg.size[0]
    arr1 = np.asarray(prevImg).astype(np.float)
    arr2 = np.asarray(img).astype(np.float)
    for i in range(arr1.shape[0] - 1, -1, -1):
        if arr1[i].min() < 254:
            break

    start = None
    mindist = np.inf
    dists = []
    for j in range(min_lines, arr2.shape[0]):
        sdist = 0.0
        for offset in range(min_lines):
            cdist = np.abs(arr1[i-offset] - arr2[j-offset]).sum(1).max() / 3
            sdist += cdist
            if cdist > stop_thr:
                sdist = np.inf
                break
        sdist /= min_lines
        dists.append(sdist)
        if sdist < mindist:
            start = j + 1
            mindist = sdist

        if mindist < thr and sdist > thr:
            break
    if start is None:
        for start in range(arr2.shape[0]):
            if arr2[start].min() > 254:
                break

    if start > 0:
        return img.crop((0, start, img.size[0], img.size[1]))
    else:
        return img


class BaseMover(object):
    MaxIRange = 15
    FilterLen = 5
    MinRho = 0.8

    def __init__(self, viewer, name):
        self.viewer = viewer
        self.name = name
        self._continuous = False
        self._merge_threshold = 50.0
        self._tops = []
        self._bottoms = []

    def step_sizes(self, overlap):
        """
        Return the step size in x and y given the overlap in percent.
        """
        view_rect = self.viewer.viewport().rect()
        view_rect = self.viewer.mapToScene(view_rect).boundingRect()
        dx = int(view_rect.width()*(100-overlap)/100)
        dy = int(view_rect.height()*(100-overlap)/100)
        return dx, dy, view_rect, self.viewer.sceneRect()

    def align_view(self, view, scene):
        dx = 0
        if view.width() >= scene.width():
            dx = scene.center().x() - view.center().x()
        elif view.right() > scene.right():
            dx = scene.right() - view.right()
        elif view.left() < scene.left():
            dx = scene.left() - view.left()

        dy = 0
        if view.height() >= scene.height():
            dy = scene.center().y() - view.center().y()
        elif view.bottom() > scene.bottom():
            dy = scene.bottom() - view.bottom()
        elif view.top() < scene.top():
            dy = scene.top() - view.top()

        next_view = view.adjusted(dx, dy, dx, dy)
        prev_view = self.viewer.viewport().rect()
        prev_view = self.viewer.mapToScene(prev_view).boundingRect()
        diff = next_view.center() - prev_view.center()
        diff = diff.x() * diff.x() + diff.y() * diff.y()
        return next_view, diff > 4.0

    def next_view(self, overlap):
        raise NotImplementedError()

    def prev_view(self, overlap):
        raise NotImplementedError()

    def first_view(self, item):
        raise NotImplementedError()

    def last_view(self, item):
        raise NotImplementedError()

    def crop_image(self, img, prevImg):
        if prevImg is not None and self.continuous_height:
            return crop_image(img, prevImg, self._merge_threshold)
        else:
            return img

    def segment_image(self, img):
        if not self._continuous:
            return [], []
        try:
            import numpy as np
            from scipy import ndimage
        except ImportError:
            return [], []

        arr = np.asarray(img.convert('L'))
        # find the intensity range for each row
        arrMin = arr.min(1).astype(np.int16)
        arrMax = arr.max(1).astype(np.int16)
        arrRange = arrMax - arrMin
        # ensure minimal range for each row is >= MaxIRange to ensure
        # a stable calculation of the correlation coeficient
        arrOff = np.maximum(self.MaxIRange - arrRange, 0) // 2
        arrMin -= arrOff
        arrMax += arrOff
        # build the reference intensity range based on the center
        # of the two neighbouring rows
        refCenter = np.empty_like(arrMin)
        refCenter[1:-1] = arrMax[:-2] + arrMax[2:] + arrMin[:-2] + arrMin[2:]
        refCenter >>= 2
        refCenter[0] = (arrMax[1] + arrMin[1]) // 2
        refCenter[-1] = (arrMax[-2] + arrMin[-2]) // 2
        refMin = refCenter - self.MaxIRange // 2
        refMax = refCenter + self.MaxIRange // 2
        # calculate the correlation coeficient rho
        compMin = np.maximum(arrMin, refMin)
        compMax = np.minimum(arrMax, refMax)
        compRange = np.maximum(compMax - compMin, 0)
        rhos = compRange / np.sqrt(self.MaxIRange * (arrMax - arrMin))
        # consider rows with a rho larger than MinRho to be background
        # and use a binary openinig to remove noise detecions
        isw = ndimage.binary_opening(rhos > self.MinRho,
                                     structure=np.ones(self.FilterLen, bool))
        # find the start and stop index for the background rows
        start = np.flatnonzero(isw[:-1] & (~isw[1:])) - self.FilterLen + 1
        stop = np.flatnonzero((~isw[:-1]) & isw[1:]) + self.FilterLen + 1
        start = start.tolist()
        stop = stop.tolist()

        if not np.all(isw):
            if len(start) == 0:
                start.insert(0, 0)
            if len(stop) == 0:
                stop.append(len(arr))

            if start[0] > stop[0]:
                start.insert(0, 0)
            if stop[-1] < start[-1]:
                stop.append(len(arr))

        return start, stop


    def set_segments(self, tops, bottoms):
        self._tops = tops[::-1]
        self._bottoms = bottoms

    @property
    def continuous(self):
        return self._continuous

    @continuous.setter
    def continuous(self, continuous):
        self._continuous = continuous

    @property
    def merge_threshold(self):
        return self._merge_threshold

    @merge_threshold.setter
    def merge_threshold(self, thr):
        self._merge_threshold = thr

    @property
    def continuous_height(self):
        raise NotImplementedError()

    @property
    def continuous_width(self):
        raise NotImplementedError()

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        return item_rect

    def _next_segment(self, view, dy):
        viewTop = int(view.top())
        viewBottom = int(view.bottom())
        nextBottom = viewBottom + dy
        minTop = viewTop
        targetBottom = None
        targetTop = None
        for cb in self._bottoms:
            if nextBottom < cb:
                break
            if viewBottom < cb:
                targetBottom = cb
            elif minTop < cb:
                minTop = cb

        minTop -= 2 * self.FilterLen
        for ct in self._tops:
            if viewTop < minTop and minTop < ct:
                targetTop = ct
            if ct < viewBottom:
                break

        if targetTop is not None:
            return targetTop - viewTop
        elif targetBottom is not None:
            return targetBottom - viewBottom
        else:
            return dy

    def _prev_segment(self, view, dy):
        viewTop = int(view.top())
        viewBottom = int(view.bottom())


        nextTop = viewTop - dy
        maxBottom = viewBottom
        targetTop = None
        targetBottom = None
        for ct in self._tops:
            if ct < nextTop:
                break
            if ct < viewTop:
                targetTop = ct
            elif ct < maxBottom:
                maxBottom = ct

        maxBottom += 2 * self.FilterLen
        for cb in self._bottoms:
            if maxBottom < viewBottom and cb < maxBottom:
                targetBottom = cb
            if viewTop < cb:
                break

        if targetBottom is not None:
            return viewBottom - targetBottom
        elif targetTop is not None:
            return viewTop - targetTop
        else:
            return dy

    def __as_immutable__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, BaseMover) and other.name == self.name

class DownLeftMover(BaseMover):
    def __init__(self, viewer):
        super(DownLeftMover, self).__init__(viewer, 'Down Left')

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        refPoint = scene_rect.topLeft()
        item_rect.moveTopRight(refPoint)
        return scene_rect.united(item_rect)

    def next_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        if scene.bottom() > view.bottom():
            view.adjust(0, dy, 0, dy)
        elif scene.left() < view.left():
            view.adjust(-dx, -INF_POINT, -dx, -INF_POINT)
        return self.align_view(view, scene)

    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        if scene.top() < view.top():
            view.adjust(0, -dy, 0, -dy)
        elif scene.right() > view.right():
            view.adjust(dx, INF_POINT, dx, INF_POINT)
        return self.align_view(view, scene)

    def first_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveTopRight(item_rect.topRight())
        return view

    def last_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveBottomLeft(item_rect.bottomLeft())
        return view

    @property
    def continuous_height(self):
        return False

    @property
    def continuous_width(self):
        return self._continuous


class DownRightMover(BaseMover):
    def __init__(self, viewer):
        super(DownRightMover, self).__init__(viewer, 'Down Right')

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        refPoint = scene_rect.topRight()
        item_rect.moveTopLeft(refPoint)
        return scene_rect.united(item_rect)

    def next_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        if scene.bottom() > view.bottom():
            view.adjust(0, dy, 0, dy)
        elif scene.right() > view.right():
            view.adjust(dx, -INF_POINT, dx, -INF_POINT)
        return self.align_view(view, scene)

    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        if scene.top() < view.top():
            view.adjust(0, -dy, 0, -dy)
        elif scene.left() < view.left():
            view.adjust(-dx, INF_POINT, -dx, INF_POINT)
        return self.align_view(view, scene)

    def first_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveTopLeft(item_rect.topLeft())
        return view

    def last_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveBottomRight(item_rect.bottomRight())
        return view

    @property
    def continuous_height(self):
        return False

    @property
    def continuous_width(self):
        return self._continuous


class RightDownMover(BaseMover):
    def __init__(self, viewer):
        super(RightDownMover, self).__init__(viewer, 'Right Down')

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        refPoint = scene_rect.bottomLeft()
        item_rect.moveTopLeft(refPoint)
        return scene_rect.united(item_rect)

    def next_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        dy = self._next_segment(view, dy)
        if scene.right() > view.right():
            view.adjust(dx, 0, dx, 0)
        elif scene.bottom() > view.bottom():
            view.adjust(-INF_POINT, dy, INF_POINT, dy)
        return self.align_view(view, scene)

    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        dy = self._prev_segment(view, dy)
        if scene.left() < view.left():
            view.adjust(-dx, 0, -dx, 0)
        elif scene.top() < view.top():
            view.adjust(INF_POINT, -dy, INF_POINT, -dy)
        return self.align_view(view, scene)

    def first_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveTopLeft(item_rect.topLeft())
        return view

    def last_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveBottomRight(item_rect.bottomRight())
        return view

    @property
    def continuous_height(self):
        return self._continuous

    @property
    def continuous_width(self):
        return False


class LeftDownMover(BaseMover):
    def __init__(self, viewer):
        super(LeftDownMover, self).__init__(viewer, 'Left Down')

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        refPoint = scene_rect.bottomRight()
        item_rect.moveTopRight(refPoint)
        return scene_rect.united(item_rect)

    def next_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        dy = self._next_segment(view, dy)
        if scene.left() < view.left():
            view.adjust(-dx, 0, -dx, 0)
        elif scene.bottom() > view.bottom():
            view.adjust(INF_POINT, dy, INF_POINT, dy)
        return self.align_view(view, scene)

    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
        dy = self._prev_segment(view, dy)
        if scene.right() > view.right():
            view.adjust(dx, 0, dx, 0)
        elif scene.top() < view.top():
            view.adjust(-INF_POINT, -dy, -INF_POINT, -dy)
        return self.align_view(view, scene)

    def first_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveTopRight(item_rect.topRight())
        return view

    def last_view(self, item):
        item_rect = item.boundingRect()
        dx, dy, view, scene = self.step_sizes(0)
        view.moveBottomLeft(item_rect.bottomLeft())
        return view

    @property
    def continuous_height(self):
        return self._continuous

    @property
    def continuous_width(self):
        return False


def known_movers():
    return list(BaseMover.__subclasses__())
