"""Simple unidirectional query.

Makes it easy to access the rows of a simple rowset."""
import venus.i18n
_ = venus.i18n.get_my_translator(__file__)


class Query:
    """Simple unidirectional query.

    Makes it easier to access the rows of a simple rowset.
    Enchanted features (compared to simple DB API 2.0 cursor object):

        * access field values by name
        * auto close cursor for commited/rolled back transactions
        * various ways to iterate over

    Instead of creating instances by hand, use the connection object:

    q = connection.query(sql,params)

    Then iterate through the query in one of three possible ways:

        # Dicts
        for d in q.iterdicts():
            print d # Dict of {fieldname:fieldvalue}

        # Rows
        for row in q.iterrows():
            print row # Tuple

        # QueryIterator
        for qi in q:
            print qi[0]      # access value by field index
            print qi['name'] # access value by field name

    NOTES:

    * You cannot tell how many rows will be returned. In order to tell
        that, you will have to iterate over all rows.
    * This is an unidirectional query.  You can only iterate through the
        query once, in one direction.
    * Query instances may be implemented with server side cursors.
    * You can only use Query instances in the same transaction level
        where you created them.
    * If you want bi-directional, rowcount-able queries that can be
        used outside their transaction level, use CachedQuery instances.
        But be aware that they prefetch all rows from the server!

    '''TODO''': Test if fetching smaller number of rows (<100) with
        fetchmany() would be faster then calling fetchone().
        Probably, for some RDBMS they would be...
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
        self.fieldnames = self.conn._getcursorfields(self.cur)
        self._row = None

    def _fetchnext(self):
        """Internal method used by QueryIterator."""
        self._row = self.cur.fetchone()
        if self._row is None:
            raise StopIteration

    def close(self):
        """Close the cursor associated to the query object.

        Some DBMS require closing all cursors before you could
            commit or rollback the transaction they where created in."""
        self.conn._closecur(self.cur)

    def __iter__(self):
        """Iterate through query with row iterator."""
        return QueryIterator(self)

    def iterrows(self):
        """Iterate through rows as tuples."""
        return iter(self.cur)

    def iterdicts(self):
        """Iterate through rows as dicts."""
        while True:
            self._row = self.cur.fetchone()
            if self._row is None:
                raise StopIteration
            yield self.get_dict()

    def __getitem__(self, key):
        """Simulating dicts

        You can get a fields' value with either q[fieldname] or q[fieldno].
        Indexing of fields starts from zero.
        """
        if isinstance(key, str):
            try:
                index = self.fieldnames.index(key)
            except ValueError:
                raise KeyError(_('no such field: "%s"') % key[:20])
        else:
            index = key
        return self._row[index]

    def get_dict(self):
        """Return the current row as a dictionary.

        Indexed by field names only."""
        return dict(list(zip(self.fieldnames, self._row)))


class QueryIterator:
    """Simple iterator for Query.

    Allows field value access by field index and field name.
    """
    def __init__(self, query):
        self.query = query

    def __iter__(self):
        return self

    def __next__(self):
        self.query._fetchnext()
        return self.query
