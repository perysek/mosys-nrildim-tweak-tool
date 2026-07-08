// Reusable client-side sortable-table behaviour for the admin list pages
// (Employees / Users / Roles). All three tables are small, server-rendered,
// and never paginated, so sorting the existing rows in place is enough —
// no reload, no server round-trip.
(function () {
    function cellValue(row, col) {
        var cell = row.cells[col];
        if (!cell) return '';
        var override = cell.getAttribute('data-sort-value');
        return (override !== null ? override : (cell.textContent || '')).trim();
    }

    function compare(x, y) {
        var xn = parseFloat(x), yn = parseFloat(y);
        if (x !== '' && y !== '' && !isNaN(xn) && !isNaN(yn)) return xn - yn;
        var xl = x.toLowerCase(), yl = y.toLowerCase();
        return xl < yl ? -1 : (xl > yl ? 1 : 0);
    }

    function sortRows(table, col, dir) {
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) {
            var cmp = compare(cellValue(a, col), cellValue(b, col));
            return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
    }

    function setIcon(th, dir) {
        var icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = dir === 'asc' ? '▲' : (dir === 'desc' ? '▼' : '⇅');
    }

    // Wires up every th[data-sort-col] in #tableId, then applies a default
    // sort (defaultCol/defaultDir) if given. Actions/toggle columns simply
    // omit data-sort-col and are left alone.
    window.initSortableTable = function (tableId, defaultCol, defaultDir) {
        var table = document.getElementById(tableId);
        if (!table) return;
        var ths = Array.prototype.slice.call(table.querySelectorAll('th[data-sort-col]'));

        ths.forEach(function (th) {
            var col = parseInt(th.getAttribute('data-sort-col'), 10);
            var btn = th.querySelector('.sort-btn');
            th.setAttribute('aria-sort', 'none');
            setIcon(th, 'none');
            if (!btn) return;
            btn.addEventListener('click', function () {
                var dir = th.getAttribute('aria-sort') === 'ascending' ? 'desc' : 'asc';
                ths.forEach(function (t) { t.setAttribute('aria-sort', 'none'); setIcon(t, 'none'); });
                th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
                setIcon(th, dir);
                sortRows(table, col, dir);
            });
        });

        if (defaultCol != null) {
            var defTh = table.querySelector('th[data-sort-col="' + defaultCol + '"]');
            if (defTh) {
                var dir = defaultDir === 'desc' ? 'desc' : 'asc';
                defTh.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
                setIcon(defTh, dir);
                sortRows(table, defaultCol, dir);
            }
        }
    };
})();
