from math import inf
from io import BytesIO
import re

# Parser states as constants
_PREAMBLE = "PREAMBLE"
_HEADER = "HEADER"
_BODY = "BODY"
_COMPLETE = "END"


class MultipartError(ValueError):
    """ Base class for all parser errors or warnings """
    #: Suitable HTTP status code for this exception
    http_status = 500  # Internal Error


class ParserError(MultipartError):
    """ Detected invalid input """
    http_status = 415  # Unsupported Media Type


class StrictParserError(ParserError):
    """ Detected unusual input while parsing in strict mode """
    http_status = 415  # Unsupported Media Type


class ParserLimitReached(MultipartError):
    """ Parser reached one of the configured limits """
    http_status = 413  # Request Entity Too Large


class ParserStateError(MultipartError):
    """ Parser reachend an invalid state (e.g. use after close) """
    http_status = 500  # Internal Error


# -------------
# Header Parser
# -------------


# ASCII minus control or special chars
_token = "[a-zA-Z0-9-!#$%&'*+.^_`|~]+"
_re_istoken = re.compile("^%s$" % _token)
# A token or quoted-string (simple qs | token | slow qs)
_value = r'"[^\\"]*"|%s|"(?:\\.|[^"])*"' % _token
# A "; key=value" pair from content-disposition header
_option = r' *(%s) *= *(%s)' % (_token, _value)
_re_option = re.compile(_option)


def header_quote(val):
    """ Quote header option values if necessary.

        Note: This is NOT the way modern browsers quote field names or filenames
        in Content-Disposition headers. See :func:`content_disposition_quote`
    """
    if _re_istoken.match(val):
        return val
    
    return '"' + val.replace("\\", "\\\\").replace('"', '\\"') + '"'


def header_unquote(val, filename=False):
    """ Unquote header option values.

        Note: This is NOT the way modern browsers quote field names or filenames
        in Content-Disposition headers. See :func:`content_disposition_unquote`
    """
    if val[0] == val[-1] == '"':
        val = val[1:-1]
        
        # fix ie6 bug: full path --> filename
        if filename and (val[1:3] == ":\\" or val[:2] == "\\\\"):
            val = val.split("\\")[-1]
        
        return val.replace("\\\\", "\\").replace('\\"', '"')
    
    return val


def content_disposition_quote(val):
    """ Quote field names or filenames for Content-Disposition headers the
        same way modern browsers do it (see WHATWG HTML5 specification).
    """
    val = val.replace("\r", "%0D").replace("\n", "%0A").replace('"', "%22")
    return '"' + val + '"'


def content_disposition_unquote(val, filename=False):
    """ Unquote field names or filenames from Content-Disposition headers.

        Legacy quoting mechanisms are detected to some degree and also supported,
        but there are rare ambiguous edge cases where we have to guess. If in
        doubt, this function assumes a modern browser and follows the WHATWG
        HTML5 specification (limited percent-encoding, no backslash-encoding).
    """
    
    if '"' == val[0] == val[-1]:
        val = val[1:-1]
        if '\\"' in val:  # Legacy backslash-escaped quoted strings
            val = val.replace("\\\\", "\\").replace('\\"', '"')
        elif "%" in val:  # Modern (HTML5) limited percent-encoding
            val = val.replace("%0D", "\r").replace(
                "%0A", "\n").replace("%22", '"')
        # ie6/windows bug: full path instead of just filename
        if filename and (val[1:3] == ":\\" or val[:2] == "\\\\"):
            val = val.rpartition("\\")[-1]
    elif "%" in val:  # Modern (HTML5) limited percent-encoding
        val = val.replace("%0D", "\r").replace("%0A", "\n").replace("%22", '"')
    return val


def parse_options_header(header, options=None, unquote=header_unquote):
    """ Parse Content-Type (or similar) headers into a primary value 
        and an options-dict.

        Note: For Content-Disposition headers you need a different unquote
        function. See `content_disposition_unquote`.

    """
    i = header.find(";")
    if i < 0:
        return header.lower().strip(), {}
    
    option_parts = header.split(";")
    opts = {}
    for part in option_parts:
        match = _re_option.search(part)
        if not match:
            continue
        opts[match.group(1)] = match.group(2)
    
    options = options or {}
    for key, val in opts.items():
        key = key.lower()
        options[key] = unquote(val, key == "filename")
    
    return header[:i].lower().strip(), options


