# -*- coding: utf-8 -*-
"""
Created on Sun Sep 06 09:06:13 2015

@author: Caasar
"""
from __future__ import print_function
import re
from bs4.element import Tag

SELECTOR_END = r'[ ,>+~:#\[]?'

class SelectorError(Exception):
    pass

class Checker(object):
    classes = set()

class CheckerTag(Checker):
    re = re.compile(r'(?P<tag>[a-zA-Z_][-.a-zA-Z0-9_]*)'+SELECTOR_END)
    
    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end('tag'):]
            checker.append(cls(match.group('tag')))
        return selector, checker

    def __init__(self, tag_name):
        self.tag_name = tag_name
    
    def __call__(self, tags):
        return set(id(tag) for tag in tags if tag.name == self.tag_name)
        
class CheckerAttrib(Checker):
    re = re.compile(r'^\[(?P<attribute>[\w-]+)(?P<operator>[~\|\^\$\*]?=)?'
                    r'"?(?P<value>[^\]"]*)"?\s*\]')

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end():]
            checker.append(cls(*match.groups()))
        return selector, checker

    def __init__(self,attrib, operator, value):
        self.attrib = attrib
        self.value = value
        if operator == '=':
            self.op = self._op_equal
        elif operator == '~=':
            self.op = self._op_in
        elif operator == '|=':
            self.op = self._op_in_start
        elif operator == '^=':
            self.op = self._op_startswith
        elif operator == '$=':
            self.op = self._op_endswith
        elif operator == '*=':
            self.op = self._op_contains
        else:
            self.op = self._op_exists
    
    def __call__(self, tags):
        return set(id(tag) for tag in tags if self.op(tag))

    def _op_exists(self, tag):
        return self.attrib in tag.attrs
    
    def _op_equal(self, tag):
        value = tag.get(self.attrib, '')
        if not isinstance(value, basestring):
            value = u' '.join(value)
        return value == self.value
    
    def _op_startswith(self, tag):
        value = tag.get(self.attrib, '')
        if not isinstance(value, basestring):
            value = ' '.join(value)
        return value.startswith(self.value)
        
    def _op_endswith(self, tag):
        value = tag.get(self.attrib, '')
        if not isinstance(value, basestring):
            value = ' '.join(value)
        return value.endswith(self.value)
    
    def _op_contains(self, tag):
        value = tag.get(self.attrib, '')
        if not isinstance(value, basestring):
            value = ' '.join(value)
        return self.value in value
        
    def _op_in(self, tag):
        value = tag.get(self.attrib, [])
        if isinstance(value, basestring):
            value = value.split()
        return self.value in value

    def _op_in_start(self, tag):
        value = tag.get(self.attrib, [])
        if isinstance(value, basestring):
            value = value.split()
        return any([v.startswith(self.value) for v in value])

class CheckerId(Checker):
    re = re.compile(r'#(?P<id>[-.a-zA-Z0-9_]+)'+SELECTOR_END)

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end('id'):]
            checker.append(cls(match.group('id')))
        return selector, checker

    def __init__(self,tag_id):
        self.tag_id = tag_id
    
    def __call__(self, tags):
        return set(id(tag) for tag in tags if tag.get('id', None) == self.tag_id)

class CheckerClass(Checker):
    re = re.compile(r'\.(?P<class>[-.a-zA-Z0-9_]+)'+SELECTOR_END)

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end('class'):]
            checker.append(cls(match.group('class')))
        return selector, checker

    def __init__(self,tag_class):
        self.tag_class = tag_class
    
    def __call__(self, tags):
        def has_class(tag):
            classes = tag.get('class',[])
            if isinstance(classes, basestring):
                classes = classes.split()
            return self.tag_class in classes
        return set(id(tag) for tag in tags if has_class(tag))

class CheckerChildSlicer(Checker):
    re = re.compile(r':(?P<op>first-child|last-child|nth-child|nth-last-child)'
                    r'(\((?P<nth>[^\)]+)\))?')

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end():]
            checker.append(cls(**match.groupdict()))
        return selector, checker

    def __init__(self, nth, op):
        if op == 'first-child':
            nth = 0
        elif op == 'last-child':
            nth = -1
        elif op == 'nth-child':
            nth = int(nth) - 1
        elif op == 'nth-last-child':
            nth = -int(nth)
        self.nth = nth
        
    def __call__(self, tags):
        try:
            return set([id(tags[self.nth])])
        except IndexError:
            return set()
    
