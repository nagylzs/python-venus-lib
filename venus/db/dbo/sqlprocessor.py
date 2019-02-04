"""Provide ways for processing SQL commands.

SQL processors are objects are fed with buffer pieces. When a SQL
command is finally available then they process the command some way.
"""
import sys

"""Default terminator for SQL commands."""
DEFAULT_TERMINATOR = ";"


class SQLProcessor:
    """Base class for SQL processors.

    SQL processors are fed with buffer pieces. When a SQL command is
    available then they process the command some way."""
    def __init__(self, terminator=None, logger=None):
        """Create SQL processor.

        @param terminator: SQL command terminator. Descendants should
            append this to the buffer before processing (if needed).

        @param logger: a logger object (see the standard logging module)
            When given, it will be used for logging.

                1. successful commands will call logger.info()
                2. when ignore_exceptions is set, unsuccessful commands
                        will call logger.debug
                3. when ignore_exceptions is unset, unsuccessful commands
                        will call logger.error
        """
        self.buffer = ''
        self.terminator = terminator or DEFAULT_TERMINATOR
        self.logger = logger
        self.subprocessors = []

    def addsubprocessor(self, subprocessor):
        """Add a new subprocessor.

        Subprocessors will be called with the same paramteres when
        addbuffer,addline,truncate_last_comma and doprocessbuffer is
        called. Please never create reference cycles with this method -
        only create processor trees. Creating a reference cycle will
        result in infinite recursion."""
        self.subprocessors.append(subprocessor)
        return self

    def removesubprocessor(self, subprocessor):
        """Remove a subprocessor."""
        self.subprocessors.remove(subprocessor)
        return self


    def addbuffer(self, txt):
        """Append some text to the internal buffer.

        @param txt: the text to add to the internal buffer
            It must be plain string (not unicode). However,
            you should always use UTF-8 strings.
        """
        self.buffer += txt
        for subprocessor in self.subprocessors:
            subprocessor.addbuffer(txt)
        return self

    def addline(self, line):
        """Append one line to internal buffer.

        This method will add the line to the internal buffer
        followed by a newline character.

        @param line: the line to add to the buffer.
            It must be plain string (not unicode). However,
            you should always use UTF-8 strings.
        """
        self.buffer += line + "\n"
        for subprocessor in self.subprocessors:
            subprocessor.addline(line)
        return self

    def truncate_last_comma(self):
        """Truncate the buffer until the last comma.

        This method can be used after iterations to truncate the buffer
        until the last comma. Please note that everything after the last
        comma is removed, including the comma.
        """
        index = self.buffer.rfind(",")
        if index >= 0:
            self.buffer = self.buffer[:index]
        for subprocessor in self.subprocessors:
            subprocessor.truncate_last_comma()
        return self

    def doprocessbuffer(self):
        """Process one SQL command (process and clear internal buffer).

        This method will process the current buffer and then clear it.

        NOTE: The buffer will be cleared even if an exception is raised.

        NOTE: descendants MUST implement this method since it is
            unimplemented in SQLProcessor. They should consider
            using self.terminator here.

        NOTE: you should NEVER call this method directly. You should
            always call processbuffer which handles exceptions, logging
            and subprocessors.
        """
        pass

    def processbuffer(self, ignore_exceptions=False):
        """Process one SQL command (process and clear internal buffer).

        This method will process the current buffer and then clear it.

        NOTE: The buffer will be cleared even if an exception is raised.

        NOTE: descendants MUST NOT override this method, they should
        override doprocessbuffer instead.

        NOTE: If the object has a logger associated, then  it will be
        used for logging:

                1. successful commands will call logger.info()
                2. when ignore_exceptions is set, unsuccessful commands
                        will logger.debug()
                3. when ignore_exceptions is unset, unsuccessful
                    commands will logger.error()

        @param ignore_exceptions: whether to ignore exceptions or not.
            If you clear this flag then exceptions are caught and
            ignored. If you set this flag then have to handle
            exceptions. (The buffer will be cleared anyway.)
        """
        log = self.buffer.lstrip()
        index = log.find(chr(13))
        if index < 0:
            index = log.find(chr(10))
        if index > 0:
            log = log[:index]
        log.strip()
        log = log[:70]
        try:
            self.doprocessbuffer()
            self.buffer = ""
            if not (self.logger is None):
                self.logger.info(log)
        except:
            self.buffer = ""
            if not (self.logger is None):
                if ignore_exceptions:
                    self.logger.debug(log)
                else:
                    self.logger.error(log)
            if not ignore_exceptions:
                raise
        for subprocessor in self.subprocessors:
            subprocessor.processbuffer(ignore_exceptions)
        return self


class StreamSQLProcessor(SQLProcessor):
    """Specialized processor that writes its buffer to a stream."""
    def __init__(self, stream, terminator=None, logger=None):
        """
        @param stream: the stream you want to write commands to.
            It should at least have a write() method.
        """
        SQLProcessor.__init__(self, terminator, logger)
        self.stream = stream

    def doprocessbuffer(self):
        """This method will write the buffer to the stream and
        clear the buffer. See also SQLProcessor.processbuffer"""
        self.stream.write(self.buffer + self.terminator + "\n")


class StdOutSQLProcessor(StreamSQLProcessor):
    """Use the standard output as the stream for L{StreamSQLProcessor}

    NOTE: The stream parameter is missing because it will always be
    sys.stdout."""
    def __init__(self, terminator=None, logger=None):
        StreamSQLProcessor.__init__(self, sys.stdout, terminator, logger)


class DirectSQLProcessor(SQLProcessor):
    """Uses a ConnectionPool to execute the SQL commands directly."""
    def __init__(self, pool, terminator=None, logger=None):
        """
        @param pool: a db.dbo.connectionpool.ConnectionPool instance.
        """
        SQLProcessor.__init__(self, terminator, logger)
        self.pool = pool

    def doprocessbuffer(self):
        """Send the buffer directly to the connection."""
        with self.pool.opentrans() as conn:
            conn.execsql(self.buffer)


class DummyLogger:
    """This is a dummy logger object that can be used for debug purposes.

    It implements the info,debug and error methods as plain print
    statements."""
    def __init__(self, name):
        self.name = name

    def info(self, data):
        print("SUCCESS " + self.name + data)

    def debug(self, data):
        print("IGNORE  " + self.name + data)

    def error(self, data):
        print("FAILURE " + self.name + data)