class PushMultipartParser:
    
    def __init__(
            self,
            boundary: bytes,
            content_length=-1,
            max_header_size=4096 + 128,  # 4KB should be enough for everyone
            max_header_count=8,  # RFC 7578 allows just 3
            max_segment_size=inf,  # unlimited
            max_segment_count=inf,  # unlimited
            header_charset="utf8",
            strict=False,
    ):
        """A push-based (incremental, non-blocking) parser for multipart/form-data.
        
        In `strict` mode, the parser will be less forgiving and bail out more
        quickly when presented with strange or invalid input, avoiding
        unnecessary work caused by broken or malicious clients. Fatal errors
        will always trigger exceptions, even in non-strict mode.
        
        The various limits are meant as safeguards and exceeding any of those
        limit will trigger a :exc:`ParserLimitReached` exception.
        
        :param boundary: The multipart boundary as found in the Content-Type header.
        :param content_length: Expected input size in bytes, or -1 if unknown.
        :param max_header_size: Maximum length of a single header line (name and value).
        :param max_header_count: Maximum number of headers per segment.
        :param max_segment_size: Maximum size of a single segment body.
        :param max_segment_count: Maximum number of segments.
        :param header_charset: Charset for header names and values.
        :param strict: Enables additional format and sanity checks.
        """
        self.boundary = boundary
        self.content_length = content_length
        self.header_charset = header_charset
        self.max_header_size = max_header_size
        self.max_header_count = max_header_count
        self.max_segment_size = max_segment_size
        self.max_segment_count = max_segment_count
        self.strict = strict
        
        self._delimiter = b"\r\n--" + self.boundary
        
        # Internal parser state
        self._parsed = 0
        self._fieldcount = 0
        self._buffer = bytearray()
        self._current = None
        self._state = _PREAMBLE
        
        #: True if the parser reached the end of the multipart stream, stopped
        #: parsing due to an :attr:`error`, or :meth:`<close>` was called.
        self.closed = False
        #: A :exc:`MultipartError` instance if parsing failed.
        self.error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close(check_complete=not exc_type)
    
    def parse(
            self, chunk: bytes
    ) -> list:
        """Parse a chunk of data and yield as many result objects as possible
        with the data given.
        
        For each multipart segment, the parser will emit a single instance
        of :class:`MultipartSegment` with all headers already present,
        followed by zero or more non-empty `bytearray` instances containing
        parts of the segment body, followed by a single `None` signaling the
        end of the current segment.
        
        The returned iterator will stop if more data is required or if the end
        of the multipart stream was detected. The iterator must be fully consumed
        before parsing the next chunk. End of input can be signaled by parsing
        an empty chunk or closing the parser. This is important to verify the
        multipart message was parsed completely and the last segment is actually
        complete.
        
        Format errors or exceeded limits will trigger :exc:`MultipartError`.
        """
        
        try:
            assert isinstance(chunk, (bytes, bytearray))
            
            if not chunk:
                self.close()
                return
            
            if self.closed:
                raise ParserStateError("Parser closed")
            
            if self.content_length > -1:
                available = self._parsed + len(self._buffer) + len(chunk)
                if self.content_length < available:
                    raise ParserError("Content-Length limit exceeded")
            
            if self._state is _COMPLETE:
                if self.strict:
                    raise StrictParserError(
                        "Unexpected data after end of multipart stream")
                return
            
            delimiter = self._delimiter
            d_len = len(delimiter)
            buffer = self._buffer
            buffer += chunk  # In-place append
            bufferlen = len(buffer)
            offset = 0
            
            while True:
                
                if self._state is _PREAMBLE:
                    # Scan for first delimiter (CRLF prefix is optional here)
                    index = buffer.find(delimiter[2:], offset)
                    
                    if index > -1:
                        # Boundary must be at position zero, or start with CRLF
                        if index > 0 and not (index >= 2 and buffer[index - 2:index] == b"\r\n"):
                            raise ParserError(
                                "Unexpected byte in front of first boundary")
                        
                        next_start = index + d_len
                        tail = buffer[next_start - 2: next_start]
                        
                        if tail == b"\r\n":  # Normal delimiter found
                            self._current = MultipartSegment(self)
                            self._state = _HEADER
                            offset = next_start
                            continue
                        elif tail == b"--":  # First is also last delimiter
                            offset = next_start
                            self._state = _COMPLETE
                            break  # parsing complete
                        elif tail[0:1] == b"\n":  # Broken client or legacy test case
                            raise ParserError(
                                "Invalid line break after first boundary")
                        elif len(tail) == 2:
                            raise ParserError(
                                "Unexpected byte after first boundary")
                    
                    elif self.strict and bufferlen >= d_len:
                        # No boundary in first chunk -> Fail fast in strict mode
                        # and do not waste time consuming a legacy preamble.
                        raise StrictParserError(
                            "Boundary not found in first chunk")
                    
                    # Delimiter not found, skip data until we find one
                    offset = bufferlen - (d_len + 2)
                    break  # wait for more data
                
                elif self._state is _HEADER:
                    # Find end of header line
                    nl = buffer.find(b"\r\n", offset)
                    
                    if nl > offset:  # Non-empty header line
                        self._current._add_headerline(buffer[offset:nl])
                        offset = nl + 2
                        continue
                    elif nl == offset:  # Empty header line -> End of header section
                        self._current._close_headers()
                        yield self._current
                        self._state = _BODY
                        offset += 2
                        continue
                    else:  # No CRLF found -> Ask for more data
                        if buffer.find(b"\n", offset) != -1:
                            raise ParserError(
                                "Invalid line break in segment header")
                        if bufferlen - offset > self.max_header_size:
                            raise ParserLimitReached(
                                "Maximum segment header length exceeded")
                        break  # wait for more data
                
                elif self._state is _BODY:
                    
                    # Ensure there is enough data in buffer to fit a delimiter
                    if offset + d_len + 2 > bufferlen:
                        break  # wait for more data
                    
                    # Scan for delimiter (CRLF + boundary + (CRLF or '--'))
                    index = buffer.find(delimiter, offset)
                    if index > -1:
                        next_start = index + d_len + 2
                        tail = buffer[next_start - 2: next_start]
                        
                        if tail == b"\r\n" or tail == b"--":
                            if index > offset:
                                self._current._update_size(index - offset)
                                yield buffer[offset:index]
                            
                            offset = next_start
                            self._current._mark_complete()
                            yield None  # End of segment
                            
                            if tail == b"--":  # Last delimiter
                                self._state = _COMPLETE
                                break
                            else:  # Normal delimiter
                                self._current = MultipartSegment(self)
                                self._state = _HEADER
                                continue
                    
                    # Keep enough in buffer to accout for a partial delimiter at
                    # the end, but emiot the rest.
                    chunk_end = bufferlen - (d_len + 1)
                    assert chunk_end > offset  # Always true
                    self._current._update_size(chunk_end - offset)
                    yield buffer[offset:chunk_end]
                    offset = chunk_end
                    break  # wait for more data
                
                else:  # pragma: no cover
                    raise RuntimeError(
                        f"Unexpected internal state: {self._state}")
            
            # We ran out of data, or reached the end
            if offset > 0:
                self._parsed += offset
                buffer[:] = buffer[offset:]
        
        except Exception as err:
            if not self.error:
                self.error = err
            self.close(check_complete=False)
            raise
    
    def close(self, check_complete=True):
        """
        Close this parser if not already closed.
        
        :param check_complete: Raise :exc:`ParserError` if the parser did not
            reach the end of the multipart stream yet.
        """
        
        self.closed = True
        self._current = None
        self._buffer = self._buffer[:]
        
        if check_complete and not self._state is _COMPLETE:
            err = ParserError(
                "Unexpected end of multipart stream (parser closed)")
            if not self.error:
                self.error = err
            raise err