class CheckerTypeSlicer(Checker):
    re = re.compile(r':(?P<op>first-of-type|last-of-type|nth-of-type|nth-last-of-type)'
                    r'(\((?P<nth>[^\)]+)\))?')

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            selector = selector[match.end():]
            checker.append(cls(**match.groupdict()))
        return selector, checker

    def __init__(self, nth, op):
        try:
            if op == 'first-of-type':
                nth = 0
            elif op == 'last-of-type':
                nth = -1
            elif op == 'nth-of-type':
                nth = int(nth) - 1
            elif op == 'nth-last-of-type':
                nth = -int(nth)
        except (TypeError, ValueError):
            raise SelectorError('Invalid nth element %r' % nth)
        self.nth = nth
        
    def __call__(self, tags):
        types = {}
        for tag in tags:
            types.setdefault(tag.name, []).append(tag)
            
        filtered = set()
        for tags in types.values():
            try:
                filtered.add(id(tags[self.nth]))
            except IndexError:
                pass
        return filtered

class CheckerAfter(Checker):
    re = re.compile(r'\s*(?P<op>[+~])\s*')

    @classmethod
    def build(cls, selector, checker):
        match = cls.re.match(selector)
        if match:
            second = []
            selector = selector[match.end():]
            old_sel = None
            while old_sel != selector:
                old_sel = selector
                for c in CHECKERS:
                    selector, second = c.build(selector, second)
            checker = [cls(checker, second, match.group('op'))]
        return selector, checker

    def __init__(self, first, second, op):
        if not first:
            raise SelectorError('Missing selector before %r' % op)
        if not second:
            raise SelectorError('Missing selector after %r' % op)
        self.multiple = op == '~'
        self.first = first
        self.second = second
    
    def __call__(self, tags):
        first = self.first[0](tags)
        for c in self.first[1:]:
            first &= c(tags)
        second = self.second[0](tags)
        for c in self.second[1:]:
            second &= c(tags)
        filtered = set()
        for i, tag in enumerate(tags):
            if id(tag) in first and (i+1) < len(tags):
                if self.multiple:
                    filtered.update(id(t) for t in tags[i+1:] if id(t) in second)
                elif id(tags[i+1]) in second:
                    filtered.add(id(tags[i+1]))
                    
        return filtered

CHECKERS = [CheckerTag, CheckerAttrib, CheckerId, CheckerChildSlicer,
            CheckerTypeSlicer, CheckerAfter, CheckerClass]

def select(root, selector, debug=False):
    """Perform a CSS selection operation on the provided element."""
    selected = []
    context = []
    selector = selector.strip()
    while selector:
        if selector[0] == '>':
            recursive = False
            selector = selector[1:].strip()
        else:
            if debug:
                print('Recursive search')
            recursive = True
        
        if not context:
            context = [root]
        checker = []
        old_selected = None
        while old_selected != selector:
            old_selected = selector
            for c_t in CHECKERS:
                selector, checker = c_t.build(selector, checker)

        if debug:
            for c in checker:
                print(type(c), c.__dict__)

        if not checker:
            raise SelectorError('Unknown selector %r' % selector)
        
        if recursive:
            groups = dict()
            for tag in context:
                for child in tag.descendants:
                    if isinstance(child, Tag):
                        groups.setdefault(id(child.parent),[]).append(child)
            groups = list(groups.values())
        else:
            groups = []
            for tag in context:
                groups.append([t for t in tag.children if isinstance(t, Tag)])
         
        context = []
        for tags in groups:
            valid = checker[0](tags)
            for c in checker[1:]:
                valid &= c(tags)
            context.extend(tag for tag in tags if id(tag) in valid)
        
        if debug:
            print('Found %d tags' % len(context))
            
        selector = selector.strip()
        if selector and selector[0] == ',':
            selected.extend(context)
            context = []
            selector = selector[1:].strip()
    
    selected.extend(context)
    return selected

__all__ = ['select', 'SelectorError']
