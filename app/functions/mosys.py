import pyodbc
import pandas as pd
import logging
import os
import uuid
import warnings
import concurrent.futures
from contextlib import contextmanager

from app.functions import nrildim_journal

logger = logging.getLogger(__name__)

# Centralize the connection string
CONNECTION_STRING = (
	"DSN=STAAMP_DB;ArrayFetchOn=1;ArrayBufferSize=8;TransportHint=TCP;DecimalSymbol=,;;")

# The PSQL/Actian ODBC driver IGNORES pyodbc's timeout= kwarg and
# SQL_ATTR_LOGIN_TIMEOUT (verified empirically: a failing connect to an
# unreachable DSN took ~43s regardless). So we bound the connect ourselves by
# running it on a worker thread and giving up after CONNECT_TIMEOUT seconds.
# This turns an ~86s two-connect "hang" on /spc-tweaks into a fast, clear error.
CONNECT_TIMEOUT = int(os.environ.get('MOSYS_DB_CONNECT_TIMEOUT', '6') or '6')
_connect_pool = concurrent.futures.ThreadPoolExecutor(
	max_workers=4, thread_name_prefix='pyodbc-connect')


def _bounded_connect(conn_str: str, seconds: int):
	"""pyodbc.connect with a hard wall-clock bound.

	If the connect does not complete within ``seconds`` we abandon it (the DSN
	is effectively unreachable) and raise a clean ConnectionError. The orphaned
	attempt keeps running on the pool thread and is closed if/when it finally
	returns, so we never leak a live handle.
	"""
	future = _connect_pool.submit(pyodbc.connect, conn_str)
	try:
		return future.result(timeout=seconds)
	except concurrent.futures.TimeoutError:
		def _close_late(f):
			try:
				f.result().close()
			except Exception:  # noqa: BLE001 - best-effort cleanup of abandoned handle
				pass
		future.add_done_callback(_close_late)
		raise ConnectionError(
			f"Database connection did not complete within {seconds}s; "
			f"the MOSYS database (DSN=STAAMP_DB) is unreachable.")

# Columns forming the NRILDIM natural key (raw, DB-stored form). Keep in sync
# with mosys_data.NATURAL_KEY_COLS; duplicated here to avoid an import cycle.
_NATURAL_KEY_COLS = ['ARTICOLO', 'DATA_RILEVAMENTO', 'ORA_RILEVAMENTO',
                     'NUMERO_RIFERIMENTO', 'NUMERO_STAMPATA', 'NUMERO_FIGURA']


@contextmanager
def pervasive_connection(readonly: bool = True):
	"""A context manager for handling database connections."""
	conn_str = f"{CONNECTION_STRING}readonly={'True' if readonly else 'False'};"
	conn = None
	try:
		conn = _bounded_connect(conn_str, CONNECT_TIMEOUT)
		yield conn
	except (pyodbc.Error, ConnectionError) as e:
		print(f"Database connection error: {e}")
		# Re-raise or handle as needed
		raise
	finally:
		if conn:
			conn.close()


def get_pervasive(query: str, params: tuple = None) -> pd.DataFrame:
	"""Executes a read-only query and returns a cleaned pandas DataFrame."""
	with pervasive_connection(readonly=True) as conn:
		# pandas warns that a raw pyodbc connection isn't a SQLAlchemy connectable.
		# It works fine here (plain SELECTs) and the DBAPI2 path is stable for our
		# use, so suppress just that one cosmetic message — nothing else.
		with warnings.catch_warnings():
			warnings.filterwarnings(
				'ignore',
				message='pandas only supports SQLAlchemy connectable.*',
				category=UserWarning)
			df = pd.read_sql(query, conn, params=params)
	
	# More efficient whitespace stripping
	for col in df.select_dtypes(include=['object']).columns:
		df[col] = df[col].str.strip()

	return df


# ==========================================================================
#  Safe NRILDIM write path  (IMPLEMENTATION-PLAN.md §3.1 — 8 guarantees)
#  Ships DRY-RUN BY DEFAULT. Live writes only when dry_run=False is passed
#  explicitly by the caller AND the WRITE_ENABLED config flag is truthy.
# ==========================================================================

