# -*- coding: utf-8 -*-
"""
Created on Sat Nov 11 18:56:09 2017

@author: Caasar
"""

import sys
import os
import re
import gzip
import socket
import ssl
from io import BytesIO
from six import text_type, reraise
from six.moves.html_parser import HTMLParser
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError, URLError
from six.moves.BaseHTTPServer import BaseHTTPRequestHandler
from six.moves.urllib.parse import urlparse, ParseResult, urlunparse, quote
from .base import WrapperIOError, BaseWrapper
import PIL.Image as Image

try:
    from bs4 import BeautifulSoup
    from bs4_selector import select as bs4_select, SelectorError
except ImportError:
    pass

class WebIOError(WrapperIOError):
    pass

class WebIO(BytesIO):
    ssl_context = ssl._create_unverified_context()
    re_charset = re.compile(r'charset=([\w-]+)')
    user_agent = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'
    forwarded_for = None

    @staticmethod
    def iriToUri(iri):
        return urlunparse([quote(c) if i == 2 else c for i, c in enumerate(urlparse(iri))])

    def __init__(self,url,data=None):
        try:
            request = Request(url)
            request.add_header('Accept-encoding', 'gzip')
            request.add_header('User-Agent',self.user_agent)
            if self.forwarded_for:
                request.add_header('X-Forwarded-For', self.forwarded_for)
            if data:
                request.add_data(data)

            response  = urlopen(request, context=self.ssl_context)
        except:
            try:
                url = self.iriToUri(url)

                request = Request(url)
                request.add_header('Accept-encoding', 'gzip')
                request.add_header('User-Agent',self.user_agent)
                if data:
                    request.add_data(data)

                response  = urlopen(request, context=self.ssl_context)
                print('opened 2nd', url)
            except Exception as err:
                raise WebIOError(str(err))

        try:
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
        except socket.error as err:
            raise WebIOError(str(err))

        super().__init__(raw)

    def tostring(self):
        raw_bytes = self.getvalue()
        try:
            content = raw_bytes.decode(self.charset)
        except UnicodeDecodeError:
            try:
                content = raw_bytes.decode('utf8')
            except UnicodeDecodeError:
                content = raw_bytes.decode('latin1')

        return content


class WebImage(object):
    def __init__(self,alt_urls,page_url,next_page=''):
        dummy, filename = os.path.split(alt_urls[0])
        self.image_url = alt_urls[0]
        self.alt_urls = alt_urls
        self.page_url = page_url
        self.next_page = next_page
        self.filename = filename or self.image_url

    def __hash__(self):
        return hash(self.image_url)


class ImageParser(HTMLParser):
    filtered = {'.gif'}
    minlength = 50000

    def __init__(self,url):
        super(HTMLParser, self).__init__()
        self.saved_link = None
        self.imgs_lists = [list() for dummy in range(8)]

        self.page_url = url
        self.page_purl = urlparse(url)
        part = '/'.join(p for p in self.page_purl.path.split('/')[:-1] if p)
        if part:
            self.base_path = '/%s/' % part
        else:
            self.base_path = '/'

        with WebIO(url) as furl:
            try:
                raw_bytes = furl.read()
                try:
                    content = raw_bytes.decode(furl.charset)
                except UnicodeDecodeError:
                    try:
                        content = raw_bytes.decode('utf8')
                    except UnicodeDecodeError:
                        content = raw_bytes.decode('latin1')
                self.feed(content)
            except Exception as err:
                WebIOError(text_type(err))

    def handle_starttag(self,tag,attrs):
        if tag == 'a':
            self.start_a(attrs)
        elif tag == 'img':
            self.do_img(attrs)

    def handle_endtag(self,tag):
        if tag == 'a':
            self.end_a()

    def start_a(self,info=None):
        try:
            elements = dict(info)
            purl = self._fullpath(elements['href'])
            if purl.netloc == self.page_purl.netloc:
                self.saved_link = purl.geturl()

        except KeyError:
            pass

        if self.saved_link == self.page_url:
            self.saved_link = None

    def end_a(self):
        self.saved_link = None

    def do_img(self,info):
        elements = dict(info)
        if 'src' in elements:
            purl = self._fullpath(elements['src'])
            src = purl.geturl()
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

        return WebImage([image_url.strip()],self.page_url,next_page)

    def _fullpath(self,url):
        purl = urlparse(url)
        furl = list(purl)
        if not purl.scheme:
            furl[0] = self.page_purl.scheme
        if not purl.netloc:
            furl[1] = self.page_purl.netloc
            if not purl.path or purl.path[0] != '/':
                furl[2] = self.base_path + purl.path

        return ParseResult(*furl)

    @staticmethod
    def get_content_length(url):
        request = Request(url)
        request.add_header('User-Agent',WebIO.user_agent)
        request.get_method = lambda: "HEAD"
        try:
            response = urlopen(request, context=WebIO.ssl_context)
            length = response.headers.get("content-length",0)
            response.close()
        except HTTPError:
            length = 0
        except ValueError:
            length = 0

        return length