class MultipartSegment:
    """ A :class:`MultipartSegment` represents the header section of a single
    multipart part and provides convenient access to part headers and other
    details (e.g. :attr:`name` and :attr:`filename`). Each segment also
    tracks its own content :attr:`size` while the :class:`PushMultipartParser`
    processes more data, and is marked as :attr:`complete` as soon as the
    next multipart border is found. Segments do not store or buffer any of
    their content data, though. 
    """
    
    #: List of headers as name/value pairs with normalized (Title-Case) names.
    headerlist: list
    #: The 'name' option of the `Content-Disposition` header. Always a string,
    #: but may be empty.
    name: str
    #: The optional 'filename' option of the `Content-Disposition` header.
    filename: str
    #: The cleaned up `Content-Type` segment header, if present. The value is
    #: lower-cased and header options (e.g. charset) are removed.
    content_type: str
    #: The 'charset' option of the `Content-Type` header, if present.
    charset: str
    
    #: Segment body size (so far). Will be updated during parsing.
    size: int
    #: If true, the segment content was fully parsed and the size value is final.
    complete: bool
    
    def __init__(self, parser: PushMultipartParser):
        """ Private constructor, used by :class:`PushMultipartParser` """
        self._parser = parser
        
        if parser._fieldcount + 1 > parser.max_segment_count:
            raise ParserLimitReached("Maximum segment count exceeded")
        parser._fieldcount += 1
        
        self.headerlist = []
        self.size = 0
        self.complete = 0
        
        self.name = None
        self.filename = None
        self.content_type = None
        self.charset = None
        self._clen = -1
        self._size_limit = parser.max_segment_size
    
    def _add_headerline(self, line: bytearray):
        assert line and self.name is None
        parser = self._parser
        
        if line[0] in b" \t":  # Multi-line header value
            if not self.headerlist or parser.strict:
                raise StrictParserError(
                    "Unexpected segment header continuation")
            prev = ": ".join(self.headerlist.pop())
            line = prev.encode(parser.header_charset) + b" " + line.strip()
        
        if len(line) > parser.max_header_size:
            raise ParserLimitReached("Maximum segment header length exceeded")
        if len(self.headerlist) >= parser.max_header_count:
            raise ParserLimitReached("Maximum segment header count exceeded")
        
        try:
            name, col, value = line.decode(
                parser.header_charset).partition(":")
            name = name.strip()
            if not col or not name:
                raise ParserError("Malformed segment header")
            if " " in name:
                raise ParserError("Invalid segment header name")
        except Exception as err:
            raise ParserError("Segment header failed to decode", err)
        
        self.headerlist.append((name.lower(), value.strip()))
    
    def _close_headers(self):
        assert self.name is None
        
        for h, v in self.headerlist:
            if h == "content-disposition":
                dtype, args = parse_options_header(
                    v, unquote=content_disposition_unquote)
                if dtype != "form-data":
                    raise ParserError(
                        "Invalid Content-Disposition segment header: Wrong type")
                if "name" not in args and self._parser.strict:
                    raise StrictParserError(
                        "Invalid Content-Disposition segment header: Missing name option")
                self.name = args.get("name", "")
                self.filename = args.get("filename")
            elif h == "content-type":
                self.content_type, args = parse_options_header(v)
                self.charset = args.get("charset")
            elif h == "content-length" and v.isdecimal():
                self._clen = int(v)
        
        if self.name is None:
            raise ParserError("Missing Content-Disposition segment header")
    
    def _update_size(self, bytecount: int):
        assert self.name is not None and not self.complete
        self.size += bytecount
        if self._clen >= 0 and self.size > self._clen:
            raise ParserError("Segment Content-Length exceeded")
        if self.size > self._size_limit:
            raise ParserLimitReached("Maximum segment size exceeded")
    
    def _mark_complete(self):
        assert self.name is not None and not self.complete
        if self._clen >= 0 and self.size != self._clen:
            raise ParserError(
                "Segment size does not match Content-Length header")
        self.complete = True
    
    def header(self, name: str, default=None):
        """Return the value of a header if present, or a default value."""
        compare = name.lower()
        for header in self.headerlist:
            if header[0] == compare:
                return header[1]
        if default is KeyError:
            raise KeyError(name)
        return default
    
    def __getitem__(self, name):
        """Return a header value if present, or raise :exc:`KeyError`."""
        return self.header(name, KeyError)


