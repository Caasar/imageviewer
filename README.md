# imageviewer

A very simple image viewer written in python using PyQt5 or PyQt4. It is optimized for reading zipped DRM free comics and is inspired by CDisplay which is no longer in active development. It was originaly develped using PySide but is now using PyQt5 as the intended framework.

Simply drag 'n drop a supported archive, a folder or a webpage containing images into the viewer.

## Extensions
The viewer uses the uipfile python package to read/write ZIP files. Further archives are supported by connecting with the 7z binary using the subprocess module. The 7z binary has to be on the system path so the viewer can use it. The support of PDF files is possible by using ctypes to connect to the MuPDF library which supports PDF 1.7 and is also used by the Sumatra PDF viewer. To read pdf files the dynamic library libmupdf has to be accessible and export the following functions:

* `fz_read`
* `fz_new_context`
* `fz_free_context`
* `pdf_open_document`
* `pdf_close_document`
* `pdf_count_objects`
* `pdf_load_object`
* `pdf_drop_obj`
* `pdf_open_raw_stream`
* `pdf_dict_gets`
* `pdf_is_name`
* `pdf_is_int`
* `pdf_to_name`
* `pdf_to_int`
