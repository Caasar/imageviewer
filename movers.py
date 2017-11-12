# -*- coding: utf-8 -*-
"""
Created on Mon Nov 13 20:47:28 2017

@author: Caasar
"""
from __future__ import division

try: 
    from PySide import QtCore
except ImportError:
    from PyQt4 import QtCore

INF_POINT = 1000000000


class BaseMover(object):
    def __init__(self, viewer, name):
        self.viewer = viewer
        self.name = name
    
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

    @classmethod
    def append_item(cls, scene_rect, item_rect):
        return item_rect
    
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
        if scene.right() > view.right():
            view.adjust(dx, 0, dx, 0)
        elif scene.bottom() > view.bottom():
            view.adjust(-INF_POINT, dy, INF_POINT, dy)
        return self.align_view(view, scene)
        
    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
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
        if scene.left() < view.left():
            view.adjust(-dx, 0, -dx, 0)
        elif scene.bottom() > view.bottom():
            view.adjust(INF_POINT, dy, INF_POINT, dy)
        return self.align_view(view, scene)

        
    def prev_view(self, overlap):
        dx, dy, view, scene = self.step_sizes(overlap)
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


def known_movers():
    return list(BaseMover.__subclasses__())
