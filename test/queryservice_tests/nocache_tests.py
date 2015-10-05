import time

from vtdb import cursor
from vtdb import dbexceptions
from vtdb import field_types
from vtdb import tablet as tablet_conn

import environment
import framework
import nocache_cases
import utils


class TestNocache(framework.TestCase):

  def test_health(self):
    self.assertEqual(self.env.health(), "ok")

  def test_query_stats(self):
    bv = {"eid": 1}
    self.env.execute(
        "select eid as query_stats from vtocc_a where eid = :eid", bv)
    self._verify_query_stats(
        self.env.query_stats(),
        "select eid as query_stats from vtocc_a where eid = :eid", "vtocc_a",
        "PASS_SELECT", 1, 2, 0)
    tstartQueryCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryCounts"], "vtocc_a", "PASS_SELECT")
    tstartRowCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryRowCounts"], "vtocc_a", "PASS_SELECT")
    tstartErrorCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryErrorCounts"], "vtocc_a", "PASS_SELECT")
    tstartTimesNs = self._get_vars_query_stats(
        self.env.debug_vars()["QueryTimesNs"], "vtocc_a", "PASS_SELECT")

    try:
      self.env.execute(
          "select eid as query_stats from vtocc_a where dontexist(eid) = :eid",
          bv)
    except dbexceptions.DatabaseError:
      pass
    else:
      self.fail("Did not receive exception: " + query)
    self._verify_query_stats(
        self.env.query_stats(),
        "select eid as query_stats from vtocc_a where dontexist(eid) = :eid",
        "vtocc_a", "PASS_SELECT", 1, 0, 1)
    tendQueryCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryCounts"], "vtocc_a", "PASS_SELECT")
    tendRowCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryRowCounts"], "vtocc_a", "PASS_SELECT")
    tendErrorCounts = self._get_vars_query_stats(
        self.env.debug_vars()["QueryErrorCounts"], "vtocc_a", "PASS_SELECT")
    tendTimesNs = self._get_vars_query_stats(
        self.env.debug_vars()["QueryTimesNs"], "vtocc_a", "PASS_SELECT")
    self.assertEqual(tstartQueryCounts + 1, tendQueryCounts)
    self.assertEqual(tstartRowCounts, tendRowCounts)
    self.assertEqual(tstartErrorCounts + 1, tendErrorCounts)
    self.assertTrue((tendTimesNs - tstartTimesNs) > 0)

  def test_other(self):
    cu = self.env.execute("show variables like 'version'")
    for v in cu:
      self.assertEqual(v[0], "version")
    cu = self.env.execute("describe vtocc_a")
    self.assertEqual(cu.rowcount, 4)
    cu = self.env.execute("explain vtocc_a")
    self.assertEqual(cu.rowcount, 4)

  def _verify_mismatch(self, query, bindvars=None):
    self._verify_error(query, bindvars, "error: type mismatch")

  def _verify_error(self, query, bindvars, err):
    self.env.conn.begin()
    try:
      self.env.execute(query, bindvars)
    except dbexceptions.DatabaseError as e:
      self.assertContains(str(e), err)
    else:
      self.fail("Did not receive exception: " + query)
    finally:
      self.env.conn.rollback()

  def _get_vars_query_stats(self, query_stats, table, plan):
    return query_stats[table + "." + plan]

  def _verify_query_stats(
      self, query_stats, query, table, plan, count, rows, errors):
    for stat in query_stats:
      if stat["Query"] != query:
        continue
      self.assertEqual(stat["Table"], table)
      self.assertEqual(stat["Plan"], plan)
      self.assertEqual(stat["QueryCount"], count)
      self.assertEqual(stat["RowCount"], rows)
      self.assertEqual(stat["ErrorCount"], errors)
      self.assertTrue(stat["Time"] > 0)
      return
    self.fail("query %s not found" % query)

  def test_sqls(self):
    error_count = self.env.run_cases(nocache_cases.cases)
    if error_count != 0:
      self.fail("test_execution errors: %d"%(error_count))

  def test_table_acl_no_access(self):
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("select * from vtocc_acl_no_access where key1=1")
    self.env.conn.begin()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("delete from vtocc_acl_no_access where key1=1")
    self.env.conn.commit()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("alter table vtocc_acl_no_access comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      cu.execute("select * from vtocc_acl_no_access where key1=1", {})
    cu.close()

  def test_table_acl_read_only(self):
    self.env.execute("select * from vtocc_acl_read_only where key1=1")
    self.env.conn.begin()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("delete from vtocc_acl_read_only where key1=1")
    self.env.conn.commit()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("alter table vtocc_acl_read_only comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    cu.execute("select * from vtocc_acl_read_only where key1=1", {})
    cu.fetchall()
    cu.close()

  def test_table_acl_read_write(self):
    self.env.execute("select * from vtocc_acl_read_write where key1=1")
    self.env.conn.begin()
    self.env.execute("delete from vtocc_acl_read_write where key1=1")
    self.env.conn.commit()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("alter table vtocc_acl_read_write comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    cu.execute("select * from vtocc_acl_read_write where key1=1", {})
    cu.fetchall()
    cu.close()

  def test_table_acl_admin(self):
    self.env.execute("select * from vtocc_acl_admin where key1=1")
    self.env.conn.begin()
    self.env.execute("delete from vtocc_acl_admin where key1=1")
    self.env.conn.commit()
    self.env.execute("alter table vtocc_acl_admin comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    cu.execute("select * from vtocc_acl_admin where key1=1", {})
    cu.fetchall()
    cu.close()

  def test_table_acl_unmatched(self):
    self.env.execute("select * from vtocc_acl_unmatched where key1=1")
    self.env.conn.begin()
    self.env.execute("delete from vtocc_acl_unmatched where key1=1")
    self.env.conn.commit()
    self.env.execute("alter table vtocc_acl_unmatched comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    cu.execute("select * from vtocc_acl_unmatched where key1=1", {})
    cu.fetchall()
    cu.close()

  def test_table_acl_all_user_read_only(self):
    self.env.execute("select * from vtocc_acl_all_user_read_only where key1=1")
    self.env.conn.begin()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute("delete from vtocc_acl_all_user_read_only where key1=1")
    self.env.conn.commit()
    with self.assertRaisesRegexp(
        dbexceptions.DatabaseError, ".*table acl error.*"):
      self.env.execute(
          "alter table vtocc_acl_all_user_read_only comment 'comment'")
    cu = cursor.StreamCursor(self.env.conn)
    cu.execute("select * from vtocc_acl_all_user_read_only where key1=1", {})
    cu.fetchall()
    cu.close()
