import errno
import socket
from micropython import const

# Components of HTTP/1.1 responses
#
# Use when manually composing an HTTP response
# Expand as required for your use
#
# For HTTP/1.1 specification see: https://www.ietf.org/rfc/rfc2616.txt
# For MIME types see: https://www.iana.org/assignments/media-types/media-types.xhtml
#
# Copyright 2021 (c) Erik de Lange
# Released under MIT license


#todo those classes appears to be not used - test that

class StatusLine:
    OK_200 = b"HTTP/1.1 200 OK\r\n"
    BAD_REQUEST_400 = b"HTTP/1.1 400 Bad Request\r\n"
    NOT_FOUND_404 = b"HTTP/1.1 404 Not Found\r\n"


class ResponseHeader:
    CONNECTION_CLOSE = b"Connection: close\r\n"
    CONNECTION_KEEP_ALIVE = b"Connection: keep-alive\r\n"


class MimeType:
    TEXT_HTML = b"Content-Type: text/html\r\n"
    TEXT_EVENT_STREAM = b"Content-Type: text/event-stream\r\n"
    IMAGE_X_ICON = b"Content-Type: image/x-icon\r\n"
    APPLICATION_JSON = b"Content-Type: application/json\r\n"


class HTTPResponse:
    
    def __init__(self, status, mimetype=None, close=True, header=None):
        """ Create a response object

        :param int status: HTTP status code
        :param str mimetype: HTTP mime type
        :param bool close: if true close connection else keep alive
        :param dict header: key,value pairs for HTTP response header fields
        """
        self.status = status
        self.mimetype = mimetype
        self.close = close
        if header is None:
            self.header = {}
        else:
            self.header = header
        
        self.reasons = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found"
        }
    
    def send(self, writer):
        """ Send response to stream writer """
        writer.write(f"HTTP/1.1 {self.status} {self.reasons.get(self.status, 'NA')}\n")
        if self.mimetype is not None:
            writer.write(f"Content-Type: {self.mimetype}\n")
        if self.close:
            writer.write("Connection: close\n")
        else:
            writer.write("Connection: keep-alive\n")
        if len(self.header) > 0:
            for key, value in self.header.items():
                writer.write(f"{key}: {value}\n")
        writer.write("\n")


# Routines for decoding an HTTP request line.
#
# HTTP request line as understood by this package:
#
#   Request line: Method SP Request-URL SP HTTP-Version CRLF
#   Request URL: Path ? Query
#   Query: key=value&key=value
#
# Example: b"GET /page?key1=0.07&key2=0.03&key3=0.13 HTTP/1.1\r\n"
#
#   Method: GET
#   Request URL: /page?key1=0.07&key2=0.03&key3=0.13
#   HTTP version: HTTP/1.1
#   Path: /page
#   Query: key1=0.07&key2=0.03&key3=0.13
#
# See also: https://www.tutorialspoint.com/http/http_requests.htm
#           https://en.wikipedia.org/wiki/Uniform_Resource_Identifier
#
# For MicroPython applications which process HTTP requests.
#
# Copyright 2021,2022 (c) Erik de Lange
# Released under MIT license


class InvalidRequest(Exception):
    pass


class HTTPRequest:

    def __init__(self, request_line) -> None:
        """ Separate an HTTP request line in its elements.

            :param bytes request_line: the complete HTTP request line
            :return Request: instance containing
                    method      the request method ("GET", "PUT", ...)
                    url         the request URL, including the query string (if any)
                    path        the request path from the URL
                    query       the query string from the URL (if any, else "")
                    version     the HTTP version
                    parameters  dictionary with key-value pairs from the query string
                    header      empty dict, placeholder for key-value pairs from request header fields
            :raises InvalidRequest: if line does not contain exactly 3 components separated by spaces
                                    if method is not in IETF standardized set
                                    aside from these no other checks done here
        """
        try:
            self.method, self.url, self.version = request_line.decode("utf-8").split()
            # note that method, url and version are str, not bytes
        except ValueError:
            raise InvalidRequest(f"Expected 3 elements in {request_line}")

        if self.version.find("/") != -1:
            self.version = self.version.split("/", 1)[1]

        if self.method not in ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE"]:
            raise InvalidRequest(f"Invalid method {self.method} in {request_line}")

        if self.url.find("?") != -1:
            self.path, self.query = self.url.split("?", 1)
            self.parameters = self.query_params_to_dict(self.query)
        else:
            self.path = self.url
            self.query = ""
            self.parameters = dict()

        self.header = dict()


    def query_params_to_dict(self, query):
        """ Place all key-value pairs from a request URLs query string into a dict.
    
        Example: request b"GET /page?key1=0.07&key2=0.03&key3=0.13 HTTP/1.1\r\n"
        yields dictionary {'key1': '0.07', 'key2': '0.03', 'key3': '0.13'}.
    
        :param str query: the query part (everything after the '?') from an HTTP request line
        :return dict: dictionary with zero or more entries
        """
        d = dict()
        if len(query) > 0:
            for pair in query.split("&"):
                try:
                    key, value = pair.split("=", 1)
                    if key not in d:  # only first occurrence taken into account
                        d[key] = value
                except ValueError:  # skip malformed parameter (like missing '=')
                    pass
    
        return d
    