class WriteError(Exception):
	"""Raised on any anomaly in the NRILDIM write path (triggers rollback)."""


def _default_connection_factory():
	"""Reuse the existing context manager with writes allowed (§2.2)."""
	return pervasive_connection(readonly=False)


def _resolve_removed_flag_value(cursor, schema_prefix):
	"""FLAG_RIMOSSO value that marks a removed characteristic = least-occurring
	value across NSCHEDIM (per spec.md line 50-52)."""
	rows = cursor.execute(
		f"SELECT FLAG_RIMOSSO, COUNT(*) AS c FROM {schema_prefix}NSCHEDIM "
		f"GROUP BY FLAG_RIMOSSO ORDER BY c ASC"
	).fetchall()
	if not rows:
		return None
	return rows[0][0]


def _characteristic_is_live(cursor, schema_prefix, numero_riferimento, removed_value):
	"""Integrity gate (§3.1 #2): the dimension must resolve via
	SCHEDIM1.RIF_MISURA -> NSCHEDIM.NUMERO_RIFERIMENTO to a live, non-removed
	characteristic that also has a tolerance anchor row in SCHEDIM1."""
	nsched = cursor.execute(
		f"SELECT FLAG_RIMOSSO FROM {schema_prefix}NSCHEDIM WHERE NUMERO_RIFERIMENTO = ?",
		(numero_riferimento,),
	).fetchall()
	if not nsched:
		return False, "no NSCHEDIM characteristic"
	if removed_value is not None and nsched[0][0] == removed_value:
		return False, "characteristic removed (FLAG_RIMOSSO)"
	anchor = cursor.execute(
		f"SELECT 1 FROM {schema_prefix}SCHEDIM1 WHERE RIF_MISURA = ?",
		(numero_riferimento,),
	).fetchall()
	if not anchor:
		return False, "no SCHEDIM1 tolerance anchor"
	return True, None


def _build_update(update, schema_prefix):
	"""Build a single-row UPDATE + its matching WHERE, plus a COUNT probe."""
	set_cols = sorted(update['new_raw'].keys())
	set_clause = ", ".join(f"{c} = ?" for c in set_cols)
	set_params = [update['new_raw'][c] for c in set_cols]

	key = update['key']
	key_cols = [c for c in _NATURAL_KEY_COLS if c in key]
	where_clause = " AND ".join(f"{c} = ?" for c in key_cols)
	where_params = [key[c] for c in key_cols]

	table = f"{schema_prefix}NRILDIM"
	update_sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
	count_sql = f"SELECT COUNT(*) FROM {table} WHERE {where_clause}"
	return update_sql, set_params + where_params, count_sql, where_params, key_cols