class MultipartPart(object):
    """ A :class:`MultipartPart` represents a fully parsed multipart part
        and provides convenient access to part headers and other details (e.g.
        :attr:`name` and :attr:`filename`) as well as its memory- or disk-buffered
        binary or text content.
    """
    
    def __init__(
        self,
        charset="utf8",
        segment: "MultipartSegment" = None,
    ):
        self._segment = segment
        #: A file-like buffer holding the parts binary content, or None if this
        #: part was :meth:`closed <close>`.
        self.file = BytesIO()
        #: Part size in bytes.
        self.size = 0
        #: Part name.
        self.name = segment.name
        #: Part filename (if defined).
        self.filename = segment.filename
        #: Charset as defined in the part header, or the parser default charset.
        self.charset = segment.charset or charset
        #: All part headers as a list of (name, value) pairs.
        self.headerlist = segment.headerlist
    
    def headers(self) -> list:
        """ A convenient list holding all part headers. """
        return self._segment.headerlist
    
    def disposition(self) -> str:
        """ The value of the `Content-Disposition` part header. """
        return self._segment.header("content-disposition")
    
    def content_type(self) -> str:
        """ Cleaned up content type provided for this part, or a sensible
            default (`application/octet-stream` for files and `text/plain` for
            text fields).
        """
        return self._segment.content_type or (
            "application/octet-stream" if self.filename else "text/plain")
    
    def _set_alternative_buffer(self, buffer):
        self.file = buffer
    
    def _write(self, chunk):
        self.size += len(chunk)
        self.file.write(chunk)
    
    def _mark_complete(self):
        self.file.seek(0)
    
    @property
    def value(self):
        """Return the entire payload as a decoded text string.
            Warning, this may consume a lot of memory, check :attr:`size` first.
        """
        return self.raw.decode(self.charset)
    
    @property
    def raw(self):
        """Return the entire payload as a raw byte string.

        Warning, this may consume a lot of memory, check :attr:`size` first.
        """
        pos = self.file.tell()
        self.file.seek(0)
        
        val = self.file.read()
        self.file.seek(pos)
        return val
    
    def close(self):
        """ Close :attr:`file` and set it to `None` to free up resources. """
        if self.file:
            self.file.close()
            self.file = False