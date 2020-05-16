import socket
import sys
import time
import threading
import os


# CONSTANTS

PORT    =   80
HOST    =   "localhost"
LOCK    =   threading.Lock()


# CLI LOADER

class CliLoader:
    
    ANIMATIONS = (
        ("-", "\\", "|", "/"),
        ("[-]", "[\\]", "[|]", "[/]")
    )
    
    def __init__(self, predicat, animation = 0, duration_time = 1):
        self._predicat      = predicat
        self._duration_time = duration_time
        self._animation     = self.ANIMATIONS[animation]
        
    def run(self):
        """Run until the predicat is False"""
        position = 0
        while self._predicat():
            position %= len(self._animation)
            to_write = self._animation[position]
            sys.stdout.write(to_write + "\b" * len(to_write))
            sys.stdout.flush()
            time.sleep(self._duration_time)
            position += 1
        sys.stdout.write("\b  ")


# SERVE DIRECTORY AND PATHS

class Path:
    pass

class Directory:
    pass


# HTTP

class _HttpRequest:
    
    def __init__(self, datas: bytes):
        """Parse the request and extract all infos"""
        self.parse(datas)
        
    def parse(self, datas: bytes):
        """Parse and return a tuple containing request, header, content"""
        header, content = datas.split(b"\r\n\r\n")
        request, *headers = header.split(b"\r\n")
        # then, split to get method, path and httptype
        self._request = request
        self._method, self._url, self._type = self._request.split(b" ")
        # transform header to dict
        self._headers = {}
        for line in headers:
            k, _, v = line.partition(b":")
            self._headers[k] = v
            
    @property
    def request(self):
        return self._request
    
    @property
    def method(self):
        return self._method
    
    @property
    def headers(self):
        return self._headers
    
    @property
    def path(self):
        return self._url
    

class _HttpAnswer:
    
    SUCCESS = "HTTP/1.1 200 OK"
    ERROR   = "HTTP/1.1 404 Not Found"
    
    def __init__(self):
        """Create a new answer"""
        self._code      = None
        self._headers   = None
        self._content   = None
        
    def set_answer_code(self, code):
        """Set the answer code (200, 400)"""
        if code in (self.SUCCESS, self.ERROR):
            self._code = code
        else:
            raise TypeError()
        
    def set_headers(self, headers: dict):
        """Set the headers"""
        self._headers = headers
        
    def set_content(self, content):
        """Set the content : can be bytes or string"""
        if isinstance(content, str):
            content = content.encode("utf-8")
        self._content = content
        
    def as_bytes(self):
        """Return the byte representation, in order to send it"""
        if self._code is None or self._headers is None or self._content is None:
            raise AttributeError()
        # if all fileds are filled
        code = self._code.encode("utf-8")
        headers = []
        for k, v in self._headers.items():
            headers.append(k.encode("utf-8") + b": " + v.encode("utf-8"))
        headers = b"\r\n".join(headers)
        content = self._content
        # the final answer
        answer = code + b"\r\n" + headers + b"\r\n\r\n" + content + b"\r\n\r\n"
        return answer
        
    @classmethod
    def default_error_msg(cls):
        """The default error message"""
        answer = _HttpAnswer()
        answer.set_answer_code(cls.SUCCESS)
        answer.set_headers({"server": "Horus",})
        answer.set_content("Not found... :/")
        return answer


# HTTP PACKET

class HttpPacket:
    
    @classmethod
    def read(cls, datas: bytes):
        """Get a packet as bytes and extract his content"""
        return _HttpRequest(datas)
    
    @classmethod
    def new(cls):
        """Create a new http packet"""
        return _HttpAnswer()
        

# CONNECTION_THREAD

class ConnectionThread(threading.Thread):
    
    def __init__(self, connexion, parent):
        self._connexion, self._sockinfos    = connexion
        self._parent    = parent
        self._alive     = True
        # initialize the thread
        super().__init__()
        
    def run(self):
        """Run the thread"""
        datas = self._connexion.recv(1024 * 20)
        c = HttpPacket.read(datas)
        answer = _HttpAnswer.default_error_msg().as_bytes()
        self._connexion.sendall(answer)
        self._connexion.close()
    
    def kill(self):
        """Kill the thread"""
        self._alive = False

# SERVER THREAD

class ServerThread(threading.Thread):
    
    def __init__(self, connexion, parent):
        self._connexion = connexion
        self._parent    = parent
        self._alive     = True
        self._threads   = []
        # init
        super().__init__()
        
    def run(self):
        """Run the thread"""
        while self._alive:
            client = self._connexion.accept()
            thread = ConnectionThread(client, self)
            self._threads.append(thread)
            thread.start()
        # close all the opened connexions
        for i, thread in enumerate(self._threads):
            self.close_thread(i, thread)
    
    def close_thread(self, i, thread):
        """Close the thread"""
        thread.kill()
            
    def kill(self):
        """Kill the thread"""
        self._alive = False

# MAIN LOOP

class Server:
    
    INIT_CONNEXION_ERROR    = "Initialisation of connexion failed..."
    
    def __init__(self, host, port):
        """The main loop"""
        self._host          = host
        self._port          = port
        # try to initialize a new connection
        self._connexion    = self._init_connection(self._host, self._port)
        self._server       = ServerThread(self._connexion, self)
        
    def _init_connection(self, host, port):
        """Initialise a new connexion or fail and exit"""
        try:
            connexion   = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connexion.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            connexion.bind((host, port))
            connexion.listen(1)
        except Exception as e:
            self.error(self.INIT_CONNEXION_ERROR)
        else:
            return connexion
        
    def run_forever(self):
        """Run the server until an error occur"""
        self._server.start()
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt as error:
            self.close()
            
    # ERRORS AND CLOSE
        
    def close(self):
        """Close all the opening files"""
        self.close_server_thread()
        self.close_connexion()
        
    def close_connexion(self):
        """Close the connexion"""
        self._connexion.close()
        sys.stdout.write("Closing connexion\t")
        sys.stdout.write("[done]\n")
        sys.stdout.flush()
        
    def close_server_thread(self):
        """Wait for the server thread"""
        self._server.kill()
        sys.stdout.write("\nClosing server thread\t")
        # run the loader until thread is dead
        loader = CliLoader(self._server.is_alive, 1)
        loader.run()
        sys.stdout.write("[done]\n")
        sys.stdout.flush()
        
    def error(self, msg = "Error"):
        """Print the error"""
        print(msg, file = sys.stderr)
        self.close()
        sys.exit(1)
        
        
        
if __name__ == "__main__":
    app = Server(HOST, PORT)
    app.run_forever()
        
        
