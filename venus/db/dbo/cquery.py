"""Cached bi-directional query."""

import venus.i18n
_ = venus.i18n.get_my_translator(__file__)



class CQuery:
    """Cached bi-directional query.

    Enchanted features (compared to simple DB API 2.0 cursor object):

        * access field values by name
        * auto close cursor for commited/rolled back transactions
        * various ways to iterate over

    Enchanted features (compared to Query object):

        * Prefetch all rows into temporary file
        * Tell number of rows
        * Get a row directly by its position
        * Iterate after closing its containing transaction level or
            even the database connection
        * Use multiple iterators from multiple threads

    Instead of creating instances by hand, use the connection object:

    q = connection.cquery(sql,params)

    Then iterate in one of three Query compatible ways:

        # Dicts
        for d in q.iterdicts():
            print d # Dict of {fieldname:fieldvalue}

        # Rows
        for row in q.iterrows():
            print row # Tuple

        # Create  Iterator manually
        qi = iter(q)
        for qi in q:
            print qi[0]      # access value by field index
            print qi['name'] # access value by field name

    NOTES:

    * Prefetching all rows takes time and can generate huge network
        traffic or disk I/O.
    * Prefetching all rows won't consume too much memory because
        data is saved into a temp file.
    * After prefetching, this query is completely independent of
        the original database connection. Before you use it, think
        about transaction isolation levels!
    * CQuery is duck-compatible with the unidirectional Query.

    """
    def __init__(self, connection, sql, params=None):
        """Create a new SimpleQuery.

        @param connection: a Connection instance.
        @param sql: a SQL query to run
        @param params: parameters for the SQL query
        """
        self.conn = connection
        self.sql = sql
        self.cur = self.conn.getcursorfor(sql, params)
        try:
            self.fieldnames = self.conn._getcursorfields(self.cur)
            self._prefetch_all()
        finally:
            self.conn._closecur(self.cur)

    def _prefetch_all(self):
        # Create tmpfile, then write pickle(self.cur.fetchmany()) ?
        raise NotImplementedError

    def close(self):
        """Close the cursor associated to the query object.

        CQuery does nothing here..."""
        pass

    def __iter__(self):
        """Iterate through query with row iterator."""
        return CQueryRowIterator(self)

    def iterrows(self):
        """Iterate through rows as tuples."""
        return CQueryRowIterator(self)

    def iterdicts(self):
        """Iterate through rows as dicts."""
        return CQueryDictIterator(self)


class CQueryBaseIterator:
    """Simple iterator for Query.

    Allows field value access by field index and field name.
    """
    def __init__(self, query):
        self.query = query
        self._row = None  # ??? Should be unpickled?

    def __iter__(self):
        return self

    def next(self):
        # ??? Should be unpickled?
        raise NotImplementedError

    def __getitem__(self, key):
        """Simulating dicts

        You can get a fields' value with either q[fieldname] or q[fieldno].
        Indexing of fields starts from zero.
        """
        if isinstance(key, str):
            try:
                index = self.query.fieldnames.index(key)
            except ValueError:
                raise KeyError(_('no such field: "%s"') % key[:20])
        else:
            index = key
        return self._row[index]

    def get_dict(self):
        """Return the current row as a dictionary.

        Indexed by field names only."""
        return dict(zip(self.fieldnames, self._row))

class CQueryRowIterator(CQueryBaseIterator):
    def next(self):
        pass

class CQueryDictIterator(CQueryBaseIterator):
    def next(self):
        pass