def execute_nrildim_updates(updates, *, dry_run=True, connection_factory=None,
                            schema_prefix='STAAMPDB.', journal_path=None,
                            batch_id=None):
	"""Apply tweaked MIS values to NRILDIM under the full safe-write doctrine.

	Args:
		updates: list of dicts from spc.compute_tweaked_updates, each
			``{'key': {<natural key>}, 'numero_riferimento': ..,
			   'new_raw': {'MIS0k': int, ..}}``.
		dry_run: when True (DEFAULT) nothing is written — the planned SQL and a
			SELECT COUNT(*) for each WHERE clause are returned so 1-row targeting
			can be proven before a live write is ever contemplated.
		connection_factory: callable returning a context manager yielding a
			DB-API connection (injected in tests). Defaults to the production
			``pervasive_connection(readonly=False)``.
		schema_prefix: table-name prefix ('STAAMPDB.' in prod, '' in tests).
		journal_path / batch_id: pre-image journal location / batch id.

	Returns a structured report dict; never partially commits (atomic §3.1 #5).
	"""
	report = {
		'dry_run': bool(dry_run),
		'batch_id': batch_id or uuid.uuid4().hex,
		'requested': len(updates or []),
		'planned': [],
		'updated_rows': 0,
		'integrity_failures': [],
		'status': 'noop',
		'error': None,
	}
	if not updates:
		report['status'] = 'noop'
		return report

	# Structural validation before touching any connection.
	for u in updates:
		if not u.get('new_raw'):
			raise WriteError("update has no MIS cells to write")
		missing = [c for c in _NATURAL_KEY_COLS if c not in u.get('key', {})]
		if missing:
			raise WriteError(f"update missing natural-key columns: {missing}")

	factory = connection_factory or _default_connection_factory
	jkwargs = {} if journal_path is None else {'path': journal_path}

	with factory() as conn:
		cursor = conn.cursor()
		removed_value = _resolve_removed_flag_value(cursor, schema_prefix)

		# ---- Integrity gate for every update (abort all if any fail) ----
		live_cache = {}
		for u in updates:
			nr = u.get('numero_riferimento')
			if nr not in live_cache:
				live_cache[nr] = _characteristic_is_live(cursor, schema_prefix, nr, removed_value)
			ok, reason = live_cache[nr]
			if not ok:
				report['integrity_failures'].append({'numero_riferimento': nr, 'reason': reason})
		if report['integrity_failures']:
			report['status'] = 'aborted'
			report['error'] = 'integrity gate failed'
			return report

		# ---- Plan (also proves 1-row targeting) ----
		plans = []
		for u in updates:
			update_sql, params, count_sql, where_params, key_cols = _build_update(u, schema_prefix)
			would_match = cursor.execute(count_sql, where_params).fetchall()[0][0]
			plan = {'sql': update_sql, 'params': params, 'would_match': int(would_match),
			        'key': u['key'], 'new_raw': u['new_raw']}
			plans.append((u, update_sql, params, where_params, key_cols))
			report['planned'].append(plan)

		if dry_run:
			report['status'] = 'dry_run'
			bad = [p for p in report['planned'] if p['would_match'] != 1]
			if bad:
				report['error'] = f"{len(bad)} update(s) would not match exactly 1 row"
			return report

		# ---- Live write (atomic) ----
		conn.autocommit = False
		try:
			# Pre-image journal BEFORE any UPDATE (§3.1 #4).
			entries = []
			for (u, _sql, _p, where_params, key_cols) in plans:
				cols = sorted(u['new_raw'].keys())
				sel = (f"SELECT {', '.join(cols)} FROM {schema_prefix}NRILDIM "
				       f"WHERE {' AND '.join(f'{c} = ?' for c in key_cols)}")
				pre = cursor.execute(sel, where_params).fetchall()
				preimage = {c: pre[0][i] for i, c in enumerate(cols)} if pre else {}
				entries.append({'key': u['key'], 'preimage': preimage})
			nrildim_journal.write_preimage(report['batch_id'], entries, **jkwargs)

			# Apply each UPDATE, asserting exactly one row per statement.
			for (u, update_sql, params, where_params, key_cols) in plans:
				cursor.execute(update_sql, params)
				if cursor.rowcount != 1:
					raise WriteError(
						f"UPDATE affected {cursor.rowcount} rows (expected 1); rolling back")
				report['updated_rows'] += 1

			conn.commit()

			# ---- Post-commit verify + auto-restore (§3.1 #6) ----
			for (u, _sql, _p, where_params, key_cols) in plans:
				cols = sorted(u['new_raw'].keys())
				sel = (f"SELECT {', '.join(cols)} FROM {schema_prefix}NRILDIM "
				       f"WHERE {' AND '.join(f'{c} = ?' for c in key_cols)}")
				stored = cursor.execute(sel, where_params).fetchall()
				if not stored or any(int(stored[0][i]) != int(u['new_raw'][c])
				                     for i, c in enumerate(cols)):
					raise WriteError("post-commit verification mismatch")

			# Success: purge journal batch (§3.1 #7).
			nrildim_journal.purge_batch(report['batch_id'], **jkwargs)
			report['status'] = 'committed'
			return report

		except Exception as exc:  # noqa: BLE001 — any anomaly rolls back the batch
			try:
				conn.rollback()
			except Exception:  # pragma: no cover - rollback best effort
				logger.exception("rollback failed for batch %s", report['batch_id'])
			report['status'] = 'failed'
			report['error'] = str(exc)
			logger.error("NRILDIM write batch %s failed: %s", report['batch_id'], exc)
			raise WriteError(report['error']) from exc