class WebWrapper(BaseWrapper):
    profiles = dict()
    profile_keys = ['url', 'img', 'next']

    def __init__(self,url):
        self.path = url
        self.mode = 'r'
        self.handle = None
        self.sel_img = None # '#comic-img > a > img'
        self.sel_next = None # '#comic-img > a'
        for paths in self.profiles.values():
            if 'bs4' in sys.modules and re.match(paths['url'], url):
                self.sel_img = paths['img']
                self.sel_next = paths['next']

        if self.sel_img:
            self._filelist = self._parse_url(url)
        else:
            self._filelist = [ImageParser(url).find_image()]

    @property
    def filelist(self):
        return self._filelist

    def filter_images(self):
        return self.filelist

    def load_next(self):
        lastinfo = self.filelist[-1]
        if lastinfo.next_page:
            try:
                if self.sel_img:
                    nextinfos = self._parse_url(lastinfo.next_page)
                    self.filelist.extend(nextinfos)
                else:
                    nextinfo = ImageParser(lastinfo.next_page).find_image()
                    self.filelist.append(nextinfo)
            except WebIOError:
                pass

    def open(self,fileinfo,mode):
        if mode in {'a','w'} and self.mode[0] == 'r':
            raise WebIOError('Child mode does not fit to mode of Archive')

        if fileinfo == self.filelist[-1]:
            self.load_next()

        stack = None, None, None
        for curl in fileinfo.alt_urls:
            try:
                fileinfo.image_url = curl
                return WebIO(curl)
            except WebIOError:
                stack = sys.exc_info()

        if stack[-1] is not None:
            reraise(*stack)
        else:
            raise WebIOError('Unexpectedly reached code')


    def close(self):
        pass

    def list_archives(self):
        return [], 0

    def _parse_url(self, url):
        with WebIO(url) as f_url:
            html_doc = f_url.tostring()

        soup = BeautifulSoup(html_doc, "lxml")

        try:
            nodes = bs4_select(soup, self.sel_next)
        except SelectorError as err:
            raise WebIOError('BeautifulSoup parse error: %s' % err.message)
        next_url = nodes[0]['href'] if nodes else ''
        next_url = self._fullpath(next_url, url)

        try:
            nodes = bs4_select(soup, self.sel_img)
        except SelectorError as err:
            raise WebIOError('BeautifulSoup parse error: %s' % err.message)

        images = [self._builditem(node, url, next_url) for node in nodes]

        if not images:
            print('No image found at %r with selector %r' % (url, self.sel_img))
            raise WebIOError("Could not find image in '%s'" % url)

        return images

    def _builditem(self, itag, url, next_url):
        curls = []
        if 'src' in itag.attrs:
            curls.append(self._fullpath(itag['src'].strip(), url))
        elif 'data-src' in itag.attrs:
            curls.append(self._fullpath(itag['data-src'].strip(), url))
        onerror = itag.get('onerror', '')
        assign = 'this.src='
        if onerror.startswith(assign):
            curl = onerror[len(assign):].strip().strip("'\"")
            curl = self._fullpath(curl, url)
            curls.append(curl.strip())

        return WebImage(curls, url, next_url)

    @staticmethod
    def _fullpath(url, parent_url):
        if not url:
            return ''

        purl = urlparse(url)
        parent_purl = urlparse(parent_url)
        part = '/'.join(p for p in parent_purl.path.split('/')[:-1] if p)
        if part:
            parent_base = '/%s/' % part
        else:
            parent_base = '/'

        furl = list(purl)
        if not purl.scheme:
            furl[0] = parent_purl.scheme
        if not purl.netloc:
            furl[1] = parent_purl.netloc
            if not purl.path or purl.path[0] != '/':
                furl[2] = parent_base + purl.path

        return ParseResult(*furl).geturl()