# Minimal HTTP server
#
# Usage:
#
#   from httpserver import HTTPServer, sendfile, CONNECTION_CLOSE
#
#   app = HTTPServer()

#   @app.route("GET", "/")
#   def root(conn, request):
#       response = HTTPResponse(200, "text/html", close=True)
#       response.send(conn)
#       sendfile(conn, "index.html")
#
#   app.start()
#
# Handlers for the (method, path) combinations must be decorated with @route,
# and declared before the server is started (via a call to start).
# Every handler receives the connection socket and an object with all the
# details from the request (see url.py for exact content). The handler must
# construct and send a correct HTTP response. To avoid typos use the
# HTTPResponse component from response.py.
# When leaving the handler the connection will be closed, unless the return
# code of the handler is CONNECTION_KEEP_ALIVE.
# Any (method, path) combination which has not been declared using @route
# will, when received by the server, result in a 404 HTTP error.
# The server cannot be stopped unless an alert is raised. A KeyboardInterrupt
# will cause a controlled exit.
#
# Copyright 2021 (c) Erik de Lange
# Released under MIT license


CONNECTION_CLOSE = const(0)
CONNECTION_KEEP_ALIVE = const(1)
STOP_SERVER = const(2)


class HTTPServerError(Exception):
    pass


class HTTPServer:

    def __init__(self, host="0.0.0.0", port=80, backlog=5, timeout=30):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.timeout = timeout
        self._routes = dict()  # stores link between (method, path) and function to execute

    def route(self, method="GET", path="/"):
        """ Decorator which connects method and path to the decorated function. """

        if (method, path) in self._routes:
            raise HTTPServerError(f"route{(method, path)} already registered")

        def wrapper(function):
            self._routes[(method, path)] = function

        return wrapper

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server.bind((self.host, self.port))
        server.listen(self.backlog)

        print(f"HTTP server started on {self.host}:{self.port}")

        while True:
            try:
                conn, addr = server.accept()
                conn.settimeout(self.timeout)

                request_line = conn.readline()
                if request_line is None:
                    raise OSError(errno.ETIMEDOUT)

                if request_line in [b"", b"\r\n"]:
                    print(f"empty request line from {addr[0]}")
                    conn.close()
                    continue

                print(f"request line {request_line} from {addr[0]}")

                try:
                    request = HTTPRequest(request_line)
                except InvalidRequest as e:
                    while True:
                        # read and discard header fields
                        line = conn.readline()
                        if line is None:
                            raise OSError(errno.ETIMEDOUT)
                        if line in [b"", b"\r\n"]:
                            break
                    response = HTTPResponse(400, "text/plain", close=True)
                    response.send(conn)
                    conn.write(repr(e).encode("utf-8"))
                    conn.close()
                    continue

                while True:
                    # read header fields and add name / value to dict 'header'
                    line = conn.readline()
                    if line is None:
                        raise OSError(errno.ETIMEDOUT)

                    if line in [b"", b"\r\n"]:
                        break
                    else:
                        if line.find(b":") != 1:
                            name, value = line.split(b':', 1)
                            request.header[name.lower()] = value.strip()

                # search function which is connected to (method, path)
                func = self._routes.get((request.method, request.path))
                if func:
                    route_handler_result = func(conn, request)
                    if route_handler_result == STOP_SERVER:
                        conn.close()
                        break
                    elif route_handler_result != CONNECTION_KEEP_ALIVE:
                        # close connection unless explicitly kept alive
                        conn.close()
                else:  # no function found for (method, path) combination
                    response = HTTPResponse(404)
                    response.send(conn)
                    conn.close()

            except KeyboardInterrupt:  # will stop the server
                conn.close()
                break
            except Exception as e:
                conn.close()
                if type(e) is OSError and e.errno == errno.ETIMEDOUT:  # communication timeout
                    pass
                elif type(e) is OSError and e.errno == errno.ECONNRESET:  # client reset the connection
                    pass
                else:
                    server.close()
                    raise e

        server.close()
        print("HTTP server stopped")